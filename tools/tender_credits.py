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
import re
import sys
from pathlib import Path


def year_of(credit: dict) -> int | None:
    raw = credit.get("year")
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return 2000 + int(raw) if 0 <= raw < 100 else int(raw)
    s = str(raw).strip()
    m = re.search(r"(?:19|20)\d{2}", s)
    if m:
        return int(m.group(0))
    m = re.fullmatch(r"(\d{1,2})", s)
    if m:
        return 2000 + int(m.group(1))
    try:
        return int(s)
    except ValueError:
        return None


def money(value) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().replace(",", "").replace("，", "")
    s = s.replace("人民币", "").replace("￥", "").replace("¥", "").strip()
    m = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*(万元|万|元)?", s)
    if not m:
        return None
    v = float(m.group(1))
    return round(v * 10_000, 2) if m.group(2) in ("万元", "万") else round(v, 2)


def haystack(credit: dict) -> str:
    parts = [str(credit.get(k, "")) for k in ("project", "client", "role", "auth_note")]
    scope = credit.get("scope", [])
    if isinstance(scope, str):
        parts.append(scope)
    else:
        parts += [str(x) for x in scope or []]
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
    if args.need < 1:
        ap.error("--need 必须是正整数")
    if args.min_amount < 0:
        ap.error("--min-amount 不能为负")

    if not args.credits.exists():
        print(f"找不到业绩库：{args.credits}（从 data/credits.example.json 复制后填写）", file=sys.stderr)
        return 2
    try:
        data = json.loads(args.credits.read_text("utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"读取业绩库失败：{exc}", file=sys.stderr)
        return 2
    if isinstance(data, list):
        credits = data
    elif isinstance(data, dict):
        credits = data.get("credits", [])
    else:
        print("业绩库顶层必须是数组或含 credits 数组的对象", file=sys.stderr)
        return 2
    if not isinstance(credits, list):
        print("业绩库「credits」必须是数组", file=sys.stderr)
        return 2

    lo = hi = None
    if args.years:
        try:
            lo_s, hi_s = args.years.split("-", 1)
            lo, hi = int(lo_s), int(hi_s)
        except ValueError:
            print("--years 格式应为 2022-2025", file=sys.stderr)
            return 2
        if lo > hi:
            print("--years 起始年份不能大于结束年份", file=sys.stderr)
            return 2

    usable: list[dict] = []
    need_auth: list[dict] = []
    rejected: list[dict] = []
    for c in credits:
        if not isinstance(c, dict):
            rejected.append({"id": None, "reasons": ["条目不是对象"]})
            continue
        reasons = []
        y = year_of(c)
        if lo is not None and (y is None or not lo <= y <= hi):
            reasons.append(f"年份不符（{y}）")
        if args.keyword:
            text = haystack(c)
            if not any(k in text for k in args.keyword):
                reasons.append("关键词不匹配")
        amount = money(c.get("amount"))
        if args.min_amount and (amount is None or amount < args.min_amount):
            reasons.append("金额不足或格式无法识别")
        use = str(c.get("credits_use", "")).strip().lower()
        if use in ("no", "不可用", "否", "禁用", "不能"):
            reasons.append("已标记不可用")
        if reasons:
            rejected.append({**c, "reasons": reasons})
        elif use in ("need_auth", "需授权", "待授权", "需业主同意", "需书面同意"):
            need_auth.append(c)
        else:
            usable.append(c)

    # 退出码只看“已授权可用”的数量：需授权项即使够数，也不能算已满足。
    auth_gap = max(0, args.need - len(usable))
    total_gap = max(0, args.need - len(usable) - len(need_auth))
    if auth_gap == 0:
        conclusion = "满足"
    elif total_gap == 0:
        conclusion = f"需补齐授权后方可满足，当前已授权业绩不足（已授权缺 {auth_gap} 项）"
    else:
        conclusion = f"已授权缺 {auth_gap} 项（即使计入需授权项仍缺 {total_gap} 项）"

    out = {
        "需求数量": args.need,
        "可用": [{"id": c.get("id"), "project": c.get("project"), "year": c.get("year")} for c in usable],
        "需授权": [{"id": c.get("id"), "project": c.get("project"), "auth_note": c.get("auth_note")} for c in need_auth],
        "不符合": [{"id": c.get("id"), "reasons": c["reasons"]} for c in rejected],
        "缺口": auth_gap,
        "计入需授权后缺口": total_gap,
        "结论": conclusion,
    }

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0 if auth_gap == 0 else 1

    print(f"要求 {args.need} 项｜可用 {len(usable)}｜需授权 {len(need_auth)}｜不符合 {len(rejected)}")
    for c in usable:
        print(f"  [可用] {c.get('id')} {c.get('project')}（{c.get('year')}）")
    for c in need_auth:
        print(f"  [需授权] {c.get('id')} {c.get('project')}——{c.get('auth_note') or '先取书面同意'}")
    for c in rejected:
        print(f"  [不符合] {c.get('id')}：{'；'.join(c['reasons'])}")
    if auth_gap:
        print(f"结论：{conclusion}。缺口照实写，附对资格或分值的影响；不得补造项目、客户或印章。")
    else:
        print("结论：数量满足。仍需核对证明材料能看出主体与角色。")
    return 0 if auth_gap == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
