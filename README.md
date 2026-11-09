# the-secondbest-lawyer

面向中国大陆（默认北京）执业律师的法律工作技能：民商事、刑事、常年顾问、尽调、执行、律所投标。

名字是自嘲也是定位：**承办律师是第一责任人，AI 是第二好的那个。** 它做检索、分析、起草、核验和自查，不做专业决定，不替律师签字。

**不绑定任何模型或客户端。** 纯 Markdown 资产，Claude Code、Codex、DSH、Hermes、WorkBuddy、Cursor、自建 agent、网页版 Projects 都能用——有技能目录就装目录，只能上传就传 zip，只能粘贴就粘单文件。见 [INSTALL.md](the-secondbest-lawyer/INSTALL.md)。

## 用之前先确认三件事

案件材料进模型之前，先确认：**①** 所内与客户允许用 AI 处理本案材料；**②** 模型服务的数据留存与存放地符合委托与本所规定；**③** 材料已脱敏，或你确认可以上传原件。三项未确认时，技能只做不带案件材料的工作（法条与类案检索、框架、模板）。它不替你判断合规，也不会说「已合规」——只会说「已按你确认的范围处理」。

脱敏口径：证件号**只留后 4 位**（前 6 位是地址码），银行卡、账号、手机号留后 4 位，姓名留姓，地址到区。

## 一条最重要的规则

**每一个法条和案例都必须能追溯到你实际读到的那一段文字。** 不是“搜到过”，是“读到了、标得出页码或段落、说得清来源”。

这条规则不是靠提示词自觉，而是分四层落实：

1. **底稿先行**：任何依据先登记到引用底稿（编号、四要素、来源、定位、读取范围、复核状态），再进正文，正文用 `[C-01]` 这类标签回指。
2. **封闭词表**：读取范围只能是 `全文／节选／摘要／标题／未读`。只有“全文”和“节选”能支撑结论；`摘要` 和 `标题` 只能进“待取正文”表。这一条直接掐死“只看摘要编裁判理由”。
3. **逐字摘录**：每条支撑结论的依据，底稿里必须存一句 **8–60 字的原文摘录**，正文引用处要原样出现。概述不算，`本院认为` 这类套话也不算——摘录是人眼唯一能快速验伪的东西。
4. **交付前回读**：进了结论的条目，重新打开本次实际读到的来源（官方页面、授权商业库、用户导出件都算），逐字比对摘录；不一致就降级为“待取正文”，不允许保留原引用。**回读与官方复核是两件事**：回读问「有没有真读到」，官方复核问「有没有核过官方原文」，后者只有官方站点与用户原件能记「已核」。
5. **机械校验**：交付前跑 `tools/citation_lint.py`，未登记案号、占位案号、摘要素材撑结论、缺摘录、摘录全文找不到、未回读、无状态标签的期限日期、绝对化措辞，一律报错；摘录只在别处出现、规范条目缺效力栏这类是警告。

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
├── SKILL.md                     入口：定位、加载方式、工作五则、路由、期限口径、双模式复核
├── AGENTS.md                    给「读 AGENTS.md 但不认技能目录」的 agent 的入口
├── INSTALL.md                   各客户端安装与验证
├── agents/openai.yaml           Codex 可选适配层
└── references/
    ├── 00-chief.md              受理、优先级、整合
    ├── scope.md                 11 类范围外业务与转介
    ├── 01-legal-research.md     规范与类案检索、核验表、待取正文表
    ├── citation.md              引用可追溯机制（最高优先级）
    ├── data-supply.md           三层数据供给：本地库 → 授权检索 → 人工导出
    ├── 02-civil-litigation.md   请求权基础、管辖五步、请求写法、金额口径
    ├── 03-criminal-defense.md   分阶段工作、辩护要点检查表
    ├── 04-evidence-trial.md     大材料索引协议、证据矩阵、质证与庭审
    ├── 05-contract-counsel.md   交易闭环、条款清单、执业合规提示
    ├── 06-corporate-due-diligence.md  尽调、否定性结论写法
    ├── 07-assets-enforcement.md 线索、保全、执行、扩张主体
    ├── 08-law-firm-tender.md    投标全流程、无效投标七类、落标救济时限
    ├── 08a-legal-service-bid.md 法律服务采购：方案十节、团队与证明、报价、评分拆解
    ├── 09-case-operations.md    期限三档、期限类型全表、公开联络
    ├── 10-legal-quality.md      自查／有限复核／独立复核
    ├── 11-client-practice.md    会谈、预期管理、收费与授权、调解授权、结案沉淀
    ├── 12-standards.md          国标/行标/团标检索、效力四态、标准在诉讼与合同中的用法
    ├── 13-procedure-actions.md  立案→保全→审理→上诉→执行的动作与材料清单、紧急模式
    ├── 14-labor.md              劳动人事：主体资格、竞业范围、补偿 N/N+1/2N、工伤三金、举证
    ├── checklist.md             交付前总闸
    ├── handoff.md               交接卡（文本版＋JSON 版）
    ├── eval-protocol.md         10 例回溯盲评、6 维 0–3 分
    ├── sources.md               官方入口与受限处理
    ├── case-access.md           案例检索选路与降级
    ├── case-mcp-setup.md        案例库 MCP 配置（含 Claude Code／Codex 写法）
    ├── codex-case-mcp.toml      配置样例
    └── acceptance-scenarios.md  34 个试用与压力测试场景
