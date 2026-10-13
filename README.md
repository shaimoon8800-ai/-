# Practical AI Skills · 实用型 AI Skill 合集

> 中文场景优先、开箱即用的 AI Skill 合集。每一个都对应一个**真实且高频的痛点**，
> 附带可离线运行的本地脚本 —— 不是"看起来很专业、用起来很没用"的那种。

## 包含的 Skill

| Skill | 一句话 | 类型 |
|---|---|---|
| 🎯 **简历狙击手** `resume-sniper` | 一份简历 + 一个岗位 JD → 关键词全中的定制简历 + 面试官最可能追问的 10 个问题 | 提示词 + 脚本 |
| 🗒️ **会议纪要提炼官** `meeting-digest` | 会议逐字稿 / 速记 / 群聊记录 → 一页纸纪要：结论 / 决议 / 待办 / 风险 / 未决 | 提示词 + 脚本 |
| 🧾 **票据管家** `receipt-keeper` | 一批发票、收据、行程单（PDF 或图片）→ 可直接交财务的 Excel 台账 | 提示词 + 脚本 |

## 为什么值得用

- **中文场景优先**：市面上的 Skill 绝大多数默认英文输入 + 海外 SaaS 语境，
  中文简历规范、中文口语会议、中国增值税发票这些场景基本没人做。
- **带本地脚本**：`receipt-keeper` 能真读 PDF 发票并生成 xlsx；
  `resume-sniper` 能算 JD 关键词命中率；`meeting-digest` 能统计发言分布与待办密度。
- **数据不出本机**：脚本全部本地运行，不上传任何票据或个人内容。

## 目录结构

```
<skill-slug>/
├── SKILL.md              # Skill 定义（frontmatter + 工作流 + 红线）
├── references/*.md       # 领域参考（规则、模板、词表）
└── scripts/*.py          # 本地可执行脚本（无强制第三方依赖时优先纯标准库）
```

## 安装

将对应目录放入你的 Agent 的 skills 目录即可（不同宿主路径不同，常见为
`~/.config/claude-code/skills/` 或宿主的 skills 目录）。

```bash
cp -r resume-sniper ~/.config/claude-code/skills/
```

## 环境要求

- Python 3.9+
- `receipt-keeper`：`pypdf`、`openpyxl`
- `resume-sniper`：`jieba`（可选，缺省时降级为术语白名单匹配）
- `meeting-digest`：无第三方依赖

## 每个 Skill 的设计原则

1. **宁缺毋错**：字段提取不到就留空并记录警告，绝不推测、绝不编造
2. **不越界**：简历不编造经历、纪要不臆造决议、票据不篡改金额
3. **可验收**：待办必须"一个人 + 一个交付物 + 一个日期"；命中率必须能算出来
4. **不替代专业判断**：票据不替代财务审核，也不提供税务建议

## 许可证

MIT
