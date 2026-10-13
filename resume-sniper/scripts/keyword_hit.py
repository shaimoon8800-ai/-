#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""关键词命中率计算器（离线可用，无第三方依赖）。

用法:
  # 直接给关键词
  python3 keyword_hit.py --resume 简历.txt --keywords "SQL,Python,数据分析,用户增长"

  # 从 JD 文件里自动抽关键词（粗略：抽取指定长度的名词性中文/英文词）
  python3 keyword_hit.py --resume 简历.txt --jd JD.txt

  # 输出 JSON（供上层编排消费）
  python3 keyword_hit.py --resume 简历.txt --keywords "SQL,Python" --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

EN_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9+#./\-]{1,22}")
CN_CHAR = re.compile(r"[\u4e00-\u9fa5]")

# 噪声词（JD 里高频但无区分度）
STOP = {
    "负责", "要求", "以上", "具有", "具备", "熟悉", "了解", "掌握", "熟练",
    "相关", "优先", "经验", "能力", "工作", "岗位", "公司", "团队", "以及",
    "我们", "你们", "能够", "可以", "良好", "优秀", "较强", "有一", "有较",
    "精通", "使用", "进行", "完成", "参与", "协助", "支持", "制定", "执行",
    "实现", "提供", "推动", "落地", "输出", "提升", "优化", "搭建", "独立",
    "策划", "基于", "通过", "包括", "等等", "其他", "任职", "职责", "岗位职责",
    "任职要求", "加分", "优先考虑", "学历", "本科", "硕士", "以上学历", "有一定",
    "者优先", "有限", "方向", "相关经验", "以上经验", "具备较强", "能够独立",
    "较强", "以下", "下面", "上述", "负责", "参与", "组织", "开展",
}

# 英文停用词（不构成技能）
EN_STOP = {
    "and", "or", "the", "for", "with", "you", "your", "our", "are", "will",
    "not", "but", "from", "that", "this", "have", "has", "can", "all", "any",
    "of", "to", "in", "on", "at", "by", "is", "be", "as", "it", "we", "us",
    "etc", "per", "via", "job", "role", "team", "work", "year", "years",
}

# 保留的词性：名词/专名/动名词/形容词性名词/简称/习用语/英文
KEEP_POS = {"n", "nz", "nt", "nr", "vn", "an", "j", "l", "eng"}

# 无 jieba 时的降级白名单（常见职能术语，宁缺毋滥）
TERM_WHITELIST = (
    "用户增长", "用户运营", "用户分层", "生命周期", "私域", "复购", "留存", "拉新",
    "转化率", "客单价", "数据驱动", "数据分析", "数据看板", "指标体系", "业务增长",
    "内容运营", "社群运营", "活动策划", "品牌营销", "渠道投放", "用户调研",
    "产品运营", "增长黑客", "商业分析", "项目管理", "供应链管理", "财务分析",
    "风险控制", "合规管理", "招聘管理", "绩效管理", "培训体系", "客户成功",
)


def read_text(p: str) -> str:
    path = Path(p)
    if not path.exists():
        raise SystemExit(f"[FATAL] 文件不存在: {p}")
    for enc in ("utf-8", "utf-8-sig", "gbk"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="ignore")


def extract_keywords(jd: str, top: int = 40) -> list[str]:
    """从 JD 抽关键词。

    - 英文/技术词（SQL、Tableau、LTV、A/B）优先级最高，权重 3
    - 中文词走 jieba 词性标注，只保留名词性词（n/nz/nt/vn/an/j/l）
    - 无 jieba 时降级为「英文词 + 术语白名单匹配」，不再乱切词

    早期版本用 `[\\u4e00-\\u9fa5]{2,6}` 贪婪匹配，会切出「熟练使用」「策略制定与落」
    这类断句碎片——那是废词，不是关键词。
    """
    score: dict[str, float] = {}
    disp: dict[str, str] = {}

    # 1) 英文 / 技术词
    for m in EN_TOKEN.finditer(jd):
        w = m.group(0).strip(".-/")
        if len(w) < 2:
            continue
        lw = w.lower()
        if lw in EN_STOP:
            continue
        # 纯数字类跳过
        if re.fullmatch(r"[\d.]+", w):
            continue
        disp.setdefault(lw, w)
        score[lw] = score.get(lw, 0) + 3.0

    # 2) 中文词
    try:
        import jieba.posseg as pseg  # type: ignore

        for w, flag in pseg.cut(jd):
            w = w.strip()
            if len(w) < 2 or w in STOP:
                continue
            if not re.fullmatch(r"[\u4e00-\u9fa5]+", w):
                continue
            if flag not in KEEP_POS:
                continue
            score[w] = score.get(w, 0) + 1.0
            disp.setdefault(w, w)
    except ImportError:
        # 降级：只吃术语白名单，宁缺毋滥
        for term in TERM_WHITELIST:
            if term in jd:
                score[term] = score.get(term, 0) + 2.0
                disp.setdefault(term, term)

    ranked = sorted(score.items(), key=lambda x: (-x[1], -len(x[0]), x[0]))
    out: list[str] = []
    for key, _ in ranked:
        out.append(disp[key])
        if len(out) >= top:
            break
    return out


def check(resume: str, keywords: list[str]) -> dict:
    low = resume.lower()
    hits, miss = [], []
    for k in keywords:
        k = k.strip()
        if not k:
            continue
        (hits if k.lower() in low else miss).append(k)
    total = len(hits) + len(miss)
    rate = round(len(hits) * 100 / total, 1) if total else 0.0
    return {
        "total": total,
        "hits": hits,
        "misses": miss,
        "hit_count": len(hits),
        "rate": rate,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--resume", required=True, help="简历文本文件")
    ap.add_argument("--keywords", default="", help="逗号分隔的关键词")
    ap.add_argument("--jd", default="", help="JD 文件（自动抽关键词）")
    ap.add_argument("--top", type=int, default=40, help="JD 自动抽取关键词上限")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    resume = read_text(args.resume)

    if args.keywords.strip():
        kws = [k.strip() for k in args.keywords.split(",") if k.strip()]
        src = "manual"
    elif args.jd:
        kws = extract_keywords(read_text(args.jd), args.top)
        src = "jd-auto"
    else:
        print("[FATAL] 需要 --keywords 或 --jd 之一")
        return 2

    result = check(resume, kws)
    result["source"] = src

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print(f"关键词来源: {'手动指定' if src == 'manual' else 'JD 自动抽取'}（{result['total']} 个）")
    print(f"命中率: {result['hit_count']}/{result['total']} = {result['rate']}%\n")
    print("✅ 已命中:")
    for k in result["hits"]:
        print(f"   - {k}")
    print("\n❌ 未命中（需补 或 确认真的没有）:")
    for k in result["misses"]:
        print(f"   - {k}")
    if result["rate"] < 60:
        print("\n⚠️ 命中率低于 60%，大概率会被 ATS 提前筛掉，建议先补关键词再投。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