├── MAINTENANCE.md               半年一次复查＋触发式复查，带到期表
├── data/                        法条库、卡片库、manifest、版本风险表（cards.sqlite 为 95 张脱敏卡）
└── tests/fixtures/              解析器测试数据
templates/                       文书 JSON 样例、取卡模板与批次、弃卡清单、检索验收题
tools/
├── lawdb.py                     法条库＋结案卡片：导入／检索／按条取文／哈希校验／card-*
├── citation_lint.py             引用校验器（18 条规则）
├── card_health.py               条号错位、跨卡矛盾、占位值、cause↔tags 一致性
├── feedback.py / improve.py     失败信号记录与改进提案（只提不改库）
├── retrieval_check.py           检索验收回归（data/retrieval-cases.json）
├── lawdiff.py                   官方件 vs 库内文本逐条比对
├── ocr_pdf.js                   扫描件 OCR（macOS Vision，约 1–2 秒/页）
├── docgen.py                    直出 docx（起诉状／证据目录／风险告知书，零依赖）
├── build.py                     生成单文件版与技能包
├── eval_score.py                评测分数汇总
├── review_due.py                复查到期检查
├── tender_matrix.py             采购文件 → 响应矩阵
├── tender_consistency.py        标书形式一致性（C1–C6）
├── tender_score.py              评分测算与降价边际
├── tender_credits.py            业绩匹配与缺口
└── test_tender.py               投标工具回归测试（7 项断言）
eval/                            评测模板：case-card / scoring CSV
dist/                            构建产物（单文件 lite/full + zip）
```

## 校验器

```bash
python3 tools/citation_lint.py 代理意见.md --ledger citations.json
python3 tools/citation_lint.py 代理意见.md --ledger 底稿.md --mode review
```

底稿可以是 JSON（结构见 [`handoff.md`](the-secondbest-lawyer/references/handoff.md)）或 markdown 表格（表头含“编号／类型／案号／定位／读取范围／回读／官方复核”即可）。交付首页写「官方复核未核 N 条」；正式诉讼材料的未核条目单独进「提交前须核」清单——这是警告口径，不阻断交付。

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
| R12 | 摘录不在引用处附近：全文别处能找到→**警告**；全文都找不到→**错误** |
| R13 | 摘录过短或全是套话，无法证伪 |
| R14 | 同一摘录被不同条目复用（警告；`--strict` 下为错误） |
| R15 | 用于结论的条目未回读；回读日期缺日期（警告）或晚于运行当天（错误） |
| R16 | 规范类条目缺「规范效力」或「适用时点」（警告）；规范效力「未确认」却用于结论（错误）——两条独立判定，缺字段不屏蔽错误；`--strict` 下用于结论却缺「规范效力」报错 |
| R17 | 离线稿形态不合规：缺〔草稿〕／缺「未经联网回读」声明／缺待回读清单／肯定地声称可交付（错误） |
| R18 | 来源渠道与官方复核矛盾：商业库／转载件却记「已核」（错误） |

没有 shell 的宿主跳过校验器，人工过 [`references/checklist.md`](the-secondbest-lawyer/references/checklist.md)，并在交付里说明未做机器校验。

## 检索接入

技能规定了国家法律法规数据库、人民法院案例库、中国裁判文书网及北京官方来源的用法，并要求核对适用时点、条款、案例差异与原始出处。

案例库接入选哪家都行：北大法宝用自己账号的 Token，威科先行用自己账号 OAuth。任意支持 MCP 的客户端都能接（Claude Code、Codex、DSH、自建框架），凭证只在客户端授权流程或受保护配置里，**不进对话、不进仓库**。见 [`case-mcp-setup.md`](the-secondbest-lawyer/references/case-mcp-setup.md)。

接不上或读不到正文时按 [`case-access.md`](the-secondbest-lawyer/references/case-access.md) 降级：读你上传的判决书 → 给可复制检索式 → 单列“待取正文”，不猜裁判理由。

## 三层数据供给：先本地，后联网

技能不附带数据库权限，所以数据分三层取，顺序写死：**L1 本地库 → L2 授权检索 → L3 人工导出 → 待取正文**。

**L1 本地法条库**（离线、毫秒级、零查询费）。仓库自带 **84 部、9081 条**：法律 42、司法解释与规定 20、行政法规 12、部门规章等其他 7、北京地方性法规 3。含民法典全 1260 条、刑法 505 条（「之N」条号已拆分，查第 133 条之一得到危险驾驶）、民诉法 306 条、刑诉法 308 条、公司法 266 条、建工与买卖合同司法解释、劳动争议与劳动合同法、担保制度解释等。条号逐部校验过连续性（版本分档见 [`data/VERSION-RISK.md`](data/VERSION-RISK.md)）。

**这是检索索引，不是引用底稿。** 10 部为官方原件（已核：3 部人大网当期法律 + 3 部北京地方性法规 + 民法典／公司法／证券法／劳动合同法的 flk 官方 Word 原件逐条比对），74 部为带版本日期的整理件（未核）。整理件用于定位与比对，正式文书引用前必须回读官方原文——这条与引用规则是同一条，不是两套标准。

```bash
python3 tools/lawdb.py seed                   # 按 data/manifest.json 批量入库
python3 tools/lawdb.py query 公告期间 期限     # 中文全文检索（FTS5 trigram，多词 AND）
python3 tools/lawdb.py article 中华人民共和国民法典 第五百八十五条
python3 tools/lawdb.py stats                  # 部数、条数、按部明细
python3 tools/lawdb.py verify                 # 比对磁盘文件哈希（当前 84/84 一致）

