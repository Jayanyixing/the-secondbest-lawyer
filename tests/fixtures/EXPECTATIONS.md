# 对抗样例与期望结果

每个样例都写明期望的退出码与命中规则。跑法：

```bash
python3 tools/citation_lint.py tests/fixtures/<名>.md [--ledger tests/fixtures/<名>.json] [--mode offline] [--strict]
```

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
