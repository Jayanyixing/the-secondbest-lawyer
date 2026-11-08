#!/usr/bin/env python3
"""按采购要求匹配业绩：谁能用、谁要授权、缺几项。

「差一项要不要编」这个问题的根在于业绩散在各人手里、没人算过到底有几项可用。本工具读
业绩库，按年份、关键词、金额筛，并按授权状态分三类输出。缺口由匹配算出，不由人临时回忆。

只做匹配，不判可比性：某项目是否属于「同类」，评委有裁量，最终以证明材料能否自证为准。

用法：
    python3 tools/tender_credits.py --credits data/credits.json --need 3 \
        --years 2022-2025 --keyword 建设工程 --keyword 诉讼
    python3 tools/tender_credits.py --credits data/credits.json --need 3 --json

退出码：0 满足；1 不满足（缺口）。无第三方依赖。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def year_of(credit: dict) -> int | None:
    y = credit.get("year")
    try:
        return int(str(y)[:4])
    except (TypeError, ValueError):
        return None


def haystack(credit: dict) -> str:
    parts = [str(credit.get(k, "")) for k in ("project", "client", "role", "auth_note")]
    parts += [str(x) for x in credit.get("scope", []) or []]
    return " ".join(parts)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="按采购要求匹配业绩")
    ap.add_argument("--credits", type=Path, default=Path("data/credits.json"), help="业绩库 JSON")
    ap.add_argument("--need", type=int, default=1, help="采购文件要求的业绩数量")
    ap.add_argument("--years", help="年份区间，如 2022-2025")
    ap.add_argument("--keyword", action="append", default=[], help="匹配关键词，可多次")
    ap.add_argument("--min-amount", type=float, default=0.0, help="单份业绩最低金额（元）")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = ap.parse_args(argv)

    if not args.credits.exists():
        print(f"找不到业绩库：{args.credits}（从 data/credits.example.json 复制后填写）", file=sys.stderr)
        return 2
    data = json.loads(args.credits.read_text("utf-8"))
    credits = data.get("credits", data if isinstance(data, list) else [])

    lo = hi = None
    if args.years:
        try:
            lo_s, hi_s = args.years.split("-")
            lo, hi = int(lo_s), int(hi_s)
        except ValueError:
            print("--years 格式应为 2022-2025", file=sys.stderr)
            return 2

    usable: list[dict] = []
    need_auth: list[dict] = []
    rejected: list[dict] = []
    for c in credits:
        reasons = []
        y = year_of(c)
        if lo and (y is None or not lo <= y <= hi):
            reasons.append(f"年份不符（{y}）")
        if args.keyword:
            text = haystack(c)
            if not any(k in text for k in args.keyword):
                reasons.append("关键词不匹配")
        amount = c.get("amount")
        if args.min_amount and (amount is None or float(amount) < args.min_amount):
            reasons.append("金额不足或未知")
        use = str(c.get("credits_use", "")).strip()
        if use == "no":
            reasons.append("已标记不可用")
        if reasons:
            rejected.append({**c, "reasons": reasons})
        elif use == "need_auth":
            need_auth.append(c)
        else:
            usable.append(c)

    satisfied = len(usable) + len(need_auth)
    gap = max(0, args.need - satisfied)

    out = {
        "需求数量": args.need,
        "可用": [{"id": c.get("id"), "project": c.get("project"), "year": c.get("year")} for c in usable],
        "需授权": [{"id": c.get("id"), "project": c.get("project"), "auth_note": c.get("auth_note")} for c in need_auth],
        "不符合": [{"id": c.get("id"), "reasons": c["reasons"]} for c in rejected],
        "缺口": gap,
        "结论": "满足" if gap == 0 else f"缺 {gap} 项",
    }

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0 if gap == 0 else 1

    print(f"要求 {args.need} 项｜可用 {len(usable)}｜需授权 {len(need_auth)}｜不符合 {len(rejected)}")
    for c in usable:
        print(f"  [可用] {c.get('id')} {c.get('project')}（{c.get('year')}）")
    for c in need_auth:
        print(f"  [需授权] {c.get('id')} {c.get('project')}——{c.get('auth_note') or '先取书面同意'}")
    for c in rejected:
        print(f"  [不符合] {c.get('id')}：{'；'.join(c['reasons'])}")
    if gap:
        print(f"结论：缺 {gap} 项。缺口照实写，附对资格或分值的影响；不得补造项目、客户或印章。")
    else:
        print("结论：数量满足。仍需核对证明材料能看出主体与角色。")
    return 0 if gap == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