# 加一部法：文件丢进 data/sources/，manifest.json 加一条，再 seed
python3 tools/lawdb.py import 民法典.docx --name 中华人民共和国民法典 \
    --issuer 全国人民代表大会 --publish 2020-05-28 --effective 2021-01-01 \
    --url https://flk.npc.gov.cn/... --official-check 已核
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

## 投标：从采购文件到响应矩阵

标书废标多来自漏条和低级不一致，两件事都能机器查：

```bash
# 1. 采购文件 → 响应矩阵骨架（资格性／实质性／评分项分开）
python3 tools/tender_matrix.py 采购文件/ --body 标书/ --out matrix.csv

# 2. 标书一致性：大写与小写、跨文件总价、同一日期、暗标文档属性
python3 tools/tender_consistency.py 标书/ --anonymous
```

`tender_matrix.py` 按 6 字片段重合率标「已应答／弱匹配／未找到」，未覆盖条目单列；分类靠关键词，必有误判，**以采购文件和评标办法原文为准，工具只保证不漏条**。

`tender_consistency.py` 查的是形式矛盾：大写金额与数字对不上、投标总价在不同文件里不同、同一截止时间两个日期、Word 属性里残留作者名。金额是否合理、业绩是否真实仍要人判断。

报价与业绩也能算：

```bash
python3 tools/tender_score.py 自评.json                    # 三种价格分算法、对手排名、降价边际
python3 tools/tender_credits.py --need 3 --years 2023-2026 --keyword 顾问
```

`tender_score.py` 只按采购文件写的公式算：最低价法、基准价法、固定价满分。超限价直接判无效并返回非零。它回答的是「再让 5% 换几分」——这个数几乎总是小于让掉的利润，比感觉可靠。对手报价是假设，不等于中标概率。

业绩素材单独存 `data/credits.json`（样例见 `data/credits.example.json`），每条记可披露范围与授权状态；投标时按采购要求匹配，输出「可用／需授权／不可用」——缺口由匹配算出，而不是临时回忆该不该编。

