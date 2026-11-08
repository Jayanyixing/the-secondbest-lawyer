# the-secondbest-lawyer

面向中国大陆（默认北京）执业律师的法律工作技能：民商事、刑事、常年顾问、尽调、执行、律所投标。

名字是自嘲也是定位：**承办律师是第一责任人，AI 是第二好的那个。** 它做检索、分析、起草、核验和自查，不做专业决定，不替律师签字。

**不绑定任何模型或客户端。** 纯 Markdown 资产，Claude Code、Codex、DSH、Hermes、WorkBuddy、Cursor、自建 agent、网页版 Projects 都能用——有技能目录就装目录，只能上传就传 zip，只能粘贴就粘单文件。见 [INSTALL.md](the-secondbest-lawyer/INSTALL.md)。

## 一条最重要的规则

**每一个法条和案例都必须能追溯到你实际读到的那一段文字。** 不是“搜到过”，是“读到了、标得出页码或段落、说得清来源”。

这条规则不是靠提示词自觉，而是分四层落实：

1. **底稿先行**：任何依据先登记到引用底稿（编号、四要素、来源、定位、读取范围、复核状态），再进正文，正文用 `[C-01]` 这类标签回指。
2. **封闭词表**：读取范围只能是 `全文／节选／摘要／标题／未读`。只有“全文”和“节选”能支撑结论；`摘要` 和 `标题` 只能进“待取正文”表。这一条直接掐死“只看摘要编裁判理由”。
3. **逐字摘录**：每条支撑结论的依据，底稿里必须存一句 **8–60 字的原文摘录**，正文引用处要原样出现。概述不算，`本院认为` 这类套话也不算——摘录是人眼唯一能快速验伪的东西。
4. **交付前回读**：进了结论的条目，重新打开来源逐字比对摘录；不一致就降级为“待取正文”，不允许保留原引用。
5. **机械校验**：交付前跑 `tools/citation_lint.py`，未登记案号、占位案号、摘要素材撑结论、缺摘录、摘录不在引用处、未回读、无状态标签的期限日期、绝对化措辞，一律报错。

说清楚一件事：**校验器只能验形式一致性，不能证明那条案例是真的**。能不能证伪，靠摘录、回读和律师本人。不要把“校验通过”当成“已核实”。

细则见 [`references/citation.md`](the-secondbest-lawyer/references/citation.md)。

## 安装（三选一）

| 你的宿主 | 怎么办 |
|---|---|
| 有技能目录的客户端 | 把 `the-secondbest-lawyer/` 整个文件夹放进技能目录（Claude Code `~/.claude/skills/`、DSH `~/.dsh/skills/`、Hermes `~/.hermes/skills/<分类>/`、Codex 技能目录） |
| 接受技能包 / 压缩包 | 上传 `dist/the-secondbest-lawyer.zip`（WorkBuddy：技能 → 添加技能 → 上传技能） |
| 只能粘贴文本 | 粘贴 `dist/the-secondbest-lawyer-lite.md`（约 1.2 万字）或 `-full.md`（约 3.9 万字） |

生成分发件：

```bash
python3 tools/build.py      # 输出到 dist/，无第三方依赖
```

调用方式随客户端而异（`/名称`、`@名称`、`$名称` 或直接描述任务），技能不依赖任何一种写法。

## 目录

```text
the-secondbest-lawyer/
├── SKILL.md                     入口：定位、加载方式、五条铁律、路由、期限口径、双模式复核
├── AGENTS.md                    给「读 AGENTS.md 但不认技能目录」的 agent 的入口
├── INSTALL.md                   各客户端安装与验证
├── agents/openai.yaml           Codex 可选适配层
└── references/
    ├── 00-chief.md              受理、优先级、整合
    ├── scope.md                 范围外业务与转介
    ├── 01-legal-research.md     规范与类案检索、核验表、待取正文表
    ├── citation.md              引用可追溯机制（最高优先级）
    ├── 02-civil-litigation.md   请求权基础、管辖五步、请求写法、金额口径
    ├── 03-criminal-defense.md   分阶段工作、辩护要点检查表
    ├── 04-evidence-trial.md     大材料索引协议、证据矩阵、质证与庭审
    ├── 05-contract-counsel.md   交易闭环、条款清单、执业合规提示
    ├── 06-corporate-due-diligence.md  尽调、否定性结论写法
    ├── 07-assets-enforcement.md 线索、保全、执行、扩张主体
    ├── 08-law-firm-tender.md    响应矩阵、报价、递交检查
    ├── 09-case-operations.md    期限三档、期限类型全表、公开联络
    ├── 10-legal-quality.md      自查／有限复核／独立复核
    ├── 11-client-practice.md    会谈、预期管理、收费与授权、调解授权、结案沉淀
    ├── 12-standards.md          国标/行标/团标检索、效力四态、标准在诉讼与合同中的用法
    ├── 13-procedure-actions.md  立案→保全→审理→上诉→执行的动作与材料清单、紧急模式
    ├── checklist.md             交付前总闸
    ├── handoff.md               交接卡（文本版＋JSON 版）
    ├── sources.md               官方入口与受限处理
    ├── case-access.md           案例检索选路与降级
    ├── case-mcp-setup.md        案例库 MCP 配置（含 Claude Code／Codex 写法）
    ├── codex-case-mcp.toml      配置样例
    └── acceptance-scenarios.md  29 个试用与压力测试场景
├── MAINTENANCE.md               半年一次复查＋触发式复查，带到期表
├── data/                        本地法条库（law.sqlite，不入库）
├── tests/fixtures/              解析器测试数据
templates/                       起诉状／证据目录／风险告知书 的 JSON 样例
tools/
├── lawdb.py                     本地法条库＋结案卡片：导入／检索／按条取文／哈希校验／card
├── citation_lint.py             引用校验器（15 条规则）
├── build.py                     生成单文件版与技能包
├── docgen.py                    直出 docx（起诉状／证据目录／风险告知书，零依赖）
├── eval_score.py                评测分数汇总
└── review_due.py                复查到期检查
eval/                            评测模板：case-card / scoring CSV
dist/                            构建产物（单文件 lite/full + zip）
```

