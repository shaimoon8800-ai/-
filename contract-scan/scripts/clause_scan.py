#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""合同高风险条款扫描（离线可用，无第三方依赖）。

按信号词定位可能对签约方不利的段落，供人工复核。
⚠️ 本脚本只做「定位」，不做法律判断，输出结果不能作为法律意见。

用法:
  python3 clause_scan.py --input 合同.txt --out 扫描结果.md
  python3 clause_scan.py --input 合同.txt --side 乙方
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# 风险信号词（按类型）——命中即提示人工复核
SIGNALS = {
    "无限责任": ["一切损失", "全部损失", "任何损失", "无限", "全部责任", "承担所有",
                 "赔偿全部", "不设上限", "全部费用"],
    "单方权利": ["单方", "自行决定", "无需通知", "无须通知", "有权随时", "有权变更",
                 "最终解释权", "自行调整", "单方面"],
    "自动续期": ["自动续期", "自动续约", "自动延长", "期满自动", "视为同意续"],
    "违约金不对等": ["违约金", "违约方应支付", "按合同总额", "双倍", "三倍"],
    "模糊标准": ["合理", "适当", "必要时", "由甲方确定", "由乙方确定",
                 "另行约定", "视情况", "酌情"],
    "权利让渡": ["不得主张", "放弃", "不可撤销", "不得异议", "不得抗辩",
                 "无权要求", "视为放弃"],
    "争议管辖": ["管辖", "仲裁", "诉讼", "所在地法院", "仲裁委员会"],
    "押金保证金": ["押金", "保证金", "订金", "定金", "不予退还", "不予返还"],
    "知识产权": ["知识产权", "著作权", "专利权", "商标", "归属", "无偿许可",
                 "独家", "排他"],
    "保密与竞业": ["保密", "竞业", "不得从事", "禁止从事", "同业竞争"],
    "解除与终止": ["解除合同", "终止合同", "提前终止", "解约", "退出"],
    "期限与交付": ["交付", "验收", "工期", "逾期", "顺延", "不可抗力"],
}

# 高风险组合：命中多个类型时优先提示
PRIORITY = ["无限责任", "单方权利", "权利让渡", "自动续期", "违约金不对等"]


def split_clauses(text: str) -> list[tuple[str, str]]:
    """把合同切成条款：优先按「第 X 条」切，否则按段落。"""
    text = text.replace("\r\n", "\n")
    parts = re.split(r"\n(?=\s*第\s*[一二三四五六七八九十百零\d]+\s*条)", text)
    out = []
    for i, p in enumerate(parts):
        p = p.strip()
        if not p:
            continue
        first = p.split("\n", 1)[0].strip()[:40]
        out.append((f"第 {i} 段 / {first}", p))
    if len(out) <= 1:
        paras = [p.strip() for p in text.split("\n\n") if p.strip()]
        out = [(f"段落 {i+1}", p) for i, p in enumerate(paras)]
    return out


def scan(clause: str) -> dict[str, list[str]]:
    hits: dict[str, list[str]] = {}
    for kind, words in SIGNALS.items():
        found = [w for w in words if w in clause]
        if found:
            hits[kind] = found
    return hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="合同文本文件")
    ap.add_argument("--out", default="", help="输出 markdown 报告")
    ap.add_argument("--side", default="", help="你的身份（甲方/乙方/承租方/出租方/劳动者）")
    ap.add_argument("--min-hits", type=int, default=1, help="至少命中几个信号才列出")
    args = ap.parse_args()

    p = Path(args.input)
    if not p.exists():
        print(f"[FATAL] 文件不存在: {p}")
        return 2

    text = None
    for enc in ("utf-8", "utf-8-sig", "gbk", "latin-1"):
        try:
            text = p.read_text(encoding=enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        print("[FATAL] 无法解码文件")
        return 2

    clauses = split_clauses(text)
    rows = []
    for label, body in clauses:
        hits = scan(body)
        if len(hits) < args.min_hits:
            continue
        kinds = list(hits)
        level = "🔴" if any(k in PRIORITY for k in kinds) else "🟡"
        rows.append({"label": label, "level": level, "kinds": kinds,
                     "hits": hits, "body": body})

    rows.sort(key=lambda r: (0 if r["level"] == "🔴" else 1, len(r["kinds"])), reverse=False)

    lines = [
        "# 合同高风险条款扫描结果", "",
        f"- 文件：{p.name}",
        f"- 识别到条款/段落：{len(clauses)} 段",
        f"- 命中风险信号：**{len(rows)}** 段",
    ]
    if args.side:
        lines.append(f"- 你的立场：**{args.side}**（风险判断需按立场解读）")
    lines += [
        "",
        "> ⚠️ **本结果只做条款定位，不构成法律意见。**",
        "> 信号词命中 ≠ 条款必然有问题（如「保密」条款本身是必要的）。",
        "> 请结合具体事实判断，重大事项请咨询执业律师。",
        "",
        "| # | 位置 | 级别 | 风险类型 | 命中信号 |",
        "|---|---|---|---|---|",
    ]
    for i, r in enumerate(rows, 1):
        lines.append(
            f"| {i} | {r['label']} | {r['level']} | {'、'.join(r['kinds'])} "
            f"| {'、'.join(sum(r['hits'].values(), [])[:5])} |")

    lines += ["", "## 条款原文摘录（供逐条复核）", ""]
    for i, r in enumerate(rows, 1):
        snippet = r["body"][:400].replace("\n", " ")
        lines.append(f"**{i}. {r['label']}** {r['level']}")
        lines.append("")
        lines.append(f"> {snippet}{'…' if len(r['body']) > 400 else ''}")
        lines.append("")
        lines.append(f"风险类型：{'、'.join(r['kinds'])}")
        lines.append("")

    lines += [
        "## 下一步",
        "",
        "1. 把 🔴 段落逐条翻译成人话（后果是什么、最坏损失多大）",
        "2. 整理成「咨询律师的问题清单」",
        "3. 对不确定的条款，回到原文核对完整语境（本表只截取了片断）",
    ]

    report = "\n".join(lines)
    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
        print(f"[OK] 扫描报告：{args.out}")
    print(report[:2500])
    print(f"\n[统计] {len(clauses)} 段中命中 {len(rows)} 段"
          f"（🔴 {sum(1 for r in rows if r['level']=='🔴')} / "
          f"🟡 {sum(1 for r in rows if r['level']=='🟡')}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
