#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量提取发票/收据字段（本地处理，不上传任何数据）。

依赖: pypdf（仅 PDF 需要，缺失时自动降级）
用法:
  python3 extract_invoices.py --input 票据目录 --out records.json
  python3 extract_invoices.py --input a.pdf b.jpg --out records.json
  python3 extract_invoices.py --input 票据目录 --out records.json --manual-template 补录.csv
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PDF_EXT = {".pdf"}
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".heic"}

# ---------- 正则 ----------
RE_INVOICE_NO = re.compile(
    r"(?:发票号码|票\s*号|No\.?)\s*[:：]?\s*(\d{8,24})", re.I)
RE_INVOICE_CODE = re.compile(
    r"(?:发票代码|票\s*代码)\s*[:：]?\s*(\d{10,14})", re.I)
RE_DATE_CN = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
RE_DATE_ISO = re.compile(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})")
RE_AMOUNT_LOWER = re.compile(
    r"(?:小写|价税合计|合\s*计|金额合计|合计金额)[^\d¥￥]{0,24}[¥￥]?\s*([\d,]+\.\d{2})")
RE_AMOUNT_ANY = re.compile(r"[¥￥]\s*([\d,]+\.\d{2})")
RE_TAX = re.compile(r"(?:税\s*额|税额合计)[^\d¥￥]{0,20}[¥￥]?\s*([\d,]+\.\d{2})")
RE_SELLER = re.compile(
    r"(?:销售方|销\s*方|开票方)(?:名称)?\s*[:：]?\s*([^\s:：,，\n]{4,40})")
RE_BUYER = re.compile(
    r"(?:购买方|购\s*方|付款方)(?:名称)?\s*[:：]?\s*([^\s:：,，\n]{4,40})")
RE_TAX_ID = re.compile(
    r"(?:纳税人识别号|统一社会信用代码|税\s*号)\s*[:：]?\s*([0-9A-Z]{15,20})", re.I)


def norm_date(y: str, m: str, d: str) -> str | None:
    try:
        yi, mi, di = int(y), int(m), int(d)
        if not (1990 <= yi <= 2100 and 1 <= mi <= 12 and 1 <= di <= 31):
            return None
        return f"{yi:04d}-{mi:02d}-{di:02d}"
    except ValueError:
        return None


def find_date(text: str) -> str | None:
    m = RE_DATE_CN.search(text)
    if m:
        return norm_date(*m.groups())
    m = RE_DATE_ISO.search(text)
    if m:
        return norm_date(*m.groups())
    return None


def to_float(s: str) -> float | None:
    try:
        return round(float(s.replace(",", "")), 2)
    except ValueError:
        return None


def find_amount(text: str, warnings: list[str]) -> float | None:
    m = RE_AMOUNT_LOWER.search(text)
    if m:
        return to_float(m.group(1))
    cands = RE_AMOUNT_ANY.findall(text)
    vals = [to_float(c) for c in cands]
    vals = [v for v in vals if v is not None]
    if vals:
        warnings.append(f"未找到『价税合计』标注，取最大候选金额；全部候选={vals}")
        return max(vals)
    return None


def detect_type(text: str) -> str:
    checks = [
        ("增值税电子专用发票", "电子专票"),
        ("增值税电子普通发票", "电子普票"),
        ("电子发票（增值税专用发票）", "全电专票"),
        ("电子发票（普通发票）", "全电普票"),
        ("增值税专用发票", "专票"),
        ("增值税普通发票", "普票"),
        ("航空运输电子客票行程单", "机票行程单"),
        ("铁路电子客票", "火车票"),
        ("出租汽车", "出租车票"),
        ("定额发票", "定额发票"),
        ("收据", "收据"),
    ]
    for kw, label in checks:
        if kw in text:
            return label
    return "未识别"


def detect_category(text: str) -> str:
    rules = [
        (("铁路", "航空", "出租车", "网约车", "地铁", "客运", "高速", "行程单"), "交通"),
        (("酒店", "宾馆", "民宿", "住宿", "旅馆"), "住宿"),
        (("餐饮", "餐厅", "食品", "咖啡", "茶", "酒楼", "饭店"), "餐饮"),
        (("办公", "文具", "打印", "耗材", "纸"), "办公"),
        (("加油", "停车", "过路", "石油", "石化", "充电"), "车辆"),
        (("电信", "移动", "联通", "通信", "话费"), "通讯"),
        (("会务", "展览", "培训", "会议"), "会务培训"),
    ]
    for kws, label in rules:
        if any(k in text for k in kws):
            return label
    return "其他"


def pdf_text(p: Path) -> str:
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError:
        return ""
    try:
        reader = PdfReader(str(p))
        chunks = []
        for page in reader.pages:
            chunks.append(page.extract_text() or "")
        return "\n".join(chunks)
    except Exception as exc:  # noqa: BLE001
        return f"__PDF_ERROR__:{exc}"


