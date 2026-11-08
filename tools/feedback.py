#!/usr/bin/env python3
"""失败信号登记：把每次检索/复核暴露的问题变成结构化数据。

自提升的前提是「失败可积累」。聊天里说过的“这张召回不了”“这条写错了”，
第二天就忘了；写成一行 JSON 才能被聚类、被提案、被回归测试。

用法：
    python3 tools/feedback.py add --type miss --query "追加 被执行人" --note "应命中 79 号卡"
    python3 tools/feedback.py add --type wrong_citation --card 108 --note "key_point 多出条文没有的前提"
    python3 tools/feedback.py list --since 2026-11-01
    python3 tools/feedback.py stats
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "data" / "feedback.jsonl"

TYPES = {
    "miss": "该召回没召回（同义词、标签、卡片缺）",
    "unusable": "召回了但用不上（key_point 不够可执行、争点偏）",
    "wrong_citation": "引文/条号/前提写错",
    "gap": "库里确实没有（来源缺口，不是检索问题）",
    "slow": "流程太慢或步骤太多",
}


def cmd_add(args) -> int:
    if args.type not in TYPES:
        print(f"type 须为：{', '.join(TYPES)}", file=sys.stderr)
        return 2
    rec = dict(date=date.today().isoformat(), type=args.type,
               query=args.query or "", card=args.card or "", case=args.case or "",
               note=args.note or "")
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"已登记：{rec['type']} | {rec['query'] or rec['card'] or '-'}")
    return 0


def load() -> list[dict]:
    if not LOG.exists():
        return []
    return [json.loads(x) for x in LOG.read_text(encoding="utf-8").splitlines() if x.strip()]


def cmd_list(args) -> int:
    rows = [r for r in load() if not args.since or r["date"] >= args.since]
    for r in rows:
        print(f"{r['date']} [{r['type']:<14}] {r.get('query') or r.get('card') or '-'} | {r.get('note','')[:50]}")
    print(f"\n共 {len(rows)} 条")
    return 0


def cmd_stats(args) -> int:
    rows = load()
    c = Counter(r["type"] for r in rows)
    print(f"累计 {len(rows)} 条失败信号")
    for k, v in c.most_common():
        print(f"  {k:<15} {v:>3}  {TYPES.get(k,'')}")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="失败信号登记")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add"); a.add_argument("--type", required=True)
    a.add_argument("--query"); a.add_argument("--card"); a.add_argument("--case"); a.add_argument("--note")
    a.set_defaults(func=cmd_add)
    l = sub.add_parser("list"); l.add_argument("--since")
    l.set_defaults(func=cmd_list)
    s = sub.add_parser("stats"); s.set_defaults(func=cmd_stats)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
