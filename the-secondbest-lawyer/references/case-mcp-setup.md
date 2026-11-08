# 配置案例检索 MCP

两家任选其一即可。已有其他名称的官方连接时，先看该连接里有没有案例工具，不必重复添加。凭证一律由用户在自己客户端完成授权或写入受保护配置——**不贴在对话里，不进仓库，不进日志**。

服务均为 Streamable HTTP，因此 Claude Code、Codex、DSH、Hermes、WorkBuddy 及自建框架等任意支持 MCP 的客户端都能接；下面给两种主流写法，其余客户端按「服务地址 + Bearer/OAuth」自行配置。不支持 MCP 的宿主直接走[接入与降级](case-access.md)。

## 威科先行（账号 OAuth）

服务地址：`https://mcp.wkinfo.com.cn/mcp-servers/case/`

Codex CLI：

```bash
codex mcp add wk-case-search --url https://mcp.wkinfo.com.cn/mcp-servers/case/
codex mcp login wk-case-search
```

Claude Code：

```bash
claude mcp add --transport http wk-case-search https://mcp.wkinfo.com.cn/mcp-servers/case/
```

在客户端弹出的页面登录自己的威科账号并确认授权。核对账号默认应用有案例检索权限与额度。

## 北大法宝（自己的 Token）

服务地址：`https://apim-gateway.pkulaw.com/mcp-case`，客户端加 `Bearer` 前缀。

先登录北大法宝官方 MCP 控制台取得自己账号的 Token，确认已开通案例检索。

Codex CLI（推荐用环境变量，不写在命令行参数里）：

```bash
# 在本终端录入，不回显、不进历史
read -rsp '北大法宝 MCP Token: ' PKULAW_MCP_TOKEN; printf '\n'; export PKULAW_MCP_TOKEN
codex mcp add pkulaw-case-keyword --url https://apim-gateway.pkulaw.com/mcp-case --bearer-token-env-var PKULAW_MCP_TOKEN
codex
unset PKULAW_MCP_TOKEN
```

Claude Code：用 `--header` 方式添加，值从环境变量读，不写明文。

```bash
claude mcp add --transport http pkulaw-case-keyword https://apim-gateway.pkulaw.com/mcp-case \
  --header "Authorization: Bearer $PKULAW_MCP_TOKEN"
```

## 通用兜底

客户端支持配置文件时，写等价的 HTTP 服务条目即可（Codex 见 [codex-case-mcp.toml](codex-case-mcp.toml)）；敏感值用客户端的密钥管理或环境变量引用，不写进文件本体。

## 验收

1. 列出配置确认条目存在（如 `codex mcp list`）。
2. **开新会话**，确认出现该供应商的案例工具。
3. 用自己知道的一个公开案号或裁判标题试查，区分返回的是案号、摘要、正文还是正文链接。
4. 换算力：确认是否扣套餐额度。

只有收到实际工具返回才能说“已联通”。授权成功与查询成功分开记录。

```text
用律师技能，通过我已授权的威科先行查找【公开案号或脱敏争点】，
给出法院、裁判日期、实际读到的内容和来源定位。接不上就分析我上传的判决书。
```

调用写法随客户端而异（`/` `@` `$` 或直接叙述），不依赖特定语法。

授权失败、额度用完、会话没有工具、正文仍不可读时，按[检索接入与降级](case-access.md)继续，不反复重试。