## 校验器

```bash
python3 tools/citation_lint.py 代理意见.md --ledger citations.json
python3 tools/citation_lint.py 代理意见.md --ledger 底稿.md --mode review
```

底稿可以是 JSON（结构见 [`handoff.md`](the-secondbest-lawyer/references/handoff.md)）或 markdown 表格（表头含“编号／类型／案号／定位／读取范围／官方复核”即可）。

输出示例：

```text
引用校验：代理意见.md

错误 3 条：
  - [R3] 第 14 行用「abstract」级材料 [C-02] 支撑正文
  - [R1] 第 22 行案号未在任何底稿条目中登记：（2022）京01民终99999号
  - [R5] 第 31 行给出期限日期但没有状态标签（已核／〔假设〕／待核）

未通过：修正后再标注可交付。
```

| 规则 | 抓什么 |
|---|---|
| R1 | 未登记案号、占位案号、未登记指导案例／入库编号 |
| R2 | 底稿缺来源、定位、读取范围或复核状态 |
| R3 | 摘要／标题级材料被用来支撑正文 |
| R4 | 把未确认生效的裁判写成生效判决 |
| R5 | 期限日期没有 `已核`／`〔假设〕`／`待核` 标签 |
| R6 | 绝对化结论（无任何风险、肯定胜诉等） |
| R7 | 无具体依据的引用（根据相关规定、某法院认为等） |
| R8 | 引用了不存在的底稿编号 |
| R9 | 自查模式却写“已复核” |
| R10 | 底稿条目未被引用（可能多余） |
| R11 | 支撑结论的条目缺原文摘录 |
| R12 | 摘录没有出现在引用处（或全文找不到） |
| R13 | 摘录过短或全是套话，无法证伪 |
| R14 | 同一摘录被不同条目复用 |
| R15 | 用于结论的条目未回读 |

没有 shell 的宿主跳过校验器，人工过 [`references/checklist.md`](the-secondbest-lawyer/references/checklist.md)，并在交付里说明未做机器校验。

## 检索接入

技能规定了国家法律法规数据库、人民法院案例库、中国裁判文书网及北京官方来源的用法，并要求核对适用时点、条款、案例差异与原始出处。

案例库接入选哪家都行：北大法宝用自己账号的 Token，威科先行用自己账号 OAuth。任意支持 MCP 的客户端都能接（Claude Code、Codex、DSH、自建框架），凭证只在客户端授权流程或受保护配置里，**不进对话、不进仓库**。见 [`case-mcp-setup.md`](the-secondbest-lawyer/references/case-mcp-setup.md)。

接不上或读不到正文时按 [`case-access.md`](the-secondbest-lawyer/references/case-access.md) 降级：读你上传的判决书 → 给可复制检索式 → 单列“待取正文”，不猜裁判理由。

## 三层数据供给：先本地，后联网

技能不附带数据库权限，所以数据分三层取，顺序写死：**L1 本地库 → L2 授权检索 → L3 人工导出 → 待取正文**。

**L1 本地法条库**（离线、毫秒级、零查询费）。仓库自带一份示例语料（3 部当期法律、159 条，均从中国人大网取原文并核过条数），开箱即可检索；常用法自己导入 3 分钟一部：

