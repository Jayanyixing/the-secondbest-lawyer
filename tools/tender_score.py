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
import re
import sys
from pathlib import Path


def to_float(value, default: float | None = 0.0) -> float | None:
    """把数字/“100万”/“1,000,000 元”统一成元；无法识别时抛 ValueError。"""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().replace(",", "").replace("，", "")
    s = s.replace("人民币", "").replace("￥", "").replace("¥", "").strip()
    m = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*(万元|万|元)?", s)
    if not m:
        raise ValueError(f"无法识别的金额：{value!r}")
    v = float(m.group(1))
    return round(v * 10_000, 2) if m.group(2) in ("万元", "万") else round(v, 2)


def base_price(pool: list[float], trim: bool = False) -> tuple[float, bool]:
    valid = [p for p in pool if p > 0]
    if not valid:
        return 0.0, False
    trimmed = False
    if (trim or len(valid) >= 4) and len(valid) >= 3:
        valid = sorted(valid)[1:-1]
        trimmed = True
    return sum(valid) / len(valid), trimmed


def price_score(our: float, others: list[float], full: float, method: str, k: float,
                trim: bool = False, meta: dict | None = None) -> float:
    pool = [our] + [o for o in others if o > 0]
    if method == "固定价":
        return round(full, 2)
    if method == "最低价":
        low = min(pool) if pool else 0.0
        return round(full * low / our, 2) if our > 0 else 0.0
    base, trimmed = base_price(pool, trim)
    if meta is not None:
        meta.update({"base": base, "trimmed": trimmed, "pool_size": len(pool),
                     "includes_self": our > 0, "trim_requested": trim})
    if base <= 0:
        return 0.0
    deviation = abs(our - base) / base
    # 每偏离 1% 扣 k 分：deviation 是小数，乘 100 换成百分点。
    return round(max(0.0, full - k * (deviation * 100)), 2)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="投标评分自评与价格分测算")
    ap.add_argument("sheet", type=Path, help="自评 JSON")
    ap.add_argument("--k", type=float, default=1.0, help="基准价法扣分系数（默认 1.0）")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = ap.parse_args(argv)
    if args.k < 0:
        ap.error("--k 不能为负")

    try:
        data = json.loads(args.sheet.read_text("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("自评 JSON 顶层必须是对象")
        our = to_float(data.get("投标价", 0))
        cap = to_float(data.get("最高限价"), None)
        budget = to_float(data.get("预算"), None)
        price_cfg = data.get("价格分") or {}
        if not isinstance(price_cfg, dict):
            raise ValueError("「价格分」必须是对象")
        full = to_float(price_cfg.get("分值", 30), 30.0)
        method = str(price_cfg.get("方法", "最低价")).strip() or "最低价"
        trim_cfg = bool(price_cfg.get("去极值", False))
        others_raw = data.get("对手价") or []
        if not isinstance(others_raw, list):
            raise ValueError("「对手价」必须是数组")
        others = [x for x in (to_float(v) for v in others_raw) if x and x > 0]
        items = data.get("评分项") or []
        if not isinstance(items, list):
            raise ValueError("「评分项」必须是数组")
        rival_other = to_float(data.get("对手非价格分", 0))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"读取自评表失败：{exc}", file=sys.stderr)
        return 2
    if not full or full <= 0:
        print("「价格分.分值」必须大于 0", file=sys.stderr)
        return 2
    if our is None or our <= 0:
        print("「投标价」必须大于 0", file=sys.stderr)
        return 2

    problems: list[str] = []
    notes: list[str] = []
    if cap is not None and cap <= 0:
        problems.append("最高限价配置为 0 或负数，无法判断是否超限，请核对自评表")
    elif cap is not None and our > cap:
        problems.append(f"投标价 {our:,.0f} 超最高限价 {cap:,.0f}——按无效投标处理，先改价再报")
    if budget is not None and budget > 0 and our > budget and not (cap is not None and cap > 0 and our > cap):
        notes.append(f"投标价超预算 {budget:,.0f}，确认采购文件是否允许超预算报价")
    if budget is not None and budget > 0 and our < budget * 0.5:
        notes.append(f"投标价低于预算 {our / budget:.0%}，核对工时成本与履约可行性")
    if method not in ("固定价", "最低价", "基准价"):
        notes.append(f"未知价格分方法「{method}」，暂按基准价法测算")

    price_meta: dict = {}
    ours_price = price_score(our, others, full, method, args.k, trim_cfg, price_meta)
    self_other = sum(to_float(i.get("自评", 0)) for i in items if isinstance(i, dict))
    full_other = sum(to_float(i.get("分值", 0)) for i in items if isinstance(i, dict))
    our_total = ours_price + self_other

    rivals = []
    for idx, o in enumerate(others):
        # 按位置剔除自己：同价对手不能被 x != o 一并删掉
        pool = [our] + others[:idx] + others[idx + 1:]
        ps = price_score(o, pool, full, method, args.k, trim_cfg)
        rivals.append({"报价": o, "价格分": ps, "总分": round(ps + rival_other, 2)})
    rivals.sort(key=lambda r: -r["总分"])

    weak = [i for i in items
            if isinstance(i, dict) and to_float(i.get("自评", 0)) < to_float(i.get("分值", 0)) * 0.7]

    # 降价边际：按当前方法算降 3% / 5% / 10% 的价格分变化
    margins = []
    for cut in (0.03, 0.05, 0.10):
        new_price = our * (1 - cut)
        new_ps = price_score(new_price, others, full, method, args.k, trim_cfg)
        margins.append({"降幅": cut, "让价": our - new_price,
                        "价格分": new_ps, "增加": round(new_ps - ours_price, 2)})

    base_note = ""
    if price_meta.get("base", 0) > 0:
        base_note = (f"基准价 {price_meta['base']:.2f}（{price_meta['pool_size']} 家，含本家，"
                     f"{'已去极值' if price_meta['trimmed'] else '未去极值（不足4家）'}）")
    result = {
        "项目": data.get("项目", ""),
        "价格分方法": method,
        "价格分": ours_price,
        "基准价口径": base_note or "不适用",
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
    if base_note:
        print(f"基准价口径：{base_note}")
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
