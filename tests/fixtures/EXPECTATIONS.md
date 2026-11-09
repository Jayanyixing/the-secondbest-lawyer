# 对抗样例与期望结果

每个样例都写明期望的退出码与命中规则。跑法：

```bash
python3 tools/citation_lint.py tests/fixtures/<名>.md [--ledger tests/fixtures/<名>.json] [--mode offline] [--strict]
```

> **关于 `flk.npc.gov.cn/detail2.html`**：样例底稿里的这个地址只是**测试占位**，用来满足「官方渠道必须有官方站点链接」这条校验（R18），它指向的是法规库首页，不是任何一部具体法律的原文页。真实底稿必须填**具体原文链接**（如 `https://flk.npc.gov.cn/detail2.html?ZmY4MDgwODE...` 这种带法规 ID 的地址，或该法规在 `www.gov.cn`／`court.gov.cn` 的实际页面），否则「已回读」「已核」都无从谈起。

| 样例 | 参数 | 期望退出码 | 期望规则 | 说明 |
|---|---|---:|---|---|
| `commercial-source.md/.json` | `--ledger …` | 0 | R0（警告） | 商业库已回读、官方复核未核，可以交付但须列「提交前须核」 |
| `commercial-verified.md/.json` | `--ledger …` | 1 | R18 | 商业库来源却写官方「已核」 |
| `commercial-verified-variants.md/.json` | `--ledger …` | 1 | R18 ×3 | `已核（与官方原文一致）`／`已核实`／`官方已核` 三种变体都要拦住 |
| `norm-status-conflict.md/.json` | `--ledger …` | 1 | R16 | N-01「未确认」用于结论＝错误，且缺「适用时点」同时警告；N-02「已废止」缺时点只警告 |
| `norm-status-out-of-vocab.md/.json` | `--ledger …` | 1 | R16 | 「有效」不在词表，按「未确认」处理 |
| `strict-missing-effect.md/.json` | `--ledger …` | 0（仅警告） | R16 | 普通模式：缺「规范效力」只警告 |
| `strict-missing-effect.md/.json` | `--ledger … --strict` | 1 | R16 | 严格模式：用于结论却缺「规范效力」报错 |
| `boilerplate-quote.md/.json` | `--ledger …` | 1 | R13 | 摘录只有「本院认为」，任何判决都有，无法证伪 |
| `reused-quote.md/.json` | `--ledger …` | 0（警告） | R14 | 同一摘录被两个不同结论复用 |
| `reused-quote.md/.json` | `--ledger … --strict` | 1 | R14 | 严格模式下摘录复用升为错误 |
| `check-vocab-outliers.md/.json` | `--ledger …` | 0（警告） | R0 | `未经官方核实`／`尚未经官方核对`／`未能与官方原文核对`／`未完成核对`／`核对中`／`待核` 六种写法都按未核处理，并提示写法不在词表内 |
| `official-nodomain.md/.json` | `--ledger …` | 1 | R18 | 渠道写「官方」但出处只有「第 1 页」，无官方链接 |
| `export-from-official.md/.json` | `--ledger …` | 0 | — | 官方站点下载的导出件：渠道「导出」＋出处官方链接＋已核，三者齐备 |
| `export-from-bjcourt.md/.json` | `--ledger …` | 0 | — | 北京法院网下载的判决书导出件，渠道「导出」＋官方链接＋已核，三段齐备 |
| `export-from-commercial.md/.json` | `--ledger …` | 1 | R18 | 北大法宝导出的判决书写「已核」，仍要拦 |
| `official-root-only.md/.json` | `--ledger …` | 1 | R2×3 | 出处只有官方主机名或根路径（`https://www.spp.gov.cn/`、`https://bjcourt.gov.cn`、`https://www.bjcourt.gov.cn/`），按「出处不具体」报错；域名合规不进 R18 |
| `pending-original.md/.json` | `--ledger …` | 0 | R15（警告） | 检察/法院站点两次 502 后降为待取正文，未换镜像；回读栏写「待取正文（2026-11-09：两次 502）」 |
| `official-nonwhitelist.md/.json` | `--ledger …` | 1 | R18 ×2 | 渠道写「官方」但出处在 pkulaw.com／lexiscn.com；`flk.npc.gov.cn` 属白名单不报 |
| `foreign-empty-check.md/.json` | `--ledger …` | 0（警告） | R0 | 非官方渠道（商业库／用户导出件）官方复核留空：计入「未核 3 条」，不报 R2／R18 |
| `commercial-affirmative-nonuclear.md/.json` | `--ledger …` | 1 | R18 ×6 | 商业库 + 不含「核」字的肯定写法（`已比对一致`／`与官方原文一致`／`已验证`／`已确认`／`已查证`／`一致`）全部报错，并进「未核 6 条」汇总 |
| `commercial-verified-outofvocab.md/.json` | `--ledger …` | 1 | R18 | 商业库 + 词表外肯定写法「基本核实」：归一记未核，但仍算已核声称，报 R18 |
| `commercial-unverified-variants.md/.json` | `--ledger …` | 0（警告） | R0 | `未核（仅商业库或转载）`／`未经核实`／`未能核实`／`尚未核` 都归为未核，不得报 R18 |
| `future-reread.md/.json` | `--ledger …` | 1 | R15 | 回读日期写成 2099 年，晚于运行当天 |
| `offline-draft.md` | `--mode offline` | 0 | — | 合规离线草稿 |
| `offline-draft-negative.md` | `--mode offline` | 0 | — | 「不是可交付稿」「无一条已核实」不算声称 |
| `offline-draft-contrast.md` | `--mode offline` | 1 | R17 | 「未经联网回读，但引用均已核实」跨分句，属肯定声称 |
| `offline-draft-nomark.md` | `--mode offline` | 1 | R17 | 缺〔草稿〕标注 |
| `homepage-count-mismatch.md` | 无 | 1 | R19 ×2 | 首页写「共 14 项问题、必改 7 项」，风险表 13 行、必改清单 6 行；数字须由表计数 |
| `homepage-count-ok.md` | 无 | 0 | — | 首页 13 项（5 高／7 中／1 低）、必改 6 项，与两张表一致 |
| `clause-ref-missing.md` | 无 | 0（警告） | R20 | 替换条款引用第 7.3 条，原合同与映射表都没有 |
| `clause-ref-missing.md` | `--strict` | 1 | R20 | 严格模式下引用不存在的编号报错 |
| `clause-ref-missing.md` | `--strict --contract contract-clause-index.txt` | 0 | — | 原合同目录含 7.3，引用成立 |
| `clause-map-ok.md` | `--strict` | 0 | — | 附「原编号／新编号／说明」映射表，引用可回溯 |
| `conclusion-unsourced.md` | 无 | 0（警告） | R21 | 风险表「不发生效力」的分句未就近挂编号→提示「该句未就近挂编号；若同行他栏已引用，请确认该编号确实支持这句结论」；有编号、「」内原文、写了「法律判断待核」的行不提示 |
| `pending-material.md` | 无 | 0（警告） | — | 材料目录写「待补材料」并列 E- 编号，不得判为词表外写法；「待取正文」另表 |
| `conditional-risk-count.md` | 无 | 0 | — | 首页「确定 3 项＋条件式 2 项」与风险表一致，条件式行均链 E- 编号 |
| `conditional-risk-mismatch.md` | 无 | 1 | R19 ×2 | 首页写确定 4／条件式 1，表内实为 3／2 |
| `inline-ledger-dedup.md` | 无 | 0（警告） | R0 | 同一编号在风险表被引用 3 次、底稿表 1 条：只算 2 条（N-01、N-02） |
| `trial-blind-review.md` | 无 | 1 | R19 ×3（另 R20／R21 为警告） | 一次试跑的写法合集：首页手填数字、替换条款引用不存在的 7.3、结论无编号、条件式风险 |
| `source-url-official.md/.json` | `--ledger …` | 0 | — | 出处写在 `source_url` 字段，R18 应认得，不得报「渠道官方却无链接」 |
| `homepage-conditional-wording.md` | 无 | 0 | — | 首页「中风险 2 项（含 2 项条件式）」＋「条件式（待补材料）2 项」，不得把后面的「低风险 3 项」读成条件式数 |
