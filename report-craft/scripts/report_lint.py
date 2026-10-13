#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""汇报自检：检查是否含成果、数据、行动项，以及过程描述占比（离线可用）。

用法:
  python3 report_lint.py --input 汇报草稿.md
  python3 report_lint.py --input 汇报.md --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

RESULT_WORDS = ["完成", "达成", "上线", "交付", "落地", "提升", "降低", "增长",
                "节省", "缩短", "优化", "解决", "产出", "发布", "结项", "验收"]
PROCESS_WORDS = ["参与", "协助", "配合", "跟进", "推进", "处理", "帮忙", "支持",
                 "参加", "沟通", "讨论", "对接", "了解", "学习"]
ACTION_WORDS = ["下周", "下月", "下阶段", "计划", "将", "目标", "拟", "准备",
                "预计", "后续", "待办"]
PROBLEM_WORDS = ["问题", "风险", "阻碍", "困难", "卡点", "偏差", "延期", "需求",
                 "需要支持", "依赖"]
NUM = re.compile(r"\d+(?:\.\d+)?\s*(?:%|个百分点|万|亿|千|百|元|人|天|小时|次|个|条|倍)")
VAGUE = ["高效", "认真", "积极", "努力", "较好地", "一定程度", "有所", "进一步提升",
         "加强了", "优化了工作"]

# 假阳性上下文：这些词组里的"成果词"其实不是成果
# 例：「落地页」里的"落地"、「用户增长项目」里的"增长"
FALSE_CTX = ["落地页", "增长项目", "增长黑客", "增长团队", "增长部门",
             "提升空间", "提升计划", "优化方案", "优化建议"]


def demote_false_positives(text: str) -> str:
    """把假阳性上下文屏蔽掉，避免把名词误算成成果。"""
    out = text
    for ctx in FALSE_CTX:
        out = out.replace(ctx, "＿" * len(ctx))
    return out


def count(text: str, words: list[str]) -> tuple[int, list[str]]:
    hits = [w for w in words if w in text]
    return sum(text.count(w) for w in words), hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    p = Path(args.input)
    if not p.exists():
        print(f"[FATAL] 文件不存在: {p}")
        return 2
    text = p.read_text(encoding="utf-8", errors="ignore")
    scored = demote_false_positives(text)  # 成果/过程词统计用去假阳性后的文本

    n_num = len(NUM.findall(text))
    n_result, kw_result = count(scored, RESULT_WORDS)
    n_process, kw_process = count(scored, PROCESS_WORDS)
    n_action, kw_action = count(text, ACTION_WORDS)
    n_problem, kw_problem = count(text, PROBLEM_WORDS)
    n_vague, kw_vague = count(text, VAGUE)
    n_chars = len(re.sub(r"\s", "", text))

    checks = []
    score = 0

    # 1) 成果
    if n_result >= 3:
        checks.append(("✅", f"成果表述 {n_result} 处（{'、'.join(kw_result[:5])}）"))
        score += 25
    elif n_result >= 1:
        checks.append(("⚠️", f"成果表述偏少（{n_result} 处），建议把'做了什么'补上'带来什么'"))
        score += 12
    else:
        checks.append(("❌", "未检出成果表述——通篇可能只有过程，没有结果"))
        checks.append(("💡", "改法：每件事后面加「→ 带来什么 → 数据」"))

    # 2) 数据
    if n_num >= 5:
        checks.append(("✅", f"量化数据 {n_num} 处，有数据支撑"))
        score += 25
    elif n_num >= 2:
        checks.append(("⚠️", f"量化数据仅 {n_num} 处，偏少，建议补关键指标"))
        score += 12
    else:
        checks.append(("❌", "几乎没有量化数据——领导看不到你的成果有多大"))
        checks.append(("💡", "改法：给关键成果补上时间/规模/幅度/金额四类数字；"
                             "确实没有的标【请补：数据】，不要编"))

    # 3) 行动项
    if n_action >= 2:
        checks.append(("✅", f"行动项 {n_action} 处（{'、'.join(kw_action[:5])}）"))
        score += 20
    elif n_action >= 1:
        checks.append(("⚠️", "行动项偏少，建议明确「下周 / 下阶段」做什么"))
        score += 10
    else:
        checks.append(("❌", "没有下步计划——显得被动"))
        score += 0

    # 4) 问题与需求
    if n_problem >= 1:
        checks.append(("✅", f"提到了问题/需求（{n_problem} 处），这是加分的"))
        score += 15
    else:
        checks.append(("⚠️", "没有提问题与需求——只报喜会让领导不知道你在哪卡住"))
        score += 5

    # 5) 过程占比
    ratio = n_process / max(n_result, 1)
    if ratio > 2.5 and n_process > 4:
        checks.append(("⚠️", f"过程词（{n_process}）远多于成果词（{n_result}）——"
                             f"像流水账，建议压缩过程、突出结果"))
    else:
        score += 15
        checks.append(("✅", "过程与成果比例尚可"))

    # 6) 虚词
    if n_vague >= 2:
        checks.append(("⚠️", f"空洞评价词 {n_vague} 处（{'、'.join(kw_vague[:4])}）——"
                             f"换成具体事实"))

    score = min(score, 100)
    verdict = ("结构扎实，可以直接交" if score >= 80 else
               "基本可用，建议按下面的提示补一补" if score >= 55 else
               "问题较多，建议重写重点部分")

    out = {
        "字数": n_chars,
        "量化数据数": n_num,
        "成果词": n_result, "过程词": n_process,
        "行动项": n_action, "问题表述": n_problem,
        "评分": score, "结论": verdict,
        "检查项": checks,
    }

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    print("=" * 56)
    print(f"  汇报自检　字数 {n_chars}　评分 {score}/100")
    print("=" * 56)
    for mark, msg in checks:
        print(f"  {mark} {msg}")
    print("-" * 56)
    print(f"  结论：{verdict}")
    print("\n提示：机器只查结构特征，内容真实性需要你自己把关。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
