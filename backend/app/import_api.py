# -*- coding: utf-8 -*-
"""Tabular intake: XLSX/CSV preview, column mapping and transactional import.

The new path stores an immutable preview snapshot in ``import_batches`` and
commits with only the batch id.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import zipfile
from datetime import date, datetime, time, timezone
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import PlainTextResponse, Response
from openpyxl import Workbook, load_workbook
from openpyxl.utils import get_column_letter
from openpyxl.utils.datetime import from_excel

from . import database as db
from .assets import load_assets
from .clinical_api import _access_map, _birth_fields, _err, _normalise_values
from .database import json_dump, new_id, record_audit, utc_now
from .feature_labels import get_label
from .schemas import ImportCommitRequest

router = APIRouter(prefix="/api/imports", tags=["imports"])

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 500
MAX_XLSX_UNCOMPRESSED = 60 * 1024 * 1024
MAX_COLUMNS = 200
IGNORE = "__ignore__"

ALIASES = {
    "病历号": "mrn", "病历编号": "mrn", "病案号": "mrn", "住院号": "mrn",
    "姓名": "name", "患者姓名": "name", "病人姓名": "name",
    "性别": "sex", "出生年份": "birth_year",
    "出生年": "birth_year", "出生日期": "birth_date",
    "证件号末四位": "certificate_last4",
    "手机号末四位": "phone_last4", "就诊编号": "case_ref",
    "发生时间": "occurred_at", "就诊时间": "occurred_at", "手术类型": "surgery_type",
    "诊断": "diagnosis", "医嘱": "orders", "负责人ID": "owner_id",
    "mrn": "mrn", "name": "name", "sex": "sex", "birth_year": "birth_year",
    "certificate_last4": "certificate_last4", "phone_last4": "phone_last4",
    "birth_date": "birth_date",
    "case_ref": "case_ref", "occurred_at": "occurred_at",
    "surgery_type": "surgery_type", "diagnosis": "diagnosis", "orders": "orders",
    "owner_id": "owner_id",
}
IGNORED_COLUMNS = {"id", "patient_id", "序号", "备注"}
PATIENT_FIELDS = {
    "mrn", "name", "sex", "birth_year", "birth_date", "certificate_last4", "phone_last4",
    "owner_id",
}
ENCOUNTER_FIELDS = {"case_ref", "occurred_at", "surgery_type", "diagnosis", "orders"}
REQUIRED_FIELDS = (("mrn", "病历号"), ("name", "姓名"), ("case_ref", "就诊编号"), ("occurred_at", "发生时间"))

FIELD_LABELS = {
    "mrn": "病历号", "name": "姓名", "sex": "性别", "birth_year": "出生年份",
    "birth_date": "出生日期",
    "certificate_last4": "证件号末四位", "phone_last4": "手机号末四位",
    "owner_id": "负责人ID", "case_ref": "就诊编号", "occurred_at": "发生时间",
    "surgery_type": "手术类型", "diagnosis": "诊断", "orders": "医嘱",
}

SEX_ALIASES = {
    "男": "男", "女": "女", "未知": "未知",
    "m": "男", "male": "男", "f": "女", "female": "女",
    "unknown": "未知", "": "未知",
}


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


def _cell_text(value: Any) -> str:
    """Convert a cell to the text form expected by the existing validators."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, float):
        if not math.isfinite(value):
            return ""
        if value.is_integer() and abs(value) < 1e15:
            return str(int(value))
        return format(value, ".15g")
    return str(value).replace("\u00a0", " ").strip()


def _normalise_sex(value: Any) -> str:
    key = _cell_text(value).lower()
    if key in SEX_ALIASES:
        return SEX_ALIASES[key]
    raise ValueError("性别只能为 男 / 女 / 未知（也接受 M/F、male/female）")


def _parse_dt(value: Any) -> datetime:
    """Parse an ISO-like string, an Excel date cell or an Excel serial date."""
    parsed: datetime
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, time.min)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        serial = float(value)
        if not 20000 <= serial <= 80000:
            raise ValueError("invalid")
        parsed = from_excel(serial)
    else:
        text = _cell_text(value).replace("/", "-")
        if not text:
            raise ValueError("empty")
        try:
            numeric = float(text)
        except ValueError:
            numeric = None
        if numeric is not None and 20000 <= numeric <= 80000:
            parsed = from_excel(numeric)
        else:
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


