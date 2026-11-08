# 配置案例检索 MCP

任选已开通案例检索权限的一家即可。已有其他名称的官方连接时，先检查该连接的案例工具，无需重复添加。首次配置在客户端完成，具体检索由 Skill 使用当前会话可调用的工具执行。以下使用 Codex CLI，也可按客户端说明配置同一 Streamable HTTP 地址。支持 TOML 的 Codex 环境可合并[配置样例](codex-case-mcp.toml)中选用的部分，已有同名配置时更新原条目。[OpenAI MCP 官方文档](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)

## 威科先行 · 用账号授权

在终端添加仅包含案例检索的服务。

```bash
codex mcp add wk-case-search --url https://mcp.wkinfo.com.cn/mcp-servers/case/
```

按页面提示登录自己的威科先行账号并确认授权。如果添加后尚未发起授权，可运行 `codex mcp login wk-case-search`。核对账号默认应用有案例检索权限和可用额度。使用应用凭证的环境可以改为添加时指定 `--bearer-token-env-var WK_MCP_TOKEN`，并通过受保护配置把该变量提供给客户端。[威科案例服务](https://mcp.wkinfo.com.cn/docs/servers/case) · [威科认证说明](https://mcp.wkinfo.com.cn/docs/authentication)

## 北大法宝 · 用自己的 Token

登录北大法宝官方 MCP 控制台，取得自己账号的 Token，确认开通案例检索。用客户端的密钥管理或启动环境设置 `PKULAW_MCP_TOKEN`，值为 Token 本身，由客户端添加 `Bearer` 前缀。然后添加案例关键词检索服务。

```bash
codex mcp add pkulaw-case-keyword --url https://apim-gateway.pkulaw.com/mcp-case --bearer-token-env-var PKULAW_MCP_TOKEN
```

如果通过终端提供环境变量，请从能读取该变量的同一启动环境运行 Codex。可在 Bash 中用以下方式在本次终端会话输入，输入不会显示在屏幕上。

```bash
read -rsp '北大法宝 MCP Token: ' PKULAW_MCP_TOKEN
printf '\n'
export PKULAW_MCP_TOKEN
codex
unset PKULAW_MCP_TOKEN
```

请在官方控制台或客户端的密钥输入处管理凭证，避免将 Token 放进对话、截图、版本库或命令参数。桌面端从其他环境启动时，按该客户端的密钥配置方式提供凭证。[北大法宝 MCP 平台](https://mcp.pkulaw.com/) · [北大法宝接入指南](https://mcp.pkulaw.com/docs)

## 验收和使用

用 `codex mcp list` 检查配置，再开启新会话确认出现供应商的案例检索工具。用一个自己已知的公开案号（或裁判标题）试查。仅在收到实际工具结果后确认已联通，区分返回的是案号、摘要、裁判正文还是正文链接。是否能读全文、会否扣用套餐额度，按实际返回和账号权益核对。

```text
请使用 $the-secondbest-lawyer，通过我已授权的威科先行查找【公开案号或脱敏争点】，
给出法院、裁判日期、实际读到的内容和来源。如果接不上，请分析我上传的判决书。
```

也可把示例中的供应商改为北大法宝。账号授权失败、额度用完、会话没有工具或正文仍不可读时，按[判决书备用流程](case-access.md)继续。
