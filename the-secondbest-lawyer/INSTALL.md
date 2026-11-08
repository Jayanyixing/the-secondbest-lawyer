# 安装与接入（全 agent 通用）

本技能是纯 Markdown ＋ 一个可选的 Python 校验器，**不绑定任何模型或客户端**。按宿主能力选一行即可。

| 宿主 | 放哪里 | 怎么调用 |
|---|---|---|
| **Claude Code** | `~/.claude/skills/the-secondbest-lawyer/`（项目级放 `.claude/skills/`） | 自动按描述触发，或明确点名 |
| **Codex CLI** | 技能目录 `~/.codex/skills/the-secondbest-lawyer/`；或在项目根放 `AGENTS.md` 指向本目录 | `$the-secondbest-lawyer` 或直接描述任务（`agents/openai.yaml` 是它的可选适配层） |
| **DSH** | `~/.dsh/skills/the-secondbest-lawyer/` | 会话技能目录里选，或直接点名 |
| **Hermes** | `~/.hermes/skills/<分类>/the-secondbest-lawyer/`（分类目录可放 `DESCRIPTION.md`） | 按分类挂载后调用 |
| **WorkBuddy（腾讯）** | 「专家·技能·连接器 → 技能 → 添加技能 → 上传技能」，上传 `dist/the-secondbest-lawyer.zip`；也支持从 `.agents` 等目录复制安装 | 在对话里选中该技能，或直接描述任务 |
| **Cursor / Windsurf / Zed 等** | 项目内 `.cursor/rules`、`.windsurf/rules`，或项目根 `AGENTS.md` 指向本目录 | 随规则加载 |
| **能读文件但没有技能机制** | 让 agent 读 `the-secondbest-lawyer/AGENTS.md`（已写成通用入口） | 直接描述任务 |
| **只能上传文件（知识库/项目文件）** | 上传 `dist/the-secondbest-lawyer-full.md` | 上传后直接提问 |
| **只能粘贴（自定义 GPT、网页 Projects、Gem、自建 bot、API system prompt）** | 粘贴 `dist/the-secondbest-lawyer-lite.md`（约 12K 字）或 `-full.md`（约 40K 字） | 直接提问 |

## 生成分发件

```bash
python3 tools/build.py          # 生成 dist/ 下的单文件版与技能包 zip
```

产物：

- `dist/the-secondbest-lawyer-lite.md` — 核心规则版，适合上下文有限的宿主；
- `dist/the-secondbest-lawyer-full.md` — 全模块合并版，适合知识库与长上下文宿主；
- `dist/the-secondbest-lawyer.zip` — 技能包，适合 WorkBuddy 上传或任意文件夹式安装。

单文件版把 `references/` 的内容按顺序合并，**不需要宿主能读多个文件**，也不需要联网；文件内已写明没有工具时怎么降级。

## 装完怎么验证

1. 问一句「你能用哪些法律工作能力」——应当能说出模块与「引用必须可追溯」这条铁律；
2. 给一个含**虚构案号**的小任务（如“（2020）京01民终12345号支持我这个观点吗”）——合格表现是先判断能否核到原文，核不到就标待取正文，**而不是顺着编裁判理由**；
3. 有 shell 时跑一次 `python3 tools/citation_lint.py 测试.md`，确认脚本可执行（无第三方依赖，Python 3.8+ 即可）。

## 卸载

删掉对应目录或技能包即可，不写注册表、不改系统配置、不装依赖。

## 注意

- 本技能不含任何密钥、Token、Cookie。案例库凭证由你在客户端自行授权，见 `references/case-mcp-setup.md`。
- 上传到第三方平台前，注意该平台的数据政策；法律案卷含个人信息，优先本地/私有部署宿主。