def _read_csv(raw: bytes) -> tuple[list[str], list[tuple[int, list[str]]], int]:
    text = _decode(raw)
    try:
        table = list(csv.reader(io.StringIO(text)))
    except csv.Error as exc:
        raise _err(f"CSV 解析失败：{exc}") from None
    header_index = next(
        (i for i, row in enumerate(table) if any(_cell_text(cell) for cell in row)),
        None,
    )
    if header_index is None:
        raise _err("CSV 缺少表头")
    headers = [_cell_text(cell) for cell in table[header_index]]
    width = len(headers)
    rows: list[tuple[int, list[str]]] = []
    for offset, source in enumerate(table[header_index + 1:], start=header_index + 2):
        values = [_cell_text(cell) for cell in source[:width]]
        values.extend([""] * (width - len(values)))
        if any(values):
            rows.append((offset, values))
    return headers, rows, header_index + 1


def _read_xlsx(
    raw: bytes, sheet_name: str
) -> tuple[list[str], list[str], list[tuple[int, list[str]]], str]:
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            total = sum(item.file_size for item in archive.infolist())
            if total > MAX_XLSX_UNCOMPRESSED:
                raise _err("XLSX 解压后体积异常，已拒绝解析", 413)
    except zipfile.BadZipFile:
        raise _err("XLSX 文件损坏或不是有效的 Excel 工作簿") from None

    try:
        workbook = load_workbook(io.BytesIO(raw), read_only=False, data_only=True)
    except Exception as exc:
        raise _err(f"XLSX 解析失败：{exc}") from None
    sheet_names = list(workbook.sheetnames)
    if not sheet_name and len(sheet_names) > 1:
        return [], sheet_names, [], ""
    if not sheet_name:
        sheet_name = sheet_names[0]
    if sheet_name not in sheet_names:
        raise _err(f"找不到工作表：{sheet_name}")

    sheet = workbook[sheet_name]
    merged_values: dict[tuple[int, int], Any] = {}
    for merged in sheet.merged_cells.ranges:
        value = sheet.cell(row=merged.min_row, column=merged.min_col).value
        if value is None:
            continue
        for row in range(merged.min_row, merged.max_row + 1):
            for column in range(merged.min_col, merged.max_col + 1):
                merged_values[(row, column)] = value

    max_row = min(sheet.max_row, MAX_ROWS + 20)
    max_column = min(sheet.max_column, MAX_COLUMNS)
    table: list[tuple[int, list[str]]] = []
    for row_index in range(1, max_row + 1):
        values = []
        for column_index in range(1, max_column + 1):
            value = sheet.cell(row=row_index, column=column_index).value
            if value is None:
                value = merged_values.get((row_index, column_index))
            values.append(_cell_text(value))
        if any(values):
            table.append((row_index, values))

    if not table:
        raise _err("工作表没有可读取的数据")
    header_row, headers = table[0]
    # Drop trailing empty columns from the header width; internal gaps stay.
    while headers and not headers[-1]:
        headers.pop()
    if not headers:
        raise _err("工作表缺少表头")
    width = len(headers)
    data_rows: list[tuple[int, list[str]]] = []
    for row_index, values in table[1:]:
        values = values[:width]
        values.extend([""] * (width - len(values)))
        if any(values):
            data_rows.append((row_index, values))
    return headers, sheet_names, data_rows, sheet_name


def _auto_mapping(headers: list[str]) -> dict[str, str]:
    allowed = set(load_assets()["features"]) | PATIENT_FIELDS | ENCOUNTER_FIELDS
    label_to_feature = {get_label(feature)["label"]: feature for feature in load_assets()["features"]}
    mapping: dict[str, str] = {}
    for header in headers:
        key = header.strip()
        target = ALIASES.get(key) or label_to_feature.get(key) or (key if key in allowed else IGNORE)
        if key in IGNORED_COLUMNS:
            target = IGNORE
        mapping[header] = target
    return mapping


