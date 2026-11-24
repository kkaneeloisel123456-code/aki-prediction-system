# -*- coding: utf-8 -*-
"""Generate deterministic Phase 3 import fixtures.

Run from the repository root:
    .venv/Scripts/python.exe tests/fixtures/build_phase3_fixtures.py
"""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from openpyxl import Workbook

HERE = Path(__file__).resolve().parent


def excel_serial(value: date) -> int:
    return (value - date(1899, 12, 30)).days


def main() -> None:
    gbk_rows = [
        ["病历号", "姓名", "性别", "出生年份", "就诊编号", "发生时间", "负责人ID", "术前Scr", "术前eGFR", "备注"],
        ["GBK-001", "张建国", "男", "1960", "GBK-CASE-001", "2026-11-20 09:00", "doctor1", "88", "92", "GBK 编码样本"],
        ["GBK-002", "李秀兰", "女", "1958", "GBK-CASE-002", "2026/11/21 10:30", "doctor1", "105", "78", "第二行"],
    ]
    with (HERE / "phase3_gbk.csv").open("w", newline="", encoding="gb18030") as handle:
        csv.writer(handle).writerows(gbk_rows)

    workbook = Workbook()
    valid = workbook.active
    valid.title = "有效数据"
    valid.append(["病历编号", "患者姓名", "性别", "出生年份", "就诊编号", "发生时间", "负责人ID", "术前肌酐", "术前 eGFR"])
    valid.append(["MAP-001", "映射患者", "男", 1960, "MAP-CASE-001", excel_serial(date(2026, 11, 20)), "doctor1", 88, 92])
    valid.append(["MAP-002", "映射患者二", "女", 1958, "MAP-CASE-002", excel_serial(date(2026, 11, 21)), "doctor1", 105, 78])

    errors = workbook.create_sheet("错误数据")
    errors.append(["病历号", "姓名", "性别", "出生年份", "证件号末四位", "手机号末四位", "就诊编号", "发生时间", "负责人ID", "术中晶体液量"])
    rows = [
        ["DUP-001", "合并患者", "男", 1970, "1234", "5678", "DUP-CASE-1", excel_serial(date(2026, 11, 20)), "doctor1", 9.5e3],
        [None, None, None, None, None, None, "DUP-CASE-2", excel_serial(date(2026, 11, 21)), "doctor1", 5000],
        ["DUP-001", "姓名不符", "女", 1972, "9999", "0000", "DUP-CASE-3", "2026-11-22 10:00", "doctor1", 4000],
        ["BAD-SEX-1", "性别错误", "X", 1975, "1111", "2222", "SEX-CASE-1", "2026-11-21 09:30", "doctor1", 3000],
        ["DUP-001", "合并患者", "男", 1970, "1234", "5678", "DUP-CASE-1", "2026-11-20 09:00", "doctor1", 6000],
    ]
    for row in rows:
        errors.append(row)
    # Merge the patient identity cells across the first two data rows.
    for column in range(1, 6):
        errors.merge_cells(start_row=2, start_column=column, end_row=3, end_column=column)
    errors["J2"].number_format = "0.00E+00"

    workbook.save(HERE / "phase3_two_sheets.xlsx")


if __name__ == "__main__":
    main()
