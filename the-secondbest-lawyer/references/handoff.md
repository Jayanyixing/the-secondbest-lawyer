# 案件任务与交接模板

用于手工交接，或交给新会话／子代理做独立复核。**只传完成任务必需的信息**；未知字段留待核。

关键点：独立复核时，接收方只拿成品、原材料目录、引用底稿和本卡片，**不拿作者的推理过程与过程稿**，否则不构成独立。

## 文本版

```text
事项编号｜任务编号｜版本｜生成日期（北京时区）
交出角色 → 接收角色
模式：自查 / 有限复核 / 独立复核
服务对象｜代理立场｜利益冲突线索
要回答的问题｜指定交付物与格式
办理地区｜机关｜程序阶段｜程序轨道（民事／刑事／行政／执行）
事实发生时点｜适用法时点｜检索截止日
截止时间｜期限类型｜起算凭据（有／无，具体文书）
授权范围｜允许的外部动作（发送／提交／联系／查询）
保密范围｜禁止跨案使用的信息｜脱敏状态

已知事实
- [F-01] 内容｜材料记载/当事人陈述/推断/待查｜来源与页码

材料目录
- [E-01] 文件名｜版本｜原件/复印件｜取得来源｜起止页｜可读性

引用底稿摘要
- [N-01] 全称｜条款｜制定机关｜公布/施行｜效力｜定位｜摘录｜读取范围｜回读｜复核状态
- [C-01] 案名｜案号｜法院｜裁判日期｜审级｜类别｜定位｜摘录｜读取范围｜回读｜复核状态｜生效状态

已完成动作与凭据
未执行的建议动作
关键矛盾｜不利材料｜资料缺口
本轮结论与限制
下一步｜主责｜需决策或补充事项
复核范围｜复核者｜状态（自查不可写独立复核）
```

## JSON 版（需要程序化交接时）

```json
{
  "matter_id": "",
  "version": "",
  "as_of": "YYYY-MM-DD",
  "mode": "self_check | limited_review | independent_review",
  "stance": "",
  "questions": [],
  "track": "civil | criminal | administrative | enforcement",
  "stage": "",
  "fact_time": "",
  "law_time": "",
  "deadline": {
    "status": "verified | conditional | pending",
    "date": "",
    "assumptions": [],
    "evidence_of_start": ""
  },
  "authorization": {"outbound_actions": [], "scope": ""},
  "facts": [{"id": "F-01", "text": "", "basis": "record|statement|inference|unknown", "source": ""}],
  "materials": [{"id": "E-01", "file": "", "version": "", "pages": "", "readability": ""}],
  "citations": [{"id": "C-01", "type": "", "number": "", "court": "", "date": "", "level": "",
                 "channel": "official|commercial|user_export|oral",
                 "location": "", "quote": "逐字原文 8-60 字", "reread": "已回读（YYYY-MM-DD）| 未回读",
                 "read_scope": "full|excerpt|abstract|title|none",
                 "official_check": "verified|unverified|na",
                 "effectiveness": "effective|unconfirmed|subsequent"}],
  "actions_done": [], "actions_not_done": [],
  "gaps": [], "review": {"scope": "", "reviewer": "", "status": ""}
}
```

## 规则

- 依据附全称／案号、机关或法院、日期、效力或生效状态；案例另附审级与事实差异。
- 敏感个人信息不因模板留有字段就默认全收集。
- 交接后的新材料与实质修改形成新版本，写明改变了哪些事实、引用、金额、期限与结论；旧版复核不自动套用到新版。
