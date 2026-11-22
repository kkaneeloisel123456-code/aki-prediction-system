# -*- coding: utf-8 -*-
"""CSV intake: preview validation and transactional patient/encounter import."""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import PlainTextResponse

from . import database as db
from .assets import load_assets
from .clinical_api import _access_map, _err, _normalise_values
from .database import json_dump, new_id, record_audit, utc_now
from .schemas import ImportCommitRequest

router = APIRouter(prefix="/api/imports", tags=["imports"])

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 500

ALIASES = {
    "病历号": "mrn", "姓名": "name", "性别": "sex", "出生年份": "birth_year",
    "出生年": "birth_year", "证件号末四位": "certificate_last4",
    "手机号末四位": "phone_last4", "就诊编号": "case_ref",
    "发生时间": "occurred_at", "就诊时间": "occurred_at", "手术类型": "surgery_type",
    "诊断": "diagnosis", "医嘱": "orders", "负责人ID": "owner_id",
    "mrn": "mrn", "name": "name", "sex": "sex", "birth_year": "birth_year",
    "certificate_last4": "certificate_last4", "phone_last4": "phone_last4",
    "case_ref": "case_ref", "occurred_at": "occurred_at",
    "surgery_type": "surgery_type", "diagnosis": "diagnosis", "orders": "orders",
    "owner_id": "owner_id",
}
IGNORED_COLUMNS = {"id", "patient_id", "序号", "备注"}
PATIENT_FIELDS = {
    "mrn", "name", "sex", "birth_year", "certificate_last4", "phone_last4",
    "owner_id",
}
ENCOUNTER_FIELDS = {"case_ref", "occurred_at", "surgery_type", "diagnosis", "orders"}


def _user(request: Request) -> dict[str, Any]:
    user = getattr(request.state, "user", None)
    if not user:
        raise _err("请先登录", 401)
    return user


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise _err("文件编码无法识别，请另存为 UTF-8 或 GBK CSV")


SEX_ALIASES = {
    "男": "男", "女": "女", "未知": "未知",
    "m": "男", "male": "男", "f": "女", "female": "女",
    "unknown": "未知", "": "未知",
}


def _normalise_sex(value: Any) -> str:
    key = str(value or "").strip().lower()
    if key in SEX_ALIASES:
        return SEX_ALIASES[key]
    raise ValueError("性别只能为 男 / 女 / 未知（也接受 M/F、male/female）")


def _parse_dt(value: str) -> datetime:
    text = value.strip().replace("/", "-")
    if not text:
        raise ValueError("empty")
    try:
        parsed = datetime.fromisoformat(text.replace(" ", "T").replace("Z", "+00:00"))
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y/%m/%d %H:%M"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        else:
            raise ValueError("invalid")
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    parsed = parsed.astimezone(timezone.utc)
    if parsed > datetime.now(timezone.utc):
        raise ValueError("future")
    return parsed


