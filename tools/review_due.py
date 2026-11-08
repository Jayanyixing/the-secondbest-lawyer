#!/usr/bin/env python3
"""检查 MAINTENANCE.md 里的复查到期项。

用法：
    python3 tools/review_due.py            # 30 天内到期也提醒
    python3 tools/review_due.py --days 60

读 MAINTENANCE.md 中「对象 | 周期(月) | 上次核实 | 下次到期」表格。
有已逾期项时返回退出码 1。无第三方依赖。
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAINT = ROOT / "MAINTENANCE.md"
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def parse_rows(text: str) -> list[dict]:
    rows, header = [], None
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            header = None
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if header is None:
            header = cells
            continue
        if all(set(c) <= set("-: ") for c in cells):
            continue
        row = dict(zip(header, cells))
        target = row.get("对象", "")
        due = row.get("下次到期", "")
        if target and DATE_RE.fullmatch(due or ""):
            rows.append({"target": target, "due": due})
    return rows


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="复查到期检查")
    ap.add_argument("--days", type=int, default=30, help="提前多少天提醒，默认 30")
    ap.add_argument("--today", help="覆盖今天日期（测试用），格式 YYYY-MM-DD")
    args = ap.parse_args(argv)

    if not MAINT.exists():
        print("找不到 MAINTENANCE.md", file=sys.stderr)
        return 2

    today = datetime.strptime(args.today, "%Y-%m-%d").date() if args.today else date.today()
    rows = parse_rows(MAINT.read_text(encoding="utf-8"))
    if not rows:
        print("MAINTENANCE.md 里没有解析到复查表", file=sys.stderr)
        return 2

    overdue, soon, ok = [], [], []
    for r in rows:
        due = datetime.strptime(r["due"], "%Y-%m-%d").date()
        delta = (due - today).days
        (overdue if delta < 0 else soon if delta <= args.days else ok).append((delta, r))

    print(f"复查基准日：{today}")
    for delta, r in sorted(overdue, key=lambda x: x[0]):
        print(f"  ✗ 已逾期 {abs(delta)} 天  {r['target']}（到期 {r['due']}）")
    for delta, r in sorted(soon, key=lambda x: x[0]):
        print(f"  ! {delta} 天后到期  {r['target']}（{r['due']}）")
    print(f"  正常 {len(ok)} 项")
    print(f"\n合计 {len(rows)} 项：逾期 {len(overdue)}／预警 {len(soon)}／正常 {len(ok)}")
    return 1 if overdue else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
