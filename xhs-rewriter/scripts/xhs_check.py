#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# compliance-check:pass — 本文件是违禁词检查工具，必须列举违禁词本身才能工作
"""小红书笔记校验：标题字数 / 正文长度 / 标签数量 / 违禁词（离线可用）。

用法:
  python3 xhs_check.py --text 笔记.txt
  python3 xhs_check.py --title "标题" --body "正文" --tags "职场,简历"
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

TITLE_LIMIT = 20

# 违禁/高风险表述（按类型）
TABOO = {
    "导流": ["加微信", "加我微信", "私信我", "留联系方式", "站外", "扫码", "公众号",
             "vx", "VX", "威信", "薇信", "扣扣", "企鹅号"],
    "绝对化": ["最有效", "第一", "最好", "最强", "永久", "彻底根治", "百分百",
               "100%有效", "全网最低", "独一无二", "国家级"],
    "医疗功效": ["治疗", "治愈", "消炎", "祛疾", "药到病除", "根治", "抗癌"],
    "虚假承诺": ["三天瘦", "一周瘦", "月入过万", "稳赚", "包过", "保过", "零风险"],
    "诱导互动": ["点赞过百就", "转发抽奖", "集赞", "求赞", "必回关"],
}

TAG_SPLIT = re.compile(r"[,#，#、\s]+")


def check_title(t: str) -> list[str]:
    out = []
    n = len(t)
    if n == 0:
        out.append("❌ 标题为空")
        return out
    if n > TITLE_LIMIT:
        out.append(f"❌ 标题 {n} 字，超出上限 {TITLE_LIMIT} 字，需删 {n - TITLE_LIMIT} 字")
    else:
        out.append(f"✅ 标题 {n} 字（≤{TITLE_LIMIT}）")
    if re.search(r"[。！？!?]$", t):
        out.append("💡 标题结尾带标点，小红书惯例可去掉以省字数")
    return out


def check_taboo(text: str) -> list[str]:
    out = []
    for kind, words in TABOO.items():
        hits = [w for w in words if w.lower() in text.lower()]
        if hits:
            out.append(f"🚫 [{kind}] 命中：{'、'.join(hits)}")
    return out or ["✅ 未命中违禁词表"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", help="笔记全文文件")
    ap.add_argument("--title", default="")
    ap.add_argument("--body", default="")
    ap.add_argument("--tags", default="")
    args = ap.parse_args()

    title, body, tags = args.title, args.body, args.tags
    full = ""

    if args.text:
        p = Path(args.text)
        if not p.exists():
            print(f"[FATAL] 文件不存在: {p}")
            return 2
        full = p.read_text(encoding="utf-8", errors="ignore")
        lines = [ln.strip() for ln in full.splitlines() if ln.strip()]
        # 第一行非 # 开头的当标题
        for ln in lines:
            if not ln.startswith("#") and not ln.startswith("【"):
                title = title or ln.lstrip("# ").strip()
                break
        tag_line = next((ln for ln in lines if "#" in ln and len(ln) < 120), "")
        tags = tags or tag_line
        body = body or full
    else:
        full = f"{title}\n{body}\n{tags}"

    tag_list = [t for t in TAG_SPLIT.split(tags) if t]

    print("=" * 50)
    print("  小红书笔记校验")
    print("=" * 50)

    print("\n【标题】")
    for line in check_title(title):
        print(f"  {line}")

    n_body = len(re.sub(r"\s", "", body))
    print(f"\n【正文】共 {n_body} 字（含标点，去空白）")
    if n_body > 1000:
        print("  ⚠️ 超过 1000 字，小红书正文有长度上限且过长影响完读率")
    elif n_body < 100:
        print("  ⚠️ 不足 100 字，内容偏薄，考虑补充细节")
    else:
        print("  ✅ 长度合适")

    print(f"\n【标签】共 {len(tag_list)} 个")
    if tag_list:
        print(f"  {' / '.join('#' + t for t in tag_list[:12])}")
    if len(tag_list) < 3:
        print("  ⚠️ 少于 3 个，建议 4-6 个（1 大词 + 2-3 精准词 + 1-2 长尾词）")
    elif len(tag_list) > 10:
        print("  ⚠️ 多于 10 个，标签过载会稀释权重")
    else:
        print("  ✅ 数量合适")

    print("\n【合规检查】")
    for line in check_taboo(full):
        print(f"  {line}")

    print("\n" + "=" * 50)
    print("提示：机器只查字面，平台还会做语义审核。发布前请人工再读一遍。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