def _normalise_row(
    raw: dict[str, str], index: int, user: dict[str, Any],
    feature_names: set[str], conn: Any,
) -> dict[str, Any]:
    canonical: dict[str, str] = {}
    for key, value in raw.items():
        header = (key or "").strip()
        mapped = ALIASES.get(header, header)
        if mapped in feature_names or mapped in PATIENT_FIELDS or mapped in ENCOUNTER_FIELDS:
            canonical[mapped] = (value if value is not None else "").strip()
    errors: list[str] = []
    warnings: list[str] = []

    mrn = canonical.get("mrn", "")
    name = canonical.get("name", "")
    case_ref = canonical.get("case_ref", "")
    if not mrn:
        errors.append("病历号不能为空")
    if not name:
        errors.append("姓名不能为空")
    if not case_ref:
        errors.append("就诊编号不能为空")

    sex = canonical.get("sex") or "未知"
    try:
        sex = _normalise_sex(sex)
    except ValueError as exc:
        errors.append(str(exc))
    birth_year = None
    if canonical.get("birth_year"):
        try:
            birth_year = int(float(canonical["birth_year"]))
            if not 1900 <= birth_year <= 2100:
                errors.append("出生年份超出合理范围")
        except ValueError:
            errors.append("出生年份不是有效整数")

    occurred_at = None
    occurred_text = canonical.get("occurred_at", "")
    if not occurred_text:
        errors.append("发生时间不能为空")
    else:
        try:
            occurred_at = _parse_dt(occurred_text).isoformat()
        except ValueError as exc:
            if str(exc) == "future":
                errors.append("发生时间不能晚于当前时间")
            elif str(exc) == "empty":
                errors.append("发生时间不能为空")
            else:
                errors.append("发生时间格式无效，建议 YYYY-MM-DD HH:MM")

    feature_values = {
        key: value for key, value in canonical.items()
        if key in feature_names and value not in ("", "-", "NA", "N/A")
    }
    stored: dict[str, Any] = {}
    if feature_values:
        try:
            stored, _, invalid = _normalise_values(feature_values, allow_incomplete=False)
            if invalid:
                errors.append("超出合理范围：" + "、".join(invalid))
        except HTTPException as exc:
            errors.append(str(exc.detail))
    else:
        warnings.append("未录入任何模型指标，导入后需补录才能预测")

    patient_id = None
    patient_exists = False
    if mrn:
        existing = conn.execute(
            "SELECT * FROM patients WHERE mrn=? COLLATE NOCASE AND active=1", (mrn,)
        ).fetchone()
        if existing:
            patient_exists = True
            patient_id = existing["id"]
            access = _access_map(conn, user, existing["id"])
            if not access["view"]:
                errors.append("该病历号对应的患者档案不在当前账号授权范围内")
            elif not access["edit"]:
                errors.append("当前账号对该患者只有只读权限，不能导入就诊")
        else:
            owner_id = canonical.get("owner_id") or ""
            requested = owner_id or (user["id"] if user["role"] == "doctor" else "")
            if not requested:
                errors.append("管理员导入新患者时必须填写负责人ID")
            else:
                owner = conn.execute(
                    "SELECT 1 FROM users WHERE id=? AND role='doctor' AND active=1",
                    (requested,),
                ).fetchone()
                if not owner:
                    errors.append("负责人必须是有效医生账号")
        if case_ref and existing:
            duplicate = conn.execute(
                "SELECT 1 FROM encounters WHERE patient_id=? AND case_ref=?",
                (existing["id"], case_ref),
            ).fetchone()
            if duplicate:
                errors.append("该患者已存在相同就诊编号")

    return {
        "index": index,
        "mrn": mrn, "name": name, "sex": sex,
        "birth_year": birth_year,
        "certificate_last4": canonical.get("certificate_last4") or None,
        "phone_last4": canonical.get("phone_last4") or None,
        "owner_id": canonical.get("owner_id") or None,
        "case_ref": case_ref, "occurred_at": occurred_at,
        "surgery_type": canonical.get("surgery_type") or None,
        "diagnosis": canonical.get("diagnosis", ""),
        "orders": canonical.get("orders", ""),
        "values": stored,
        "patient_id": patient_id,
        "patient_exists": patient_exists,
        "errors": errors,
        "warnings": warnings,
    }


@router.get("/template.csv", response_class=PlainTextResponse)
def template_csv(request: Request):
    _user(request)
    headers = [
        "病历号", "姓名", "性别", "出生年份", "证件号末四位", "手机号末四位",
        "就诊编号", "发生时间", "手术类型", "诊断", "医嘱",
    ] + list(load_assets()["features"])
    sample = [
        "MRN-DEMO-001", "示例患者", "男", "1960", "1234", "5678",
        "CASE-20261122-001", "2026-11-20 09:00", "冠脉搭桥术",
        "冠心病，拟行冠脉搭桥术", "术后监测肌酐与尿量",
    ] + [""] * len(load_assets()["features"])
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(headers)
    writer.writerow(sample)
    return PlainTextResponse(
        "\ufeff" + buffer.getvalue(), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="AKI_import_template.csv"'},
    )