def _resolve_mapping(
    headers: list[str], mapping_text: str | None
) -> tuple[dict[str, str], list[str]]:
    allowed = set(load_assets()["features"]) | PATIENT_FIELDS | ENCOUNTER_FIELDS
    auto = _auto_mapping(headers)
    supplied: dict[str, Any] = {}
    if mapping_text and mapping_text.strip():
        try:
            parsed = json.loads(mapping_text)
        except json.JSONDecodeError:
            raise _err("列映射格式无效，应为 JSON 对象") from None
        if not isinstance(parsed, dict):
            raise _err("列映射格式无效，应为 JSON 对象")
        supplied = {str(k): v for k, v in parsed.items()}
    errors: list[str] = []
    mapping: dict[str, str] = {}
    for header in headers:
        target = supplied.get(header, auto.get(header, IGNORE))
        target = str(target or IGNORE).strip()
        if target in {"", "ignore", "__ignore__"}:
            target = IGNORE
        elif target not in allowed:
            errors.append(f"列“{header}”映射到未知字段：{target}")
            target = IGNORE
        mapping[header] = target

    used: dict[str, list[str]] = {}
    for header, target in mapping.items():
        if target != IGNORE:
            used.setdefault(target, []).append(header)
    for target, sources in used.items():
        if len(sources) > 1:
            label = FIELD_LABELS.get(target) or get_label(target)["label"] or target
            errors.append(f"多列映射到同一字段“{label}”：{'、'.join(sources)}")
    for key, label in REQUIRED_FIELDS:
        if key not in used:
            errors.append(f"缺少必需列：{label}")
    return mapping, errors


def _field_options() -> list[dict[str, str]]:
    options = [
        {"value": key, "label": label, "group": "患者信息"}
        for key, label in FIELD_LABELS.items()
        if key in PATIENT_FIELDS
    ]
    options.extend(
        {"value": key, "label": label, "group": "就诊信息"}
        for key, label in FIELD_LABELS.items()
        if key in ENCOUNTER_FIELDS
    )
    for feature in load_assets()["features"]:
        info = get_label(feature)
        suffix = f"（{info['unit']}）" if info.get("unit") else ""
        options.append({
            "value": feature,
            "label": f"{info['label']}{suffix}",
            "group": "模型指标",
        })
    return options


def _canonical_values(raw_values: dict[str, str], mapping: dict[str, str]) -> dict[str, str]:
    canonical: dict[str, str] = {}
    for header, value in raw_values.items():
        target = mapping.get(header, IGNORE)
        if target != IGNORE:
            canonical[target] = _cell_text(value)
    return canonical


