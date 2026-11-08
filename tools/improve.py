#!/usr/bin/env python3
"""从失败信号生成改进提案（不做修改，只出清单）。

自提升的第二层：失败要能变成「下一步做什么」，而不是攒着。
提案分四类，每类都带证据条数——没有证据支撑的规则修改不该发生。

用法：
    python3 tools/improve.py                 # 输出到 reports/improvement-<日期>.md
    python3 tools/improve.py --stdout
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "data" / "feedback.jsonl"
SYN = ROOT / "data" / "card-synonyms.txt"

ACTION = {
    "miss": "先查同义词表；仍不命中则补卡（按判据：条文之外要有判断路径）",
    "unusable": "改该卡 key_point 为可执行动作，或重写争点表述",
    "wrong_citation": "回原文核条号与前提；改 key_point 或引文，SQL 直改不重导",
    "gap": "登记为来源缺口；等文书通道，不要用转载站凑",
    "slow": "看是否可脚本化（检索、校验、报告生成）",
}


def load() -> list[dict]:
    if not LOG.exists():
        return []
    return [json.loads(x) for x in LOG.read_text(encoding="utf-8").splitlines() if x.strip()]


def synonyms() -> list[str]:
    if not SYN.exists():
        return []
    return [l.split("=")[0].strip() for l in SYN.read_text(encoding="utf-8").splitlines()
            if "=" in l and not l.startswith("#")]


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="生成改进提案")
    ap.add_argument("--stdout", action="store_true")
    args = ap.parse_args(argv)

    rows = load()
    if not rows:
        print("没有失败信号，先跑一次真实检索并登记问题")
        return 0

    by_type = defaultdict(list)
    for r in rows:
        by_type[r["type"]].append(r)

    lines = [f"# 改进提案（{date.today().isoformat()}）", "",
             f"基于 {len(rows)} 条失败信号。**本文件只是提案，不自动改规则或卡片。**", ""]
    for t, items in sorted(by_type.items(), key=lambda x: -len(x[1])):
        lines.append(f"## {t}（{len(items)} 条）")
        lines.append(f"动作：{ACTION.get(t, '待定')}")
        lines.append("")
        for r in items:
            who = r.get("case") or r.get("card") or r.get("query") or "-"
            lines.append(f"- {r['date']} `{who}` {r.get('note','')}")
        lines.append("")

    # 同义词候选：miss 里的检索词如果不在同义词表，建议补
    syn = set(synonyms())
    cand = sorted({w for r in by_type["miss"] for w in (r.get("query") or "").split() if w and w not in syn})
    if cand:
        lines += ["## 同义词候选（miss 里出现、词表里没有）", "",
                  "```", *[f"{w}=待补同义词" for w in cand], "```", ""]

    lines += ["## 回归要求", "",
              "改完必须重跑，两项都要过：", "",
              "```", "python3 tools/card_health.py", "python3 tools/retrieval_check.py", "```", ""]

    text = "\n".join(lines)
    if args.stdout:
        print(text)
        return 0
    out = ROOT / "reports" / f"improvement-{date.today().isoformat()}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"已生成 {out}（{len(rows)} 条信号）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