@router.post("/preview")
async def preview_import(request: Request, file: UploadFile = File(...)):
    user = _user(request)
    db.ensure_initialized()
    raw = await file.read()
    if len(raw) > MAX_BYTES:
        raise _err("文件超过 5 MB 限制", 413)
    if not raw:
        raise _err("文件为空")
    text = _decode(raw)
    try:
        reader = csv.DictReader(io.StringIO(text))
        headers = [str(h or "").strip() for h in (reader.fieldnames or [])]
        source_rows = list(reader)
    except csv.Error as exc:
        raise _err(f"CSV 解析失败：{exc}") from None
    if not headers:
        raise _err("CSV 缺少表头")
    if len(source_rows) > MAX_ROWS:
        raise _err(f"单批最多 {MAX_ROWS} 行，当前 {len(source_rows)} 行", 413)

    feature_names = set(load_assets()["features"])
    mapped_headers = [ALIASES.get(h, h) for h in headers]
    recognized = {h for h in mapped_headers if h in feature_names or h in PATIENT_FIELDS or h in ENCOUNTER_FIELDS}
    ignored = {h for h, orig in zip(mapped_headers, headers) if orig.lower() in IGNORED_COLUMNS}
    unknown = sorted({
        orig for h, orig in zip(mapped_headers, headers)
        if h not in recognized and orig.lower() not in IGNORED_COLUMNS
    })
    header_errors: list[str] = []
    missing_required = [
        label for label, key in (("病历号", "mrn"), ("姓名", "name"), ("就诊编号", "case_ref"), ("发生时间", "occurred_at"))
        if key not in recognized
    ]
    if missing_required:
        header_errors.append("缺少必需列：" + "、".join(missing_required))
    if unknown:
        header_errors.append("存在无法识别的列：" + "、".join(unknown[:6]))

    with db.reader() as conn:
        rows = [
            _normalise_row(row, i + 2, user, feature_names, conn)
            for i, row in enumerate(source_rows)
        ]
    valid = sum(1 for row in rows if not row["errors"])
    return {
        "filename": file.filename,
        "headers": headers,
        "recognized_headers": sorted(recognized),
        "ignored_headers": sorted(ignored),
        "header_errors": header_errors,
        "rows": rows,
        "summary": {
            "total": len(rows), "valid": valid,
            "invalid": len(rows) - valid,
            "new_patients": sum(1 for r in rows if not r["patient_exists"] and not r["errors"]),
            "existing_patients": sum(1 for r in rows if r["patient_exists"] and not r["errors"]),
        },
    }