```bash
python3 tools/lawdb.py seed                   # 按 data/manifest.json 批量入库
python3 tools/lawdb.py query 公告期间          # 中文全文检索（FTS5 trigram）
python3 tools/lawdb.py stats
python3 tools/lawdb.py verify                 # 比对磁盘文件哈希，被改动即报警

# 加一部法：文件丢进 data/sources/，manifest.json 加一条，再 seed
python3 tools/lawdb.py import 民法典.docx --name 中华人民共和国民法典 \
    --issuer 全国人民代表大会 --publish 2020-05-28 --effective 2021-01-01 \
    --url https://flk.npc.gov.cn/... --official-check 已核
python3 tools/lawdb.py query 违约金 调整      # 中文全文检索（FTS5 trigram）
python3 tools/lawdb.py article 中华人民共和国民法典 第五百八十五条
python3 tools/lawdb.py verify                 # 比对磁盘文件哈希，被改动即报警
```

数据**不做爬虫**：官方站点普遍反爬（实测 `flk` 接口已改为前端渲染、法院转载站 403），批量抓取既不稳也不合规。做法是律师从官方下载页取 Word／HTML／PDF 一次，本地长期复用。支持的格式：`.txt/.md/.html/.docx/.pdf`。

库里就是原文，所以摘录不会错一个字；每条引用带导入日期与哈希，回读可机器校验。

**L2 授权检索**：案例库 MCP（北大法宝／威科先行）或官方在线检索，见 [`case-mcp-setup.md`](the-secondbest-lawyer/references/case-mcp-setup.md)。
**L3 人工导出**：律师按检索式导出，拖进对话，AI 只做分析与登记。

完整规则见 [`data-supply.md`](the-secondbest-lawyer/references/data-supply.md)。

## 交付物：直接出 Word

律师要交的是 .docx，不是 Markdown。`tools/docgen.py` 零依赖生成三种文书：

```bash
python3 tools/docgen.py complaint --input templates/complaint.sample.json --out 起诉状.docx
python3 tools/docgen.py evidence  --input templates/evidence.sample.json  --out 证据目录.docx
python3 tools/docgen.py risk      --input templates/risk.sample.json      --out 风险告知书.docx
```

生成后脚本会提示还有几处 `【待补】` 占位符——**没替换完不许交出去**。证据目录自动排成表格（序号／名称／证明内容／页数／原件或复印件／备注）。

## 结案卡片：把判断沉淀下来

办过的案子不该只用一次。`lawdb card-add` 把「争点 → 裁判要点 → 我方胜负手 → 摘录」存进同一个库，`lawdb card-query` 按关键词召回：

```bash
python3 tools/lawdb.py card-add --case-no "（2023）京0105民初XXX号" \
    --cause 买卖合同纠纷 --issues "逾期验收是否视为验收合格" \
    --holding "未在合理期限提出异议视为验收合格" --key-point "验收单须留签收记录" \
    --quote "买受人未在约定期限内提出质量异议" --source 本地库

python3 tools/lawdb.py card-query 验收
```

卡片里的摘录同样受 `citation.md` 约束：没有原文就不许写摘录。

## 评测：跑过才有分数

`references/eval-protocol.md` 写的是怎么做**回溯盲评**：10 件已结案件，隐藏结论，同一案件只跑一次，按 6 个维度 0–3 分打分（事实准确／引用可追溯／时点适用／不利面覆盖／交付可用／边界诚实），编造类问题直接记 0。

```bash
cp eval/case-card.template.json eval/cases/C01.json
cp eval/scoring.template.csv eval/scores.csv
python3 tools/eval_score.py eval/scores.csv
```

目前**没有跑过任何一例**，所以本仓库不提供准确率数字。谁跑完，分数才算数。

## 维护

- 常规：每 6 个月复查；触发式：新法施行、程序法修订、官方入口迁移、实战中出现错引。
- 到期检查：`python3 tools/review_due.py`（逾期返回非零）。
- 清单见 [`MAINTENANCE.md`](MAINTENANCE.md)。

## 已知局限

- 格式、内部链接、校验器、法条库、构建与到期脚本已实测；**未做真实案件准确率评测**（见上节）。
- 本地法条库自带 3 部示例语料（159 条），**不是完整法规库**；民法典、民诉法、刑法、公司法等常用法需按 `data/README.md` 自行导入。
- 法条条号与数值一律现场核，技能内不写死条文内容——避免技能自己制造错误引用。
- 行政、婚姻家事继承、破产重整、劳动仲裁实体、知识产权实体比对、涉税、涉外等属范围外，只给边界与最小辅助，见 [`scope.md`](the-secondbest-lawyer/references/scope.md)。
- 单会话内的“复核”只是自查，交付物会标 `〔自查〕`；要独立复核需新上下文或另一位律师。
- 正式成果由承办律师结合原始材料与实际委托复核。

## 许可

[MIT](LICENSE)。
