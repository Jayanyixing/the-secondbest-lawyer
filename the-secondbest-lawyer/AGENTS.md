# AGENTS.md — 本目录是一个法律实务技能包

给所有读 `AGENTS.md` 的 agent（Codex CLI、Cursor、Windsurf、DSH、自建框架等）：本目录不是代码仓库，是一份**法律工作技能**。按下面顺序加载即可，不需要构建、不需要安装依赖。

## 加载顺序

1. 先读本目录的 `SKILL.md`（入口：定位、工作五则、路由表、期限口径、交付限制）。
2. 按用户任务，从 `references/` 只加载对应模块：主模块 1 个 + 补充模块最多 2 个（`citation.md` 常驻，不占额度）：
   - 复杂任务总控：`00-chief.md`
   - 检索与引用：`01-legal-research.md` + `citation.md`（本地检索优先用 `python3 tools/lawdb.py search "关键词"`）
   - 民商诉讼：`02-civil-litigation.md`
   - 刑事：`03-criminal-defense.md`
   - 证据与庭审：`04-evidence-trial.md`
   - 合同与顾问：`05-contract-counsel.md`
   - 尽调：`06-corporate-due-diligence.md`
   - 财产与执行：`07-assets-enforcement.md`
   - 投标：`08-law-firm-tender.md`、`08a-legal-service-bid.md`
   - 期限与联络：`09-case-operations.md`
   - 复核：`10-legal-quality.md`
   - 客户沟通与结案：`11-client-practice.md`
   - 国标／行标／团标：`12-standards.md`
   - 程序动作与紧急模式：`13-procedure-actions.md`
   - 劳动人事：`14-labor.md`
   - 范围外：`scope.md`（命中行政、婚家、破产、知产实体、涉税、涉外等先读它）
3. 交付前读 `references/checklist.md`，有条件时跑 `python3 tools/citation_lint.py`（加 `--verify-db` 可与本地法条／卡片库交叉核对摘录），需要 Word 交付物时用 `python3 tools/docgen.py`（支持 `complaint`／`defense`／`preservation`／`evidence`／`risk`）。

## 无论哪个宿主都必须遵守的三条

1. **引用可追溯**：法条和案例必须有底稿条目——完整案号或条款、来源渠道、具体定位（页／段／小节）、读取范围（全文／节选／摘要／标题）。只有“全文”和“节选”能支撑结论，摘要与标题只能进“待取正文”表。
2. **不造事实**：案号、条号、金额、日期、电话、进度、业绩一律不推测补齐；不知道就写 `【待补：…】` 或标 `待核`。
3. **动作真实**：没有工具返回就不写“已提交／已发送／已冻结／已提醒”。

## 能力差异怎么处理

- 没有联网：按 `references/01-legal-research.md` 出检索式与待取正文表，不假装查过。
- 没有文件系统：只处理对话里给的材料，页码引用到“用户提供文本的第几段”。
- 没有 shell：跳过 `tools/citation_lint.py`，人工过 `references/checklist.md`，并在交付里说明未做机器校验。
- 有子代理能力：可用它做“独立复核”（只给成品与底稿，不给推理过程），否则一律标 `〔自查〕`。

不要在未经用户要求时修改本目录内的文件。新增事实或偏好时，只追加，不改写既有规则。
