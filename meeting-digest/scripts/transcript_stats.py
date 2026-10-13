#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""会议转写稿统计器（离线可用，无第三方依赖）。

给纪要提炼做量化辅助：
  - 发言分布（谁说了多少，是否存在一言堂）
  - 待办密度（哪些议题在推进、哪些在原地打转）
  - 时间估算（按字数推算时长）
  - 风险/异议信号词扫描（漏项检查）

用法:
  python3 transcript_stats.py 会议记录.txt
  python3 transcript_stats.py 会议记录.txt --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# 「说话人：内容」格式（兼容中英文冒号）
SPEAKER = re.compile(r"^\s*(?:\[[\d:.]+\]\s*)?([\u4e00-\u9fa5A-Za-z][\u4e00-\u9fa5A-Za-z0-9_·]{0,11})\s*[:：]\s*(.*)$")

# 待办信号词
ACTION_WORDS = [
    "我来", "你去", "他负责", "咱们", "跟进", "落实", "输出", "给一版", "同步",
    "对接", "确认一下", "整理", "发一下", "提交", "排期", "对齐", "拉通",
    "截止", "deadline", "ddl", "交付", "之前给", "号之前",
]
# 决议信号词
DECISION_WORDS = [
    "就这么定", "就这么办", "定下来", "拍板", "同意", "通过", "可以按", "按这个来",
    "没问题就", "我的意见", "先按", "就这么", "那就", "听我的", "定了", "记下来",
    "先记下来", "这事定了",
]
# 风险/异议信号词
RISK_WORDS = ["风险", "担心", "隐患", "万一", "不行", "有问题", "但是", "不同意", "前提是", "可能会"]
# 未决信号词
PENDING_WORDS = ["下次再议", "再说", "待定", "回头讨论", "先放着", "再看看"]

CN_CHAR = re.compile(r"[\u4e00-\u9fa5]")


def count_word_hits(text: str, words: list[str]) -> dict[str, int]:
    return {w: text.count(w) for w in words if text.count(w) > 0}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", help="转写稿文件")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--chars-per-min", type=int, default=200,
                    help="讲话速度（字/分钟），中文口语约 180-220")
    args = ap.parse_args()

    p = Path(args.path)
    if not p.exists():
        print(f"[FATAL] 文件不存在: {p}")
        return 2
    raw = p.read_text(encoding="utf-8", errors="ignore")

    lines = [ln for ln in raw.splitlines() if ln.strip()]
    speakers: dict[str, int] = {}
    unlabeled = 0
    for ln in lines:
        m = SPEAKER.match(ln)
        if m:
            sp, content = m.group(1), m.group(2)
            speakers[sp] = speakers.get(sp, 0) + len(CN_CHAR.findall(content))
        else:
            unlabeled += len(CN_CHAR.findall(ln))

    total_chars = sum(speakers.values()) + unlabeled
    est_min = round(total_chars / max(args.chars_per_min, 1), 1)

    # 一言堂检测
    top_share = 0.0
    top_speaker = ""
    if speakers:
        top_speaker, top_chars = max(speakers.items(), key=lambda x: x[1])
        top_share = round(top_chars * 100 / max(sum(speakers.values()), 1), 1)

    out = {
        "总字数": total_chars,
        "估算时长_分钟": est_min,
        "发言人数": len(speakers),
        "未标注段落字数": unlabeled,
        "发言分布": dict(sorted(speakers.items(), key=lambda x: -x[1])[:12]),
        "最高占比": f"{top_speaker} {top_share}%" if speakers else "—",
        "待办信号": count_word_hits(raw, ACTION_WORDS),
        "决议信号": count_word_hits(raw, DECISION_WORDS),
        "风险异议信号": count_word_hits(raw, RISK_WORDS),
        "未决信号": count_word_hits(raw, PENDING_WORDS),
    }

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    print("=" * 52)
    print(f"  总字数 {total_chars}　估算时长 ≈ {est_min} 分钟")
    print(f"  识别到发言人 {len(speakers)} 位，未标注段落 {unlabeled} 字")
    print("=" * 52)
    if speakers:
        print("\n【发言分布】（字数 / 占比）")
        tot = max(sum(speakers.values()), 1)
        for sp, n in sorted(speakers.items(), key=lambda x: -x[1])[:12]:
            bar = "█" * max(1, int(n * 30 / tot))
            print(f"  {sp:<10} {n:>6}  {n*100//tot:>3}%  {bar}")
        if top_share >= 60:
            print(f"\n  ⚠️ 单人占比 {top_share}%，接近一言堂——检查是否有他人意见被淹没。")

    def show(title: str, d: dict[str, int]) -> None:
        print(f"\n【{title}】命中 {sum(d.values())} 次")
        if not d:
            print("  （无）")
            return
        for w, n in sorted(d.items(), key=lambda x: -x[1]):
            print(f"  {w} × {n}")

    show("待办信号", out["待办信号"])
    show("决议信号", out["决议信号"])
    show("风险/异议信号", out["风险异议信号"])
    show("未决信号", out["未决信号"])

    print("\n" + "-" * 52)
    if sum(out["决议信号"].values()) == 0:
        print("⚠️ 未检出任何决议信号——这场会可能只讨论没结论，纪要里不要写'决议'。")
    if sum(out["待办信号"].values()) > 0 and not speakers:
        print("⚠️ 有大量待办信号但没识别到发言人——责任人需要人工回溯。")
    print("提示：以上为机械统计，只用于查漏，不能替代人工判断。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