## 结案卡片：把判断沉淀下来

办过的案子不该只用一次。`lawdb card-add` 把「争点 → 裁判要点 → 我方胜负手 → 摘录」存进同一个库，`lawdb card-query` 按关键词召回：

```bash
python3 tools/lawdb.py card-add --case-no "（2023）京0105民初XXX号" \
    --cause 买卖合同纠纷 --issues "逾期验收是否视为验收合格" \
    --holding "未在合理期限提出异议视为验收合格" --key-point "验收单须留签收记录" \
    --quote "买受人未在约定期限内提出质量异议" --source 本地库

python3 tools/lawdb.py card-query 验收
```

### 卡片库：公开 95 张，本地全量另存

`data/cards.sqlite` **入库**，但只含 **95 张脱敏卡**——clone 下来就能直接 `card-query`、跑 `card_health.py`。

含当事人姓名的 5 张案卷卡（`id` 1、2、6、9、14）留在本地全量库 `data/cards.full.sqlite`（已 gitignore，100 张）。**两张表不是同一个东西**：

| 文件 | 卡片数（2026-11-09 实测） | 是否入库 |
|---|---:|---|
| `data/cards.sqlite` | 95（全 verified） | ✅ |
| `data/cards.full.sqlite` | 100（全 verified，含 5 张姓名卡） | ❌ |
| `data/cards.json` | 95，与 `cards.sqlite` 同源导出的只读副本 | ✅ |

`card_health.py` 默认体检 95 张那份；要体检全量：`python3 tools/card_health.py --db data/cards.full.sqlite`。新增卡片默认写 `cards.sqlite`，涉姓名的那几张本地手动挪到 `cards.full.sqlite`，**不要把全量库推上去**。

### 扫描件怎么办

判决书多为扫描 PDF，没有文本层。用 macOS Vision OCR 转文本：

```bash
PDF_PATH=/path/判决书.pdf OUT_PATH=/tmp/j.txt osascript -l JavaScript tools/ocr_pdf.js
```

约 1–2 秒/页，中文识别可用；OCR 有错字，**摘录必须回原图核对**后再入库——实测 15 张卡里就有 1 张因 OCR 漏字而摘录失真（`荣誉称号具体理由` 漏了「的」）。

### 入库校验

卡片入库前过校验，**整批不通过就不入库**：

| 规则 | 说明 |
|---|---|
| 九字段必填 | case_no / cause / issues / holding / our_side / key_point / quote / source / tags |
| 摘录长度 | 判例卡 8–60 字，规则卡 8–120 字；必须是原文，概述不算 |
| 案号须脱敏且合格式 | 真实案号（年份＋法院代字＋类型＋数字号）必须保留 X/＊ 遮罩；**来源编号**（指导案例、典型案例、公报案例、入库编号）不要求遮罩，保留序号以维持区分度 |
| 同案号+同争点不重复 | 批次内和库内双向查；重复默认跳过，`--replace` 覆盖 |
| 摘录核验状态 | `verify_status` 列，默认 `pending`；回原文比对后 `card-verify` 改 `verified` |
| `kind` | `judgment`（判例卡，`case_no` 为真实案号或典型案例编号）／`rule`（规则卡，`case_no` 为《法规名》或会议纪要/指导意见名称）。规则卡不要求遮罩 |
| `our_side` 口径 | **本卡适用于哪一方**（我方在同类案件中所处位置），不是原审诉讼地位。可填诉讼地位（原告／被告）或角色（劳动者／用人单位／承包人／发包人） |

`source` 统一写「来源名｜URL｜抓取日期」，单张卡片自带可核验信息，不依赖外部清单。

```bash
lawdb.py card-query 施工 --status verified   # 只看已回原文核过的
lawdb.py card-query 施工 --status pending    # 只看待核
lawdb.py card-query 质量 --kind rule         # 只看规则卡（会议纪要/司法解释类）
```

当前入库 **95 张全部 verified**（2026-11-09 实测：判例 45、规则 50；另 5 张姓名卡在本地 `cards.full.sqlite`，全量 100 张）。`data/cards.json` 由同一份 `cards.sqlite` 导出，两者内容一致；改库后跑 `python3 tools/lawdb.py card-export` 重新导出，别手改 JSON。

