# 卡片摘录核验记录 · 第五批（买卖合同组开组，2026-11-09）

> 偏移以 `templates/snapshots/` 下的文本快照为基准计算，快照文件与哈希一并留存，可离线复算。

## 快照

| 快照文件 | 字数 | sha256(前16位) | 来源 |
| --- | --- | --- | --- |
| snap-2026-11-08-csj典型案例.txt | 44772 | 6f763a259b59909b | https://www.court.gov.cn/zixun/xiangqing/400542.html |
| snap-2026-11-08-xunhui1质量异议.txt | 5226 | fd72169d9b79c438 | https://www.court.gov.cn/xunhui1/xiangqing/282341.html |

## 逐卡核验

| 条号 | kind | 字数 | 快照 | 偏移 | 命中 | 前置上下文 |
| --- | --- | --- | --- | --- | --- | --- |
| （2018）浙0281民初XXX号 | judgment | 45 | snap-2026-11-08-csj典型案例.txt | 9039 | ✓ | 际损失/公平原则裁判要旨1. |
| （2018）浙0281民初XXX号 | judgment | 59 | snap-2026-11-08-csj典型案例.txt | 9179 | ✓ | 为其已经完成了房屋交付。2. |
| 最高人民法院第一巡回法庭法官会议纪要（合 | rule | 26 | snap-2026-11-08-xunhui1质量异议.txt | 980 | ✓ | 不符合约定的情形通知出卖人。 |

## 复算方法

```
python3 -c "import sys;t=open(sys.argv[1]).read();print(t.find(sys.argv[2]))" snap-xxx.txt "摘录原文"
```