def _normalise_row(
    canonical: dict[str, str], index: int, user: dict[str, Any],
    feature_names: set[str], conn: Any,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    mrn = canonical.get("mrn", "").strip()
    name = canonical.get("name", "").strip()
    case_ref = canonical.get("case_ref", "").strip()
    if not mrn:
        errors.append("病历号不能为空")
    if not name:
        errors.append("姓名不能为空")
    if not case_ref:
        errors.append("就诊编号不能为空")

    try:
        sex = _normalise_sex(canonical.get("sex") or "未知")
    except ValueError as exc:
        errors.append(str(exc))
        sex = "未知"

    birth_date = None
    birth_year = None
    raw_birth_date = (canonical.get("birth_date") or "").strip()
    raw_birth_year = (canonical.get("birth_year") or "").strip()
    if raw_birth_date:
        try:
            birth_date, birth_year = _birth_fields(raw_birth_date, None)
        except HTTPException as exc:
            errors.append(str(exc.detail))
        if raw_birth_year and birth_year is not None:
            try:
                stated_year = int(float(raw_birth_year))
                if stated_year != birth_year:
                    warnings.append(f"出生年份 {stated_year} 与出生日期不一致，以出生日期为准")
            except ValueError:
                warnings.append("出生年份无法识别，已忽略")
    elif raw_birth_year:
        try:
            birth_year = int(float(canonical["birth_year"]))
            if not 1900 <= birth_year <= date.today().year:
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
                errors.append("发生时间格式无效，建议 YYYY-MM-DD HH:MM 或 Excel 日期")

    feature_values = {
        key: value for key, value in canonical.items()
        if key in feature_names and value not in ("", "-", "NA", "N/A", "—", "null")
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
    resolved_owner = None
    if mrn:
        existing = conn.execute(
            "SELECT * FROM patients WHERE mrn=? COLLATE NOCASE AND active=1", (mrn,)
        ).fetchone()
        if existing:
            patient_exists = True
            patient_id = existing["id"]
            stored_birth = existing["birth_date"] if "birth_date" in existing.keys() else None
            if birth_date and stored_birth and stored_birth != birth_date:
                warnings.append(f"档案已有出生日期 {stored_birth}，本次导入不覆盖")
            elif birth_date and not stored_birth:
                warnings.append("将把出生日期补进已有档案")
            elif (
                not birth_date and birth_year and not stored_birth
                and existing["birth_year"] and existing["birth_year"] != birth_year
            ):
                warnings.append(f"档案已有出生年 {existing['birth_year']}，本次导入不覆盖")
            elif not birth_date and birth_year and not stored_birth and not existing["birth_year"]:
                warnings.append("将把出生年补进已有档案")
            if existing["name"] != name:
                errors.append("病历号已存在但姓名不一致，不能挂到该档案")
            access = _access_map(conn, user, existing["id"])
            if not access["view"]:
                errors.append("该病历号对应的患者档案不在当前账号授权范围内")
            elif not access["edit"]:
                errors.append("当前账号对该患者只有只读权限，不能导入就诊")
        else:
            owner_ref = canonical.get("owner_id", "").strip()
            if user["role"] == "doctor":
                if owner_ref and owner_ref not in {user["id"], user["username"]}:
                    errors.append("医生只能把新患者建在自己名下")
                elif not owner_ref:
                    owner_ref = user["id"]
            if not owner_ref:
                errors.append("管理员导入新患者时必须填写负责人ID")
            else:
                doctor = conn.execute(
                    """SELECT id,display_name FROM users
                       WHERE role='doctor' AND active=1
                         AND (username=? COLLATE NOCASE OR id=?)""",
                    (owner_ref, owner_ref),
                ).fetchone()
                if not doctor:
                    errors.append("负责人必须是有效医生账号")
                elif user["role"] != "doctor" and doctor["id"] == user["id"]:
                    errors.append("负责人应填写医生账号，不能填写管理员本人")
                else:
                    resolved_owner = doctor["id"]
        if case_ref and existing:
            duplicate = conn.execute(
                "SELECT 1 FROM encounters WHERE patient_id=? AND case_ref=?",
                (existing["id"], case_ref),
            ).fetchone()
            if duplicate:
                errors.append("该患者已存在相同就诊编号")

    return {
        "index": index,
        "mrn": mrn,
        "name": name,
        "sex": sex,
        "birth_year": birth_year,
        "birth_date": birth_date,
        "certificate_last4": canonical.get("certificate_last4") or None,
        "phone_last4": canonical.get("phone_last4") or None,
        "owner_id": resolved_owner or canonical.get("owner_id") or None,
        "case_ref": case_ref,
        "occurred_at": occurred_at,
        "surgery_type": canonical.get("surgery_type") or None,
        "diagnosis": canonical.get("diagnosis", ""),
        "orders": canonical.get("orders", ""),
        "values": stored,
        "patient_id": patient_id,
        "patient_exists": patient_exists,
        "errors": errors,
        "warnings": warnings,
    }


def _mark_file_duplicates(rows: list[dict[str, Any]]) -> None:
    """Highlight duplicate MRN/case pairs before anything is written."""
    by_mrn: dict[str, dict[str, Any]] = {}
    by_pair: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        mrn = str(row.get("mrn") or "").strip().upper()
        case_ref = str(row.get("case_ref") or "").strip()
        if not mrn:
            continue
        pair = (mrn, case_ref)
        if pair in by_pair and case_ref:
            previous = by_pair[pair]
            message = "文件内存在相同的病历号与就诊编号"
            if message not in row["errors"]:
                row["errors"].append(message)
            if message not in previous["errors"]:
                previous["errors"].append(message)
        elif case_ref:
            by_pair[pair] = row
        previous_mrn = by_mrn.get(mrn)
        if previous_mrn and previous_mrn["name"] != row["name"]:
            message = "同一文件内病历号重复且姓名不一致"
            if message not in row["errors"]:
                row["errors"].append(message)
            if message not in previous_mrn["errors"]:
                previous_mrn["errors"].append(message)
        elif not previous_mrn:
            by_mrn[mrn] = row
        elif previous_mrn and previous_mrn["name"] == row["name"] and case_ref:
            warning = "同一患者多行，将按多就诊导入"
            if warning not in row["warnings"]:
                row["warnings"].append(warning)


def _summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    valid_rows = [row for row in rows if not row["errors"]]
    new_mrns = {
        str(row["mrn"]).strip().upper() for row in valid_rows
        if not row["patient_exists"] and row["mrn"]
    }
    return {
        "total": len(rows),
        "valid": len(valid_rows),
        "invalid": len(rows) - len(valid_rows),
        "new_patients": len(new_mrns),
        "existing_patients": sum(1 for row in valid_rows if row["patient_exists"]),
    }


def _template_headers() -> list[str]:
    return [
        "病历号", "姓名", "性别", "出生日期", "证件号末四位", "手机号末四位",
        "就诊编号", "发生时间", "手术类型", "诊断", "医嘱", "负责人ID",
    ] + list(load_assets()["features"])


def _template_sample() -> list[str]:
    return [
        "MRN-DEMO-001", "示例患者", "男", "1960-03-15", "1234", "5678",
        "CASE-20261122-001", "2026-11-20 09:00", "冠脉搭桥术",
        "冠心病，拟行冠脉搭桥术", "术后监测肌酐与尿量", "",
    ] + [""] * len(load_assets()["features"])


@router.get("/template.csv", response_class=PlainTextResponse)
def template_csv(request: Request):
    _user(request)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(_template_headers())
    writer.writerow(_template_sample())
    return PlainTextResponse(
        "\ufeff" + buffer.getvalue(), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="AKI_import_template.csv"'},
    )


def _build_template_workbook() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "导入模板"
    headers = _template_headers()
    sheet.append(headers)
    sheet.append(_template_sample())
    sheet.freeze_panes = "A2"
    widths = [18, 14, 8, 10, 14, 14, 20, 20, 16, 28, 28, 18] + [15] * (len(headers) - 12)
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


@router.get("/template.xlsx")
def template_xlsx(request: Request):
    _user(request)
    return Response(
        content=_build_template_workbook(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="AKI_import_template.xlsx"'},
    )


async def _receive_file(request: Request, file: UploadFile) -> tuple[bytes, str, str]:
    user = _user(request)
    db.ensure_initialized()
    raw = await file.read()
    if len(raw) > MAX_BYTES:
        raise _err("文件超过 5 MB 限制", 413)
    if not raw:
        raise _err("文件为空")
    filename = (file.filename or "import.csv")[:200]
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if suffix == "xls":
        raise _err("旧版 .xls 暂不支持，请在 Excel 中另存为 .xlsx 后上传")
    if suffix not in {"xlsx", "xlsm", "csv"}:
        raise _err("仅支持 .xlsx、.xlsm 或 .csv 文件")
    return raw, filename, suffix


@router.post("/preview")
async def preview_import(
    request: Request,
    file: UploadFile = File(...),
    sheet_name: str = Form(default=""),
    mapping: str = Form(default=""),
):
    raw, filename, suffix = await _receive_file(request, file)
    user = _user(request)
    file_type = "xlsx" if suffix in {"xlsx", "xlsm"} else "csv"
    sheet_names: list[str] = []
    selected_sheet = ""
    if file_type == "xlsx":
        headers, sheet_names, source_rows, selected_sheet = _read_xlsx(raw, sheet_name)
    else:
        headers, source_rows, _ = _read_csv(raw)
        if len(source_rows) > MAX_ROWS:
            raise _err(f"单批最多 {MAX_ROWS} 行，当前 {len(source_rows)} 行", 413)

    if file_type == "xlsx" and not sheet_name and len(sheet_names) > 1:
        return {
            "requires_sheet": True,
            "filename": filename,
            "file_type": file_type,
            "sheet_names": sheet_names,
            "headers": [],
            "rows": [],
            "summary": {"total": 0, "valid": 0, "invalid": 0, "new_patients": 0, "existing_patients": 0},
        }

    if len(source_rows) > MAX_ROWS:
        raise _err(f"单批最多 {MAX_ROWS} 行，当前 {len(source_rows)} 行", 413)
    if not headers:
        raise _err("文件缺少表头")
    duplicates = sorted({header for header in headers if headers.count(header) > 1})
    if duplicates:
        raise _err("表头存在重复列：" + "、".join(duplicates[:6]))
    if any(not header for header in headers):
        raise _err("表头存在空列，请先补全列名")

    feature_names = set(load_assets()["features"])
    columns, header_errors = _resolve_mapping(headers, mapping)
    header_warnings: list[str] = []
    ignored_headers = [header for header, target in columns.items() if target == IGNORE]
    if ignored_headers:
        header_warnings.append("未映射列将忽略：" + "、".join(ignored_headers[:8]))

    with db.reader() as conn:
        rows = []
        for index, values in source_rows:
            canonical = _canonical_values(dict(zip(headers, values)), columns)
            rows.append(_normalise_row(canonical, index, user, feature_names, conn))
    _mark_file_duplicates(rows)
    summary = _summary(rows)

    file_hash = hashlib.sha256(raw).hexdigest()
    with db.reader() as conn:
        completed = conn.execute(
            "SELECT id FROM import_batches WHERE file_hash=? AND status='completed' ORDER BY created_at DESC LIMIT 1",
            (file_hash,),
        ).fetchone()
    if completed:
        raise _err(f"该文件已导入过（批次 {completed['id']}），不能重复提交", 409)

    samples: dict[str, str] = {}
    for header in headers:
        samples[header] = ""
    for _, values in source_rows[:3]:
        for header, value in zip(headers, values):
            if value and not samples.get(header):
                samples[header] = value

    batch_id = new_id("IMP")
    preview_payload = {
        "headers": headers,
        "columns": columns,
        "rows": rows,
        "raw_rows": [
            {"index": index, "values": dict(zip(headers, values))}
            for index, values in source_rows
        ],
        "header_errors": header_errors,
    }
    with db.transaction(immediate=True) as conn:
        conn.execute(
            """INSERT INTO import_batches
               (id,filename,created_by,total,imported,failed,status,detail_json,
                preview_json,mapping_json,file_hash,sheet_name,updated_at,created_at)
               VALUES(?,?,?,?,0,?,'preview','{}',?,?,?,?,?,?)""",
            (
                batch_id, filename, user["id"], len(rows), summary["invalid"],
                json_dump(preview_payload), json_dump(columns), file_hash,
                selected_sheet, utc_now(), utc_now(),
            ),
        )
        record_audit(
            conn, actor_type="user", actor_id=user["id"], action="import_preview",
            entity_type="import_batch", entity_id=batch_id,
            detail={"filename": filename, "sheet_name": selected_sheet,
                    "total": len(rows), "valid": summary["valid"]},
            ip=request.client.host if request.client else None,
        )

    return {
        "requires_sheet": False,
        "batch_id": batch_id,
        "filename": filename,
        "file_type": file_type,
        "sheet_name": selected_sheet,
        "sheet_names": sheet_names,
        "headers": headers,
        "columns": columns,
        "samples": samples,
        "field_options": _field_options(),
        "ignored_headers": ignored_headers,
        "header_errors": header_errors,
        "header_warnings": header_warnings,
        "rows": rows,
        "summary": summary,
        "file_hash": file_hash,
    }


def _insert_row(
    conn: Any, row: dict[str, Any], user: dict[str, Any], request: Request,
    filename: str, batch_id: str,
) -> tuple[str, str]:
    """Validate and insert one normalized row inside the caller's transaction."""
    index = row.get("index", 1)
    mrn = str(row.get("mrn") or "").strip().upper()
    name = str(row.get("name") or "").strip()
    case_ref = str(row.get("case_ref") or "").strip()
    if not mrn or not name or not case_ref:
        raise ValueError("病历号、姓名和就诊编号不能为空")
    try:
        occurred = _parse_dt(row.get("occurred_at") or "")
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
    feature_names = set(load_assets()["features"])
    unknown = sorted(set(values) - feature_names)
    if unknown:
        raise ValueError(f"包含未知指标：{', '.join(unknown[:5])}")
    stored, _, invalid = _normalise_values(values, allow_incomplete=False)
    if invalid:
        raise ValueError("指标超出合理范围：" + "、".join(invalid))

    existing = conn.execute(
        "SELECT * FROM patients WHERE mrn=? COLLATE NOCASE AND active=1", (mrn,)
    ).fetchone()
    if existing:
        if existing["name"] != name:
            raise ValueError("病历号已存在但姓名不一致，该行未导入")
        patient_id = existing["id"]
        if not _access_map(conn, user, patient_id)["edit"]:
            raise ValueError("无权向该患者导入就诊")
        incoming_date = row.get("birth_date") or None
        incoming_year = row.get("birth_year")
        stored_date = existing["birth_date"] if "birth_date" in existing.keys() else None
        if incoming_date and not stored_date:
            conn.execute(
                "UPDATE patients SET birth_date=?,birth_year=?,updated_at=? WHERE id=?",
                (incoming_date, incoming_year, utc_now(), patient_id),
            )
        elif incoming_year and not stored_date and not existing["birth_year"]:
            conn.execute(
                "UPDATE patients SET birth_year=?,updated_at=? WHERE id=?",
                (incoming_year, utc_now(), patient_id),
            )
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
               (id,mrn,name,sex,birth_year,birth_date,certificate_last4,phone_last4,
                owner_id,active,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,1,?,?)""",
            (
                patient_id, mrn, name, sex,
                row.get("birth_year"), row.get("birth_date"), row.get("certificate_last4") or None,
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
            user["id"], user["id"], utc_now(), utc_now(),
        ),
    )
    record_audit(
        conn, actor_type="user", actor_id=user["id"],
        action="import_row_create", entity_type="encounter",
        entity_id=encounter_id,
        detail={"patient_id": patient_id, "mrn": mrn, "case_ref": case_ref,
                "filename": filename, "row": index, "batch_id": batch_id},
        ip=request.client.host if request.client else None,
    )
    return patient_id, encounter_id


@router.post("/commit")
def commit_import(req: ImportCommitRequest, request: Request):
    user = _user(request)
    db.ensure_initialized()
    if not req.batch_id:
        raise _err("请先预览并提交批次号", 400)
    return _commit_preview_batch(req.batch_id, user, request)


def _commit_preview_batch(batch_id: str, user: dict[str, Any], request: Request):
    with db.reader() as conn:
        batch = conn.execute("SELECT * FROM import_batches WHERE id=?", (batch_id,)).fetchone()
    if batch is None:
        raise _err("导入批次不存在", 404)
    if batch["created_by"] != user["id"] and user["role"] != "admin":
        raise _err("无权提交该导入批次", 403)
    if batch["status"] != "preview":
        raise _err("该批次已提交或已失效，不能重复提交", 409)
    preview = json.loads(batch["preview_json"] or "{}")
    if preview.get("header_errors"):
        raise _err("表头/列映射存在错误，不能提交：" + "；".join(preview["header_errors"][:3]))
    rows = preview.get("rows") or []
    if not rows:
        raise _err("没有可导入的数据")

    results: list[dict[str, Any]] = []
    imported = 0
    failed = 0
    with db.transaction(immediate=True) as conn:
        fresh = conn.execute(
            "SELECT id,status,file_hash,created_by FROM import_batches WHERE id=?", (batch_id,)
        ).fetchone()
        if fresh is None:
            raise _err("导入批次不存在", 404)
        if fresh["created_by"] != user["id"] and user["role"] != "admin":
            raise _err("无权提交该导入批次", 403)
        if fresh["status"] != "preview":
            raise _err("该批次已提交或已失效，不能重复提交", 409)
        duplicate = conn.execute(
            """SELECT id FROM import_batches WHERE file_hash=? AND status='completed'
               AND id<>? ORDER BY created_at DESC LIMIT 1""",
            (fresh["file_hash"], batch_id),
        ).fetchone()
        if duplicate:
            raise _err(f"该文件已导入过（批次 {duplicate['id']}），不能重复提交", 409)

        for index, row in enumerate(rows):
            if row.get("errors"):
                failed += 1
                results.append({
                    "index": row.get("index", index + 1), "ok": False,
                    "error": "预览校验未通过：" + "；".join(row["errors"][:3]),
                })
                continue
            savepoint = f"sp_{index}"
            conn.execute(f"SAVEPOINT {savepoint}")
            try:
                patient_id, encounter_id = _insert_row(
                    conn, row, user, request, batch["filename"], batch_id,
                )
                conn.execute(f"RELEASE SAVEPOINT {savepoint}")
                imported += 1
                results.append({
                    "index": row.get("index", index + 1), "ok": True,
                    "patient_id": patient_id, "encounter_id": encounter_id,
                })
            except (ValueError, HTTPException) as exc:
                conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                conn.execute(f"RELEASE SAVEPOINT {savepoint}")
                failed += 1
                message = exc.detail if isinstance(exc, HTTPException) else str(exc)
                results.append({
                    "index": row.get("index", index + 1), "ok": False, "error": str(message),
                })
            except Exception as exc:
                conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                conn.execute(f"RELEASE SAVEPOINT {savepoint}")
                failed += 1
                message = str(exc)
                if "UNIQUE constraint failed: encounters" in message:
                    message = "同一患者下就诊编号已存在，该行未导入"
                elif "UNIQUE constraint failed: patients.mrn" in message:
                    message = "病历号已存在，该行未导入"
                results.append({
                    "index": row.get("index", index + 1), "ok": False,
                    "error": f"数据库写入失败：{message}",
                })

        conn.execute(
            """UPDATE import_batches
               SET status='completed', imported=?, failed=?, detail_json=?, updated_at=?
               WHERE id=? AND status='preview'""",
            (
                imported, failed,
                json_dump({"failures": [r for r in results if not r["ok"]][:100]}),
                utc_now(), batch_id,
            ),
        )
        record_audit(
            conn, actor_type="user", actor_id=user["id"], action="import_commit",
            entity_type="import_batch", entity_id=batch_id,
            detail={"filename": batch["filename"], "total": len(rows),
                    "imported": imported, "failed": failed},
            ip=request.client.host if request.client else None,
        )
    return {
        "batch_id": batch_id, "total": len(rows), "imported": imported,
        "failed": failed, "results": results,
    }


@router.get("/{batch_id}/errors.xlsx")
def export_errors(batch_id: str, request: Request):
    user = _user(request)
    with db.reader() as conn:
        batch = conn.execute("SELECT * FROM import_batches WHERE id=?", (batch_id,)).fetchone()
    if batch is None:
        raise _err("导入批次不存在", 404)
    if batch["created_by"] != user["id"] and user["role"] != "admin":
        raise _err("无权导出该批次", 403)
    preview = json.loads(batch["preview_json"] or "{}")
    errors = [row for row in preview.get("rows") or [] if row.get("errors")]
    if not errors:
        raise _err("该批次没有错误行")
    headers = preview.get("headers") or []
    raw_by_index = {
        item.get("index"): item.get("values") or {}
        for item in preview.get("raw_rows") or []
    }
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "错误行"
    sheet.append(["行号", "错误", "提示"] + headers)
    for row in errors:
        raw = raw_by_index.get(row.get("index"), {})
        sheet.append([
            row.get("index"),
            "；".join(row.get("errors") or []),
            "；".join(row.get("warnings") or []),
        ] + [raw.get(header, "") for header in headers])
    sheet.freeze_panes = "A2"
    for index, width in enumerate([8, 48, 30] + [18] * len(headers), start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    buffer = io.BytesIO()
    workbook.save(buffer)
    return Response(
        content=buffer.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="AKI_import_errors_{batch_id}.xlsx"'
        },
    )
