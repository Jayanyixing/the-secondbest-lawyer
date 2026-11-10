#!/usr/bin/env python3
"""回溯评测汇总：读分数 CSV，算均分、阻断率，给结论档位。

用法：
    python3 tools/eval_score.py eval/scores.csv
    python3 tools/eval_score.py eval/scores.csv --min-cases 10

CSV 列：case_id,case_type,d1_facts,d2_citations,d3_time,d4_risk,d5_usability,d6_boundary,blocker,notes
分数 0-3；blocker 为 1 表示出现阻断项（该案记 0，不参与均分）。
无第三方依赖。
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

DIMS = ["d1_facts", "d2_citations", "d3_time", "d4_risk", "d5_usability", "d6_boundary"]
NAMES = {
    "d1_facts": "事实准确",
    "d2_citations": "引用可追溯",
    "d3_time": "时点适用",
    "d4_risk": "不利面覆盖",
    "d5_usability": "交付可用",
    "d6_boundary": "边界诚实",
}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="评测分数汇总")
    ap.add_argument("csv_path", type=Path)
    ap.add_argument("--min-cases", type=int, default=10, help="少于这个数不出结论，默认 10")
    args = ap.parse_args(argv)

    if not args.csv_path.exists():
        print(f"找不到 {args.csv_path}", file=sys.stderr)
        return 2

    rows = list(csv.DictReader(args.csv_path.open(encoding="utf-8-sig")))
    rows = [r for r in rows if (r.get("case_id") or "").strip()]
    if not rows:
        print("没有有效数据行", file=sys.stderr)
        return 2

    blocked, scored = [], []
    for r in rows:
        if str(r.get("blocker", "0")).strip().lower() in ("1", "true", "yes", "y", "是"):
            blocked.append(r["case_id"])
        else:
            scored.append(r)

    totals = {d: 0.0 for d in DIMS}
    for r in scored:
        for d in DIMS:
            try:
                totals[d] += float(r.get(d, 0) or 0)
            except ValueError:
                pass
    n = len(scored) or 1
    means = {d: totals[d] / n for d in DIMS}
    overall = sum(means.values()) / len(DIMS)

    print(f"样本：{len(rows)} 件（阻断 {len(blocked)} 件）")
    if blocked:
        print(f"阻断案件：{', '.join(blocked)}  → 阻断率 {len(blocked)/len(rows):.0%}")
    print("\n维度均分：")
    for d in DIMS:
        bar = "█" * int(round(means[d] * 5))
        print(f"  {NAMES[d]:<6} {means[d]:.2f}  {bar}")
    print(f"\n总分：{overall:.2f}")

    if len(rows) < args.min_cases:
        print(f"\n仅 {len(rows)} 件，样本不足（建议 ≥{args.min_cases} 件），暂不出结论。")
        return 0

    if blocked:
        verdict, code = "不可用：存在阻断项（编造引用／事实／状态）", 1
    elif overall >= 2.6:
        verdict, code = "可推荐给同事使用", 0
    elif overall >= 2.2:
        verdict, code = "可用，但需律师逐份复核", 0
    elif overall >= 1.8:
        verdict, code = "仅作初稿，需大改", 1
    else:
        verdict, code = "不可用，回炉", 1

    weakest = min(DIMS, key=lambda d: means[d])
    print(f"\n结论：{verdict}")
    print(f"最弱维度：{NAMES[weakest]}（{means[weakest]:.2f}）")
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