@router.post("/commit")
def commit_import(req: ImportCommitRequest, request: Request):
    user = _user(request)
    db.ensure_initialized()
    if not req.rows:
        raise _err("没有可导入的数据")
    if len(req.rows) > MAX_ROWS:
        raise _err(f"单批最多 {MAX_ROWS} 行", 413)
    feature_names = set(load_assets()["features"])
    results: list[dict[str, Any]] = []
    imported = 0
    failed = 0
    for row in req.rows:
        index = row.get("index", len(results) + 1)
        try:
            mrn = str(row.get("mrn") or "").strip().upper()
            name = str(row.get("name") or "").strip()
            case_ref = str(row.get("case_ref") or "").strip()
            occurred_text = str(row.get("occurred_at") or "")
            if not mrn or not name or not case_ref:
                raise ValueError("病历号、姓名和就诊编号不能为空")
            try:
                occurred = _parse_dt(occurred_text)
            except ValueError:
                raise ValueError("发生时间格式无效") from None
            sex = _normalise_sex(row.get("sex"))
            diagnosis_text = str(row.get("diagnosis") or "").strip()
            orders_text = str(row.get("orders") or "").strip()
            if len(diagnosis_text) > 4000:
                raise ValueError("诊断超过 4000 字")
            if len(orders_text) > 4000:
                raise ValueError("医嘱超过 4000 字")
            values = row.get("values") or {}
            if not isinstance(values, dict):
                raise ValueError("指标格式无效")
            unknown = sorted(set(values) - feature_names)
            if unknown:
                raise ValueError(f"包含未知指标：{', '.join(unknown[:5])}")
            stored, numeric, invalid = _normalise_values(values, allow_incomplete=False)
            if invalid:
                raise ValueError("指标超出合理范围：" + "、".join(invalid))
            with db.transaction(immediate=True) as conn:
                existing = conn.execute(
                    "SELECT * FROM patients WHERE mrn=? COLLATE NOCASE AND active=1", (mrn,)
                ).fetchone()
                if existing:
                    if existing["name"] != name:
                        raise ValueError("病历号已存在但姓名不一致，该行未导入")
                    patient_id = existing["id"]
                    access = _access_map(conn, user, patient_id)
                    if not access["edit"]:
                        raise ValueError("无权向该患者导入就诊")
                else:
                    owner_ref = str(row.get("owner_id") or "").strip()
                    if not owner_ref:
                        owner_ref = user["id"] if user["role"] == "doctor" else ""
                    if not owner_ref:
                        raise ValueError("新患者必须指定负责人（医生用户名）")
                    if user["role"] == "doctor" and owner_ref not in {user["id"], user["username"]}:
                        raise ValueError("医生只能把新患者建在自己名下")
                    doctor = conn.execute(
                        """SELECT id FROM users WHERE role='doctor' AND active=1
                           AND (username=? COLLATE NOCASE OR id=?)""",
                        (owner_ref, owner_ref),
                    ).fetchone()
                    if not doctor:
                        raise ValueError("负责人必须是有效医生")
                    owner_id = doctor["id"]
                    if user["role"] != "doctor" and owner_id == user["id"]:
                        raise ValueError("请填写医生用户名，而不是管理员账号")
                    patient_id = new_id("P")
                    conn.execute(
                        """INSERT INTO patients
                           (id,mrn,name,sex,birth_year,certificate_last4,phone_last4,
                            owner_id,active,created_at,updated_at)
                           VALUES(?,?,?,?,?,?,?,?,1,?,?)""",
                        (
                            patient_id, mrn, name, sex,
                            row.get("birth_year"), row.get("certificate_last4") or None,
                            row.get("phone_last4") or None, owner_id, utc_now(), utc_now(),
                        ),
                    )
                encounter_id = new_id("E")
                conn.execute(
                    """INSERT INTO encounters
                       (id,patient_id,case_ref,occurred_at,surgery_type,values_json,
                        diagnosis,orders,status,current_prediction_id,row_version,
                        created_by,updated_by,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,'draft',NULL,1,?,?,?,?)""",
                    (
                        encounter_id, patient_id, case_ref, occurred.isoformat(),
                        str(row.get("surgery_type") or "").strip() or None,
                        json_dump(stored), diagnosis_text, orders_text,
                        user["id"], user["id"],
                        utc_now(), utc_now(),
                    ),
                )
                record_audit(
                    conn, actor_type="user", actor_id=user["id"],
                    action="import_row_create", entity_type="encounter",
                    entity_id=encounter_id,
                    detail={"patient_id": patient_id, "mrn": mrn, "case_ref": case_ref,
                            "filename": req.filename, "row": index},
                    ip=request.client.host if request.client else None,
                )
            imported += 1
            results.append({"index": index, "ok": True, "patient_id": patient_id,
                            "encounter_id": encounter_id})
        except (ValueError, HTTPException) as exc:
            failed += 1
            message = exc.detail if isinstance(exc, HTTPException) else str(exc)
            results.append({"index": index, "ok": False, "error": str(message)})
        except Exception as exc:
            failed += 1
            message = str(exc)
            if "UNIQUE constraint failed: encounters" in message:
                message = "同一患者下就诊编号已存在，该行未导入"
            elif "UNIQUE constraint failed: patients.mrn" in message:
                message = "病历号已存在，该行未导入"
            results.append({"index": index, "ok": False, "error": f"数据库写入失败：{message}"})

    batch_id = new_id("IMP")
    with db.transaction(immediate=True) as conn:
        conn.execute(
            """INSERT INTO import_batches
               (id,filename,created_by,total,imported,failed,status,detail_json,created_at)
               VALUES(?,?,?,?,?,?,'completed',?,?)""",
            (
                batch_id, req.filename[:200], user["id"], len(req.rows), imported,
                failed,
                json_dump({"failures": [r for r in results if not r["ok"]][:100]}),
                utc_now(),
            ),
        )
        record_audit(
            conn, actor_type="user", actor_id=user["id"], action="import_commit",
            entity_type="import_batch", entity_id=batch_id,
            detail={"filename": req.filename, "total": len(req.rows),
                    "imported": imported, "failed": failed},
            ip=request.client.host if request.client else None,
        )
    return {"batch_id": batch_id, "total": len(req.rows), "imported": imported,
            "failed": failed, "results": results}
