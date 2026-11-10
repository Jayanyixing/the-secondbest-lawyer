#!/usr/bin/env python3
"""回归测试：跑固定问题集，任何一条从命中变不命中就报错。

自提升的第三层：改同义词、改卡片、改规则之后，必须证明没把原来的能力弄坏。
题库在 data/retrieval-cases.json，格式：[{"q": ["争点词","补充词"], "expect": "必须出现的关键词"}]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT / "data" / "retrieval-cases.json"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default=str(CASES))
    args = ap.parse_args(argv)
    cases_path = Path(args.cases)
    if not cases_path.exists():
        print(f"题库不存在：{cases_path}")
        return 2
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    passed = failed = 0
    for c in cases:
        r = subprocess.run([sys.executable, str(ROOT / "tools" / "lawdb.py"), "card-query", *c["q"],
                            "--limit", "3"],
                           cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
        # 未命中时 card-query 退出 1 并回显查询词；expect 常与查询词相同，
        # 只看 stdout 会把「未命中卡片：追加 被执行人」误判为命中，所以先看退出码。
        ok = r.returncode == 0 and c["expect"] in r.stdout
        if ok:
            passed += 1
        else:
            failed += 1
            print(f"  ✗ {' '.join(c['q'])} → 期望含「{c['expect']}」")
    print(f"回归：{passed}/{len(cases)} 通过" + ("" if not failed else f"，{failed} 条失败"))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
