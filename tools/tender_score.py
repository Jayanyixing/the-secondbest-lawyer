#!/usr/bin/env python3
"""投标评分自评与价格分测算。

法律服务采购的得分结构固定（价格分 + 方案 + 团队 + 业绩 + 本地化），但价格分三种算法
结果差别很大：最低价法降价换分快，基准价法降过头反而扣分，固定价比价无意义。
本工具按同一份自评表算三种情况，并给出「降价边际」——降多少分换多少钱，值不值。

只算算术，不判胜负：对手报价是假设，评委打分不可预测。别把测算结果当承诺。

用法：
    python3 tools/tender_score.py 自评.json
    python3 tools/tender_score.py 自评.json --json
    python3 tools/tender_score.py 自评.json --k 1.5      # 基准价法偏离扣分系数

退出码：0 正常；1 发现硬伤（超最高限价等）。无第三方依赖。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def price_score(our: float, others: list[float], full: float, method: str, k: float) -> float:
    pool = [our] + [o for o in others if o > 0]
    if method == "固定价":
        return full
    if method == "最低价":
        low = min(pool)
        return round(full * low / our, 2) if our > 0 else 0.0
    # 基准价：去极值均价为基准，每偏离 1% 扣 k 分（按分值折算）
    base = sum(pool) / len(pool)
    if base <= 0:
        return 0.0
    deviation = abs(our - base) / base
    return round(max(0.0, full * (1 - k * deviation * 10)), 2)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="投标评分自评与价格分测算")
    ap.add_argument("sheet", type=Path, help="自评 JSON")
    ap.add_argument("--k", type=float, default=1.0, help="基准价法扣分系数（默认 1.0）")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = ap.parse_args(argv)

    data = json.loads(args.sheet.read_text("utf-8"))
    our = float(data.get("投标价", 0))
    cap = data.get("最高限价")
    budget = data.get("预算")
    price_cfg = data.get("价格分", {})
    full = float(price_cfg.get("分值", 30))
    method = price_cfg.get("方法", "最低价")
    others = [float(x) for x in data.get("对手价", [])]
    items = data.get("评分项", [])
    rival_other = float(data.get("对手非价格分", 0))

    problems: list[str] = []
    notes: list[str] = []
    if cap and our > float(cap):
        problems.append(f"投标价 {our:,.0f} 超最高限价 {float(cap):,.0f}——按无效投标处理，先改价再报")
    if budget and our > float(budget) and not (cap and our > float(cap)):
        notes.append(f"投标价超预算 {float(budget):,.0f}，确认采购文件是否允许超预算报价")
    if budget and our < float(budget) * 0.5:
        notes.append(f"投标价低于预算 {our / float(budget):.0%}，核对工时成本与履约可行性")

    ours_price = price_score(our, others, full, method, args.k)
    self_other = sum(float(i.get("自评", 0)) for i in items)
    full_other = sum(float(i.get("分值", 0)) for i in items)
    our_total = ours_price + self_other

    rivals = []
    for o in others:
        ps = price_score(o, [our] + [x for x in others if x != o], full, method, args.k)
        rivals.append({"报价": o, "价格分": ps, "总分": round(ps + rival_other, 2)})
    rivals.sort(key=lambda r: -r["总分"])

    weak = [i for i in items if float(i.get("自评", 0)) < float(i.get("分值", 0)) * 0.7]

    # 降价边际：按当前方法算降 5% / 10% 的价格分变化
    margins = []
    for cut in (0.03, 0.05, 0.10):
        new_price = our * (1 - cut)
        new_ps = price_score(new_price, others, full, method, args.k)
        margins.append({"降幅": cut, "让价": our - new_price,
                        "价格分": new_ps, "增加": round(new_ps - ours_price, 2)})

    result = {
        "项目": data.get("项目", ""),
        "价格分方法": method,
        "价格分": ours_price,
        "非价格得分": self_other,
        "非价格总分": full_other,
        "总分": round(our_total, 2),
        "对手": rivals,
        "需争取项": [{"名称": i.get("名称"), "分值": i.get("分值"), "自评": i.get("自评")} for i in weak],
        "降价边际": margins,
        "硬伤": problems,
        "提示": notes,
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if problems else 0

    print(f"项目：{result['项目'] or '（未填）'}｜价格分方法：{method}")
    print(f"价格分 {ours_price}（满分 {full:g}）＋ 非价格 {self_other:g}/{full_other:g} = 总分 {our_total:.2f}")
    if rivals:
        print("对手假设：")
        for r in rivals:
            print(f"  {r['报价']:>12,.0f} 元  价格分 {r['价格分']:>5.2f}  总分 {r['总分']:>6.2f}")
    if weak:
        print("需争取项（自评低于该项 70%）：")
        for i in weak:
            print(f"  - {i.get('名称')}：{i.get('自评')}/{i.get('分值')}")
    print("降价边际：")
    for m in margins:
        print(f"  降 {m['降幅']:.0%}（让价 {m['让价']:,.0f} 元）→ 价格分 {m['价格分']:g}（{m['增加']:+.2f}）")
    for p in problems:
        print(f"[错误] {p}")
    for n in notes:
        print(f"[提示] {n}")
    print("提示：对手报价为假设，评委打分不可预测；测算不等于中标概率。")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