从判决书抽卡的顺序与反例见 [`templates/card-extraction.md`](templates/card-extraction.md)。

## 评测：跑过才有分数

`references/eval-protocol.md` 写的是怎么做**回溯盲评**：10 件已结案件，隐藏结论，同一案件只跑一次，按 6 个维度 0–3 分打分（事实准确／引用可追溯／时点适用／不利面覆盖／交付可用／边界诚实），编造类问题直接记 0。

```bash
cp eval/case-card.template.json eval/cases/C01.json
cp eval/scoring.template.csv eval/scores.csv
python3 tools/eval_score.py eval/scores.csv
```

已跑两轮，样本都是最高法已生效典型案例（官方裁判理由封存后比对），结果与方法见 [`eval/README.md`](eval/README.md)：

| | 第一批（禁网） | 第二批（联网） |
|---|---|---|
| 样本 | 劳动争议 5 ＋ 虚假诉讼逃废债 5 | 网络消费 5 ＋ 民企保护 5 |
| 总分 | 2.77 | **2.98** |
| 引用可追溯 | 2.00（回读率 0%） | **3.00**（回读率 100%，163 条逐字比对） |
| 阻断 | 0 | 0 |

两批分数**不可直接相减**：样本类型、难度、盲法强度都不同。读第二批结果时注意两条限制：

- `blind/` 附的来源页本身就是官网案例页，代理读完等于读到裁判理由（多份自述"本案即发布稿案例 X"），所以第二批的「交付可用／结论一致」不算独立预测能力，有效读数只有引用可追溯、时点适用、边界诚实。
- 联网也只能拿到 `court.gov.cn`；`npc.gov.cn` 被 WAF 302 回首页、`flk.npc.gov.cn` 只返回 552 字节空壳，法条回读全部走 wikisource，10 份简报一律标「未核（仅转载）」，无一份冒充官方已核。

第一批暴露的真缺陷（C02 把劳动人事整块判为范围外、C04 漏竞业限制范围主线、C10 误判误工费）已修，见 `CHANGELOG.md` v2.36.2。

## 自检：改完先跑一遍

```bash
python3 tools/test_citation_lint.py   # 引用校验器回归，79/79 条断言（含对抗样例，见 tests/fixtures/EXPECTATIONS.md）
python3 tools/test_tender.py          # 投标四件套回归，7/7
python3 tools/test_lawdb.py           # 条号归一（38／第三十八条／133之一…），9/9
python3 tools/test_lawdiff.py         # 法条逐字比对（标题粘连 vs 实质差异），5/5
python3 tools/retrieval_check.py      # 卡片检索回归，8/8
python3 tools/card_health.py          # 条号错位、跨卡矛盾、占位值、cause↔tags 一致性
python3 tools/lawdb.py verify         # 法条文件哈希，84/84
```

测试计数口径：一条断言＝一次 `_chk()` 调用（同一断言换个 fixture 再跑算另一条），所以数字会随样例增加而涨；`test_citation_lint.py` 的输出末尾会打印断言总数，与本节数字一致。

`card_health.py` 会把每张卡的摘录放回它自称的条文里比对：摘录字对但条号错，它就报出来。这条检查逮到过真错误（民诉法解释终本恢复曾引 517 条第二款而非 519 条）。

失败信号记 `data/feedback.jsonl`（`tools/feedback.py`），`tools/improve.py` 只聚类出提案，**不自动改库**。

## 维护

- 常规：每 6 个月复查；触发式：新法施行、程序法修订、官方入口迁移、实战中出现错引。
- 到期检查：`python3 tools/review_due.py`（逾期返回非零）。
- 清单见 [`MAINTENANCE.md`](MAINTENANCE.md)。

## 已知局限

