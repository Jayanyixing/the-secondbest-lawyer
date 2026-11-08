# 本地法条库数据目录

`law.sqlite` 由 `tools/lawdb.py init` 生成，**不入库**（体积与许可原因）。

导入来源只用官方渠道，见 `references/data-supply.md`：

```bash
python3 tools/lawdb.py init
python3 tools/lawdb.py import <官方下载的法规文件> --name <法规全称> \
  --issuer <制定机关> --publish <公布日> --effective <施行日> \
  --url <具体页面链接> --official-check 已核
```

导出文件被替换或修订时，`python3 tools/lawdb.py verify` 会报警，重新导入同名法规即可覆盖。
