#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""面试回答自评：检查回答是否包含「结论 / 证据 / 数据 / 反思」四要素（离线可用）。

用法:
  python3 mock_score.py --answer 我的回答.txt
  python3 mock_score.py --answer 回答.txt --question "讲一次你主导的项目"
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# 结论信号（先行表述 / 判断词）
CONCLUSION = ["我认为", "我的结论", "核心是", "主要是", "所以", "因此", "结论",
              "一句话", "归根结底", "本质", "关键"]
# 证据信号（具体事实）
EVIDENCE = ["当时", "具体", "比如", "例如", "后来", "首先", "其次", "然后",
            "我们做了", "我的做法", "我负责", "我主导", "我独立"]
# 数据
NUM = re.compile(r"\d+(?:\.\d+)?\s*(?:%|个百分点|万|亿|千|百|元|人|天|小时|分钟|次|个|条|倍|ms|秒)")
# 反思信号
REFLECTION = ["反思", "如果重来", "如果再来", "学到", "教训", "改进", "下次",
              "复盘", "现在回想", "不足"]
# 弱化词：把功劳推给集体的表述（面试官分不清你做了什么）
WEAKEN = ["参与了", "我参与", "协助", "帮忙", "配合", "我们做了", "我们团队",
          "大家一起", "跟同事一起"]
# 强化词：体现个人 ownership 的表述
STRONG = ["我主导", "我负责", "我独立", "我推动", "我决定", "我设计", "我提出",
          "我牵头", "我完成"]


def hits(text: str, words: list[str]) -> list[str]:
    return [w for w in words if w in text]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--answer", required=True, help="你的回答文本文件")
    ap.add_argument("--question", default="", help="对应的面试问题")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    p = Path(args.answer)
    if not p.exists():
        print(f"[FATAL] 文件不存在: {p}")
        return 2
    text = p.read_text(encoding="utf-8", errors="ignore")
    body = re.sub(r"\s", "", text)

    h_con = hits(text, CONCLUSION)
    h_evi = hits(text, EVIDENCE)
    h_ref = hits(text, REFLECTION)
    nums = NUM.findall(text)

    score = 0
    parts = []

    if len(body) < 80:
        parts.append(("❌", "回答太短（<80 字）——面试官会觉得你没准备"))
        score += 0
    elif len(body) > 900:
        parts.append(("⚠️", f"回答偏长（{len(body)} 字）——常规题建议 60-90 秒（约 250-400 字）"))
        score += 8
    else:
        parts.append(("✅", f"长度合适（{len(body)} 字）"))
        score += 15

    if h_con:
        parts.append(("✅", f"有结论性表述（{'、'.join(h_con[:3])}）"))
        score += 25
    else:
        parts.append(("❌", "没有明确结论——建议开头就把答案说出来（结论先行）"))
        parts.append(("💡", "改法：第一句写「这件事的核心是…」，再展开"))

    if len(h_evi) >= 2:
        parts.append(("✅", f"有具体事实（{'、'.join(h_evi[:4])}）"))
        score += 25
    elif h_evi:
        parts.append(("⚠️", "事实细节偏少——面试官会怀疑真实性，建议补具体动作"))
        score += 12
    else:
        parts.append(("❌", "全是概括性表述，没有具体做了什么"))
        parts.append(("💡", "改法：把「我负责了 X」换成「我做了 A、B、C 三件事」"))

    if len(nums) >= 2:
        parts.append(("✅", f"有量化结果（{len(nums)} 处：{'、'.join(nums[:4])}）"))
        score += 25
    elif nums:
        parts.append(("⚠️", f"量化数据仅 {len(nums)} 处，建议补关键指标"))
        score += 12
    else:
        parts.append(("❌", "没有任何数字——面试官无法判断成果大小"))
        parts.append(("💡", "改法：补上规模（多少人/多少量）、幅度（百分比）、时间（周期）"))

    if h_ref:
        parts.append(("✅", f"有反思（{'、'.join(h_ref[:3])}）——这类回答最加分"))
        score += 10

    # 贡献边界：弱化词 vs 强化词
    h_weak = hits(text, WEAKEN)
    h_strong = hits(text, STRONG)
    if h_weak and not h_strong:
        parts.append(("❌", f"通篇是{('、'.join(h_weak[:3]))}——面试官看不出你做了什么"))
        parts.append(("💡", "改法：把「我参与了 X」换成「我在 X 里负责 A、产出了 B」；"
                             "团队归团队，个人归个人"))
        score -= 10
    elif len(h_weak) > len(h_strong) and h_weak:
        parts.append(("⚠️", f"弱化表述（{len(h_weak)}）多于强化表述（{len(h_strong)}）——"
                             f"建议明确个人贡献边界"))
    elif h_strong:
        parts.append(("✅", f"有明确个人贡献表述（{'、'.join(h_strong[:3])}）"))
        score += 5

    score = min(score, 100)
    verdict = ("回答结构完整，能扛住追问" if score >= 80 else
               "基本可用，补齐上面的缺口会更稳" if score >= 55 else
               "结构不完整，建议按框架重写")

    out = {
        "问题": args.question or "(未提供)",
        "字数": len(body),
        "结论信号": h_con, "事实信号": h_evi,
        "数据": nums, "反思信号": h_ref,
        "评分": score, "结论": verdict,
        "检查项": parts,
    }

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    print("=" * 56)
    if args.question:
        print(f"  问题：{args.question[:50]}")
    print(f"  回答自评　字数 {len(body)}　评分 {score}/100")
    print("=" * 56)
    for mark, msg in parts:
        print(f"  {mark} {msg}")
    print("-" * 56)
    print(f"  结论：{verdict}")
    print("\n提示：机器只查结构要素，回答内容是否真实、有无夸大需要你自己把关。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
