#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""数据清洗：按规则修复脏数据，输出 xlsx（原始 + 清洗后 + 日志）。

默认动作：去重、strip、全角转半角、数值格式化、日期归一、空值标记。
**绝不**：删非重复行、填缺失值、改数值大小、合并列。

依赖: openpyxl（输出 xlsx 必需）。

用法:
  python3 clean_data.py --input 数据.csv --out 清洗后.xlsx
  python3 clean_data.py --input 数据.csv --out 清洗后.xlsx --keep-duplicates
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

FULLWIDTH = {chr(0xFF01 + i): chr(0x21 + i) for i in range(94)}
FW_SPACE = "\u3000"
NUM_CLEAN = re.compile(r"[¥￥$,\s]|元|万元|%")
DATE_PATS = [
    (re.compile(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$"), "ymd"),
    (re.compile(r"^(\d{4})年(\d{1,2})月(\d{1,2})日$"), "ymd"),
    (re.compile(r"^(\d{4})(\d{2})(\d{2})$"), "ymd"),
]


def to_half(s: str) -> str:
    s = s.replace(FW_SPACE, " ")
    return "".join(FULLWIDTH.get(ch, ch) for ch in s)


def norm_date(v: str) -> str | None:
    for pat, _ in DATE_PATS:
        m = pat.match(v)
        if m:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if 1900 < y < 2200 and 1 <= mo <= 12 and 1 <= d <= 31:
                return f"{y:04d}-{mo:02d}-{d:02d}"
    return None


def try_number(v: str) -> float | None:
    s = NUM_CLEAN.sub("", v)
    if not s or s in ("-", "+"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def read_table(path: Path) -> tuple[list[str], list[list[str]]]:
    ext = path.suffix.lower()
    if ext in (".csv", ".tsv", ".txt"):
        delim = "\t" if ext == ".tsv" else ","
        for enc in ("utf-8-sig", "utf-8", "gbk", "latin-1"):
            try:
                with path.open(encoding=enc, newline="") as f:
                    rows = list(csv.reader(f, delimiter=delim))
                break
            except UnicodeDecodeError:
                continue
        else:
            raise SystemExit("[FATAL] 无法解码 CSV")
        if not rows:
            raise SystemExit("[FATAL] 文件为空")
        return rows[0], rows[1:]

    if ext in (".xlsx", ".xlsm"):
        from openpyxl import load_workbook  # type: ignore
        wb = load_workbook(str(path), read_only=True, data_only=True)
        ws = wb[wb.sheetnames[0]]
        rows = [[("" if c is None else str(c)) for c in r]
                for r in ws.iter_rows(values_only=True)]
        wb.close()
        return rows[0], rows[1:]

    raise SystemExit(f"[FATAL] 不支持的格式: {ext}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", default="清洗后.xlsx")
    ap.add_argument("--log", default="")
    ap.add_argument("--keep-duplicates", action="store_true")
    ap.add_argument("--no-number", action="store_true", help="不做数值格式化")
    ap.add_argument("--no-date", action="store_true", help="不做日期归一")
    args = ap.parse_args()

    src = Path(args.input)
    if not src.exists():
        print(f"[FATAL] 文件不存在: {src}")
        return 2

    header, rows = read_table(src)
    ncol = len(header)
    rows = [r + [""] * (ncol - len(r)) for r in rows]
    orig_n = len(rows)

    log: list[tuple[str, str, int, str]] = []  # (动作, 列, 影响行, 说明)

    # 1) 全角转半角 + strip
    n_fw = n_strip = 0
    for r in rows:
        for i, v in enumerate(r):
            s0 = str(v)
            s = to_half(s0)
            if s != s0:
                n_fw += 1
            if s != s.strip():
                n_strip += 1
            r[i] = s.strip()
    if n_fw:
        log.append(("全角转半角", "全部", n_fw, "数字/字母全角字符"))
    if n_strip:
        log.append(("去首尾空格", "全部", n_strip, "strip"))

    # 2) 去重
    dup_removed = 0
    if not args.keep_duplicates:
        seen = set()
        kept = []
        for r in rows:
            k = tuple(r)
            if k in seen:
                dup_removed += 1
                continue
            seen.add(k)
            kept.append(r)
        rows = kept
        if dup_removed:
            log.append(("去重", "全部", dup_removed, "完全相同的行，保留首次出现"))

    # 3) 数值格式化（只在整列大多数是数字时生效，避免误改编号类文本）
    if not args.no_number:
        for ci in range(ncol):
            col = [r[ci] for r in rows]
            nonblank = [v for v in col if v]
            if not nonblank:
                continue
            nums = [try_number(v) for v in nonblank]
            ok = sum(1 for n in nums if n is not None)
            if ok / len(nonblank) < 0.85:
                continue
            changed = 0
            for r in rows:
                v = r[ci]
                if not v:
                    continue
                n = try_number(v)
                if n is None:
                    continue
                newv = f"{n:.2f}" if abs(n - round(n)) > 1e-9 else str(int(round(n)))
                if newv != v and NUM_CLEAN.search(v):
                    r[ci] = newv
                    changed += 1
            if changed:
                log.append(("数值格式化", header[ci] or f"列{ci+1}", changed,
                            "去除 ¥/千分位/单位，转为纯数字"))

    # 4) 日期归一
    if not args.no_date:
        for ci in range(ncol):
            col = [r[ci] for r in rows]
            nonblank = [v for v in col if v]
            if not nonblank:
                continue
            converted = 0
            for r in rows:
                v = r[ci]
                if not v:
                    continue
                nd = norm_date(v)
                if nd and nd != v:
                    r[ci] = nd
                    converted += 1
                elif nd:
                    r[ci] = nd
            hits = sum(1 for v in nonblank if norm_date(v))
            if hits / len(nonblank) > 0.8 and converted:
                log.append(("日期归一", header[ci] or f"列{ci+1}", converted,
                            "统一为 YYYY-MM-DD"))

    # 5) 空值统计（只标记不填充）
    blanks = sum(1 for r in rows for v in r if not v)

    # ---- 输出 xlsx ----
    out = Path(args.out)
    try:
        from openpyxl import Workbook  # type: ignore
        from openpyxl.styles import Alignment, Font, PatternFill
    except ImportError:
        print("[FATAL] 输出 xlsx 需要 openpyxl：pip install openpyxl")
        return 1

    wb = Workbook()
    ws1 = wb.active
    ws1.title = "清洗后"
    ws1.append(header)
    for r in rows:
        ws1.append(r)
    ws2 = wb.create_sheet("原始数据")
    ws2.append(header)
    _h2, raw_rows = read_table(src)
    for r in raw_rows:
        ws2.append(r + [""] * (ncol - len(r)))

    head_fill = PatternFill("solid", fgColor="F2F3F5")
    for ws in (ws1, ws2):
        for c in ws[1]:
            c.font = Font(bold=True)
            c.fill = head_fill
            c.alignment = Alignment(horizontal="center")
        ws.freeze_panes = "A2"
    wb.save(str(out))

    # ---- 日志 ----
    lines = [
        f"# 清洗日志",
        "",
        f"- 原始文件：{src.name}（{orig_n} 行 × {ncol} 列）",
        f"- 输出文件：{out.name}（{len(rows)} 行 × {ncol} 列）",
        "",
        "| # | 操作 | 列 | 影响行数 | 说明 |",
        "|---|---|---|---|---|",
    ]
    for i, (act, col, n, note) in enumerate(log, 1):
        lines.append(f"| {i} | {act} | {col} | {n} | {note} |")
    if not log:
        lines.append("| — | 无需清洗 | — | 0 | 数据本来就干净 |")
    lines += [
        "",
        "## 未做的操作（需你确认后再执行）",
        "",
        "- **缺失值填充**：未填充。空值共 "
        f"{blanks} 处，填充方式（均值/中位数/固定值/删除）需要业务判断。",
        "- **异常值处理**：未删除任何非重复行。异常值请人工确认是录入错误还是真实数据。",
        "- **列合并/拆分**：未改动表结构。",
        "",
        "## 请核对",
        "",
        "1. 去重是否误删了「看起来一样但实际不同」的记录（如同日同额的两笔订单）",
        "2. 数值格式化是否把编号类字段（如订单号 0012345）变成了数字",
        "3. 日期归一是否把非日期列误判为日期",
    ]
    logtext = "\n".join(lines)
    logpath = Path(args.log) if args.log else out.with_suffix(".log.md")
    logpath.write_text(logtext, encoding="utf-8")

    print(f"[OK] 清洗完成")
    print(f"     原始 {orig_n} 行 → 清洗后 {len(rows)} 行（去重 {dup_removed}）")
    print(f"     输出：{out}")
    print(f"     日志：{logpath}")
    for act, col, n, note in log:
        print(f"       · {act}｜{col}｜{n} 行｜{note}")
    if not log:
        print("       · 未发现需要清洗的问题")
    return 0


if __name__ == "__main__":
    sys.exit(main())