def extract_one(p: Path) -> dict:
    warnings: list[str] = []
    rec: dict = {
        "file": p.name,
        "path": str(p),
        "invoice_no": None,
        "invoice_code": None,
        "date": None,
        "amount": None,
        "tax": None,
        "seller": None,
        "buyer": None,
        "tax_id": None,
        "type": None,
        "category": None,
        "status": "有效",
        "warnings": warnings,
    }

    ext = p.suffix.lower()
    if ext in PDF_EXT:
        text = pdf_text(p)
        if text.startswith("__PDF_ERROR__"):
            warnings.append("PDF 解析失败：" + text.split(":", 1)[-1][:80])
            rec["status"] = "待人工补录"
            return rec
        if len(text.strip()) < 20:
            warnings.append("PDF 无文本层（疑似扫描件），需人工补录")
            rec["status"] = "待人工补录"
            return rec
    elif ext in IMG_EXT:
        warnings.append("图片票据：当前环境无 OCR，需按模板人工补录")
        rec["status"] = "待人工补录"
        return rec
    else:
        warnings.append(f"不支持的文件类型 {ext}")
        rec["status"] = "待人工补录"
        return rec

    text = re.sub(r"[ \t]+", " ", text)
    flat = re.sub(r"\s+", " ", text)

    m = RE_INVOICE_NO.search(flat)
    if m:
        rec["invoice_no"] = m.group(1)
    m = RE_INVOICE_CODE.search(flat)
    if m:
        rec["invoice_code"] = m.group(1)

    rec["date"] = find_date(flat)
    rec["amount"] = find_amount(flat, warnings)

    m = RE_TAX.search(flat)
    if m:
        rec["tax"] = to_float(m.group(1))

    m = RE_SELLER.search(flat)
    if m:
        rec["seller"] = m.group(1).strip()
    m = RE_BUYER.search(flat)
    if m:
        rec["buyer"] = m.group(1).strip()
    m = RE_TAX_ID.search(flat)
    if m:
        rec["tax_id"] = m.group(1)

    rec["type"] = detect_type(flat)
    rec["category"] = detect_category(flat)

    for field in ("invoice_no", "date", "amount"):
        if rec[field] in (None, ""):
            warnings.append(f"缺少必填字段 {field}")
    if rec["type"] == "未识别":
        warnings.append("票种未识别")
    if any("缺少必填字段" in w for w in warnings):
        rec["status"] = "待确认"

    return rec


def collect(inputs: list[str]) -> list[Path]:
    files: list[Path] = []
    for raw in inputs:
        p = Path(raw)
        if p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file() and f.suffix.lower() in (PDF_EXT | IMG_EXT):
                    if f.name.startswith(".") or f.name == ".DS_Store":
                        continue
                    files.append(f)
        elif p.is_file():
            files.append(p)
    return files


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", nargs="+", required=True, help="文件或目录（可多个）")
    ap.add_argument("--out", default="records.json", help="输出 JSON 路径")
    ap.add_argument("--manual-template", default="", help="导出人工补录 CSV 模板")
    args = ap.parse_args()

    files = collect(args.input)
    if not files:
        print("[FATAL] 未找到任何 PDF/图片票据")
        return 2

    print(f"[i] 发现 {len(files)} 个票据文件")

    records = [extract_one(f) for f in files]

    ok = [r for r in records if r["status"] == "有效"]
    uncertain = [r for r in records if r["status"] == "待确认"]
    manual = [r for r in records if r["status"] == "待人工补录"]

    out = {
        "generated": True,
        "total": len(records),
        "counts": {"有效": len(ok), "待确认": len(uncertain), "待人工补录": len(manual)},
        "records": records,
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n[OK] 已写出 {args.out}")
    print(f"     ✅ 有效 {len(ok)}　⚠️ 待确认 {len(uncertain)}　📝 待人工补录 {len(manual)}")
    total_amount = sum(r["amount"] or 0 for r in records)
    print(f"     💰 提取到金额合计 ¥{total_amount:,.2f}")

    for r in records:
        flag = {"有效": "✅", "待确认": "⚠️", "待人工补录": "📝"}[r["status"]]
        amt = f"¥{r['amount']:,.2f}" if r["amount"] is not None else "—"
        print(f"     {flag} {r['file'][:36]:<38} {r['invoice_no'] or '—':<22} "
              f"{r['date'] or '—':<12} {amt}")
        for w in r["warnings"]:
            print(f"        └ {w}")

    if args.manual_template and manual:
        lines = ["文件名,发票号码,开票日期,金额,税额,销售方,类别"]
        for r in manual:
            lines.append(f"{r['file']},,,,,,")
        Path(args.manual_template).write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"\n[OK] 人工补录模板已导出: {args.manual_template}（{len(manual)} 行）")

    return 0


if __name__ == "__main__":
    sys.exit(main())
