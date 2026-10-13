#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""短视频口播时长估算与超时校验（离线可用，无第三方依赖）。

用法:
  # 直接给口播稿，按目标时长校验
  python3 shot_duration.py --script 分镜表.md --minutes 1

  # 只估算一段文本
  python3 shot_duration.py --text "你的口播稿……"

  # 按平台默认时长校验
  python3 shot_duration.py --script 分镜表.md --platform 抖音
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# 中文正常讲述语速（字/分钟），保守取 240
CHARS_PER_MIN = 240

PLATFORM_LIMIT = {
    "抖音": (21, 45),
    "视频号": (60, 90),
    "小红书": (30, 60),
    "B站": (180, 480),
    "快手": (30, 60),
}

CN = re.compile(r"[\u4e00-\u9fa5]")
# 分镜表行：| 镜号 | 时长 | 景别 | 画面 | 台词 | 拍法 | 备注 |
TIME_CELL = re.compile(r"(\d+(?:\.\d+)?)\s*[-–~]\s*(\d+(?:\.\d+)?)\s*s?")
SINGLE_CELL = re.compile(r"^(\d+(?:\.\d+)?)\s*s$")


def count_cn(text: str) -> int:
    return len(CN.findall(text))


def strip_md(text: str) -> str:
    """去掉 markdown 表格符号与常见标记，只留台词内容。"""
    lines = []
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith("|") and s.endswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            # 取「台词」列（若列数 >= 5 取第 5 列，否则整体）
            lines.append(cells[4] if len(cells) >= 5 else " ".join(cells))
        elif s and not s.startswith("#"):
            lines.append(s)
    return "\n".join(lines)


def parse_shot_times(text: str) -> tuple[float, int]:
    """从分镜表里解析出（总时长秒数, 识别到的镜头数）。"""
    total = 0.0
    shots = 0
    for ln in text.splitlines():
        s = ln.strip()
        if not (s.startswith("|") and s.endswith("|")):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if not cells:
            continue
        # 在第 1/2 列里找时间
        for c in cells[:3]:
            m = TIME_CELL.search(c)
            if m:
                total += float(m.group(2)) - float(m.group(1))
                shots += 1
                break
            m = SINGLE_CELL.match(c)
            if m:
                total += float(m.group(1))
                shots += 1
                break
    return total, shots


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", help="分镜表或口播稿文件")
    ap.add_argument("--text", help="直接给文本")
    ap.add_argument("--minutes", type=float, default=0, help="目标时长（分钟）")
    ap.add_argument("--platform", default="", help="按平台默认时长校验")
    ap.add_argument("--cpm", type=int, default=CHARS_PER_MIN, help="语速（字/分钟）")
    args = ap.parse_args()

    if args.script:
        p = Path(args.script)
        if not p.exists():
            print(f"[FATAL] 文件不存在: {p}")
            return 2
        raw = p.read_text(encoding="utf-8", errors="ignore")
    elif args.text:
        raw = args.text
    else:
        print("[FATAL] 需要 --script 或 --text")
        return 2

    speech = strip_md(raw)
    n = count_cn(speech)
    est_min = n / max(args.cpm, 1)
    est_sec = est_min * 60

    print("=" * 54)
    print(f"  口播字数（中文字符）: {n}")
    print(f"  语速假设            : {args.cpm} 字/分钟")
    print(f"  估算口播时长        : {est_sec:.1f} 秒（{est_min:.2f} 分钟）")

    shot_total, shot_n = parse_shot_times(raw)
    if shot_n:
        print(f"  分镜表标注总时长    : {shot_total:.1f} 秒（{shot_n} 个镜头）")
        print(f"  平均每镜            : {shot_total/shot_n:.1f} 秒")
        if shot_total > est_sec * 1.35:
            print("  ⚠️ 标注时长比口播估算长很多——可能台词太少或镜头留白过多")
        elif est_sec > shot_total * 1.35:
            print("  ⚠️ 口播字数超出标注时长——按 240 字/分钟算，念不完")
    print("=" * 54)

    lo = hi = None
    label = ""
    if args.platform and args.platform in PLATFORM_LIMIT:
        lo, hi = PLATFORM_LIMIT[args.platform]
        label = f"{args.platform} 建议区间"
    elif args.minutes:
        lo, hi = args.minutes * 60 * 0.85, args.minutes * 60 * 1.15
        label = f"目标 {args.minutes} 分钟（±15%）"

    if lo is not None:
        print(f"\n[{label}] {lo:.0f}–{hi:.0f} 秒")
        budget_hi = int(hi / 60 * args.cpm)
        budget_lo = int(lo / 60 * args.cpm)
        print(f"  对应字数预算: {budget_lo}–{budget_hi} 字")
        if est_sec < lo:
            print(f"  ⚠️ 偏短 {lo - est_sec:.0f} 秒——内容可以再充实，或缩短目标时长")
        elif est_sec > hi:
            print(f"  ❌ 超出 {est_sec - hi:.0f} 秒（约 {int((est_sec-hi)/60*args.cpm)} 字）")
            print("     必须删内容。优先删：重复表达、形容词、铺垫句、可有可无的例子。")
        else:
            print("  ✅ 时长合适")
    else:
        for name, (l, h) in PLATFORM_LIMIT.items():
            mark = "✅" if l <= est_sec <= h else "❌"
            print(f"  {mark} {name:6} 建议 {l}-{h}s")

    return 0


if __name__ == "__main__":
    sys.exit(main())