- 格式、内部链接、校验器、法条库、构建与到期脚本已实测；**未做真实案件准确率评测**（见上节）。
- 本地法条库 **84 部、9081 条**（2026-11-09 `lawdb.py stats` 实测），覆盖民法典、刑法、三大诉讼法、公司法、劳动、建工、担保、破产、知产、行政与数据合规，含 20 部司法解释与规定；**不含北京以外的地方性文件，部门规章仅 7 部**。其中 **10 部为官方原件逐条比对（已核），74 部为整理件（未核）**，正式文书引用前须按 `citation.md` 回读官方原文。
- 卡片库全量 100 张（入库 95 张）全部来自已办案件与公开典型案例，**只能证明「这一案这样判」，不证明跨案结论**；`pending` 卡不可引用。
- 法条条号与数值一律现场核，技能内不写死条文内容——避免技能自己制造错误引用。
- 行政、婚姻家事继承、破产重整、知识产权实体比对、涉税、涉外等属范围外，只给边界与最小辅助，见 [`scope.md`](the-secondbest-lawyer/references/scope.md)；**劳动人事不属范围外**，由 [`14-labor.md`](the-secondbest-lawyer/references/14-labor.md) 覆盖（不做精确测算、伤残等级、竞业效力终局判断）。
- 单会话内的“复核”只是自查，交付物会标 `〔自查〕`；要独立复核需新上下文或另一位律师。
- 官方复核栏按**默认拒绝**归一：只有词表内的写法能记「已核」，其余写法（不论是否带「核」字——「未经官方核实」「核对中」「待核」「基本核实」「已比对一致」「已验证」「一致」）一律按「未核」并进汇总提示；非官方渠道留空同样计入「官方复核未核 N 条」，但不报错。
- 渠道写「官方」时，出处必须给出官方站点链接：主机名等于白名单域名或以「.白名单域名」结尾（court.gov.cn／npc.gov.cn／www.gov.cn 限 `/zhengce/xxgk/gjgzk/` 路径／bjrd.gov.cn），不认裸 `gov.cn`；`pkulaw.com`、`lexiscn.com`、`court.gov.cn.evil.com`、`pkulaw.com/redirect?u=court.gov.cn` 均由 R18 报错，只写出处文件名或页码也报错。官方站点下载的导出件：渠道写「导出」＋出处写官方链接＋官方复核记「已核（与官方原文一致）」，三者齐备才放行。
- 渠道不是「官方」时，官方复核栏**只接受**未核词表、不适用或留空；写任何肯定说法报 R18（含「已比对一致」「与官方原文一致」「已验证」「已确认」「已查证」「一致」）。
- `citation_lint.py` **只验形式**：编号登记、摘录位置、字段完整性、状态词合法。它不判断摘录是否真的支持那句话，也不判断案情与规则是否匹配——语义越界只能靠人工抽样复核。
- 编造一个**看似合理的过去日期**（例如把回读日期写成上周某天）无法被机械识别：校验器只能拦未来日期、缺日期和明显矛盾，真假仍以回读记录与原文为准。
- 官方复核**多数情况仍会记「未核」**：`npc.gov.cn` 深链被 WAF 302 回首页、`flk.npc.gov.cn` 只返回前端空壳，法条常只能从维基文库等转载件读；此时交付物首页会写「官方复核未核 N 条」，不是遗漏，是如实标注。
- 正式成果由承办律师结合原始材料与实际委托复核。

## 仓库性质

**公开仓库，已脱敏。** 内容分三类：

| 内容 | 是否公开 | 说明 |
|---|---|---|
| skill 本体、工具、法条库 | ✅ 公开 | 法律文本不受著作权保护，工具为通用能力 |
| 卡片库 `data/cards.sqlite`、`data/cards.json` | ✅ 公开（**已脱敏**） | 95 张，两种格式同源；**每张卡的 `quote` 都是逐字原文**。含当事人姓名的 5 张案卷卡不在其中，只存本地 `cards.full.sqlite`，避免出现“脱敏后引文不再逐字”的中间状态 |
| 案件快照 `templates/snapshots/` | ✅ 公开 | 均为最高法公开发布的典型案例页，本身已匿名 |
| 检索报告 `reports/` | ❌ 不公开 | 含具体案件分析与当事人关系，`.gitignore` 已排除 |
| 本地全量卡片库 `data/cards.full.sqlite` | ❌ 不公开 | 100 张，比公开版多 5 张含姓名的案卷卡 |

脱敏口径：姓名→姓+某（侯某→侯某、张某→张某、高某→高某）；案号保留遮罩（`（2024）京03民终16XXX号`）；企业名称保留（公开主体）。

公开副本全部为 `verified`（引文逐字、可引用）。其中公报案例（2021）最高法民再188号的原页 `gongbao.court.gov.cn` 已无法直取，引文经盈造网转载件核对，`source` 字段注明「转载件、官方复核未做」。**不含**任何“因脱敏而降级”的卡片。

## 许可

[MIT](LICENSE)。
