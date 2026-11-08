# the-secondbest-lawyer

面向中国大陆（默认北京）执业律师的法律工作技能：民商事、刑事、常年顾问、尽调、执行、律所投标。

名字是自嘲也是定位：**承办律师是第一责任人，AI 是第二好的那个。** 它做检索、分析、起草、核验和自查，不做专业决定，不替律师签字。

**不绑定任何模型或客户端。** 纯 Markdown 资产，Claude Code、Codex、DSH、Hermes、WorkBuddy、Cursor、自建 agent、网页版 Projects 都能用——有技能目录就装目录，只能上传就传 zip，只能粘贴就粘单文件。见 [INSTALL.md](the-secondbest-lawyer/INSTALL.md)。

## 一条最重要的规则

**每一个法条和案例都必须能追溯到你实际读到的那一段文字。** 不是“搜到过”，是“读到了、标得出页码或段落、说得清来源”。

这条规则不是靠提示词自觉，而是分三层落实：

1. **底稿先行**：任何依据先登记到引用底稿（编号、四要素、来源、定位、读取范围、复核状态），再进正文，正文用 `[C-01]` 这类标签回指。
2. **封闭词表**：读取范围只能是 `全文／节选／摘要／标题／未读`。只有“全文”和“节选”能支撑结论；`摘要` 和 `标题` 只能进“待取正文”表。这一条直接掐死“只看摘要编裁判理由”。
3. **机械校验**：交付前跑 `tools/citation_lint.py`，正文里出现未登记的案号、占位案号、摘要素材撑结论、无状态标签的期限日期、绝对化措辞，一律报错，不许标“可交付”。

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
    ├── checklist.md             交付前总闸
    ├── handoff.md               交接卡（文本版＋JSON 版）
    ├── sources.md               官方入口与受限处理
    ├── case-access.md           案例检索选路与降级
    ├── case-mcp-setup.md        案例库 MCP 配置（含 Claude Code／Codex 写法）
    ├── codex-case-mcp.toml      配置样例
    └── acceptance-scenarios.md  29 个试用与压力测试场景
tools/
├── citation_lint.py             引用校验器（10 条规则，无第三方依赖）
└── build.py                     生成单文件版与技能包
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

没有 shell 的宿主跳过校验器，人工过 [`references/checklist.md`](the-secondbest-lawyer/references/checklist.md)，并在交付里说明未做机器校验。

## 检索接入

技能规定了国家法律法规数据库、人民法院案例库、中国裁判文书网及北京官方来源的用法，并要求核对适用时点、条款、案例差异与原始出处。

案例库接入选哪家都行：北大法宝用自己账号的 Token，威科先行用自己账号 OAuth。任意支持 MCP 的客户端都能接（Claude Code、Codex、DSH、自建框架），凭证只在客户端授权流程或受保护配置里，**不进对话、不进仓库**。见 [`case-mcp-setup.md`](the-secondbest-lawyer/references/case-mcp-setup.md)。

接不上或读不到正文时按 [`case-access.md`](the-secondbest-lawyer/references/case-access.md) 降级：读你上传的判决书 → 给可复制检索式 → 单列“待取正文”，不猜裁判理由。

## 已知局限

- 格式、内部链接、校验器与构建脚本已实测；**未做真实案件准确率评测**。
- 法条条号与数值一律现场核，技能内不写死条文内容——避免技能自己制造错误引用。
- 行政、婚姻家事继承、破产重整、劳动仲裁实体、知识产权实体比对、涉税、涉外等属范围外，只给边界与最小辅助，见 [`scope.md`](the-secondbest-lawyer/references/scope.md)。
- 单会话内的“复核”只是自查，交付物会标 `〔自查〕`；要独立复核需新上下文或另一位律师。
- 正式成果由承办律师结合原始材料与实际委托复核。

## 许可

[MIT](LICENSE)。
