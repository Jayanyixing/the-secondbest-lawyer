#!/usr/bin/env python3
"""卡片体检：抓「条号错位」和「跨卡矛盾」这两类机器看不见的错。

规则卡最危险的错误不是摘录打错字，而是**引文正确、条号写错**——
字错能看出来，条号错看起来完全正常。本脚本逐张把引文放回它自我声称的
那一条里比对；放不进去但能在同一部法其他条找到的，直接报「条号错位」。

用法：
    python3 tools/card_health.py                # 默认体检 data/cards.sqlite
    python3 tools/card_health.py --db /tmp/x.sqlite --json

退出码：0 无问题；1 有问题。
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LAW_DB = ROOT / "data" / "law.sqlite"

CASE_RE = re.compile(r"^(.*?)(第[零〇一二三四五六七八九十百千两\d]+条(?:之[一二三四五六七八九十]+)?)$")
ART_PREFIX_RE = re.compile(r"^第[零〇一二三四五六七八九十百千两\d]+条(?:之[一二三四五六七八九十]+)?[\s\u3000]*")


def norm_law(name: str) -> str:
    """统一书名号写法，去掉首尾符号：《民法典》≈〈民法典〉≈民法典。"""
    for ch in "《》〈〉「」":
        name = name.replace(ch, "")
    return name.strip()


def norm(t: str) -> str:
    return re.sub(r"\s+", "", t or "")


def load_articles() -> dict[str, dict[str, str]]:
    """law 名 → {条号: 正文}。"""
    if not LAW_DB.exists():
        return {}
    conn = sqlite3.connect(LAW_DB)
    out: dict[str, dict[str, str]] = {}
    for name, no, text in conn.execute(
        "SELECT l.name, a.article_no, a.text FROM articles a JOIN laws l ON l.id=a.law_id"
    ):
        out.setdefault(name, {})[no] = norm(text)
    return out


def find_article(articles: dict[str, dict[str, str]], law_hint: str, no: str):
    """容忍《民法典》与《中华人民共和国民法典》这类简称差异。"""
    hint = norm_law(law_hint)
    best, score = None, 0
    for name, arts in articles.items():
        norm_name = norm_law(name)
        if not hint or no not in arts:
            continue
        if norm_name == hint:
            s_ = 3
        elif hint in norm_name:
            s_ = 2
        elif norm_name in hint:
            s_ = 1
        else:
            continue
        if s_ > score or (s_ == score and best and len(name) > len(best)):
            best, score = name, s_
    return (best, articles[best][no]) if best else (None, None)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="卡片体检")
    ap.add_argument("--db", default=str(ROOT / "data" / "cards.sqlite"))
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    conn = sqlite3.connect(args.db)
    articles = load_articles()
    rows = conn.execute(
        "SELECT id, case_no, issues, holding, quote, kind FROM cards WHERE kind='rule'"
    ).fetchall()

    PLACEHOLDER = ("见 tags", "见tags", "待定", "TODO", "TBD", "?")
    placeholders = conn.execute(
        "SELECT id, case_no, cause FROM cards WHERE trim(cause) IN (%s)"
        % ",".join("?" * len(PLACEHOLDER)), PLACEHOLDER).fetchall() if False else []
    misplaced, missing, ok = [], [], 0
    for cid, no_, issues, holding, quote, kind in rows:
        m = CASE_RE.search((no_ or "").strip())
        if not m:
            missing.append((cid, no_, "无法从 case_no 解析《法规》第X条"))
            continue
        law, art_no = m.group(1).strip(), m.group(2)
        law = law.strip("《》〈〉") if law.count("《") <= 1 else law.strip("《》")
        name, text = find_article(articles, law, art_no)
        if text is None:
            missing.append((cid, no_, f"库中找不到 {law} {art_no}"))
            continue
        q = norm(quote)
        q = ART_PREFIX_RE.sub("", q)
        if q and q in text:
            ok += 1
            continue
        # 引文不在声称的条里——去同一部法的其他条找
        hit = next((k for k, v in articles.get(name, {}).items() if q and q in v), None)
        misplaced.append((cid, no_, hit))

    # 跨卡矛盾：同组同争点、holding 明显不同
    conflicts = []
    allc = conn.execute("SELECT id, cause, issues, holding FROM cards").fetchall()
    for i in range(len(allc)):
        for j in range(i + 1, len(allc)):
            a, b = allc[i], allc[j]
            if a[1] != b[1]:
                continue
            if a[2] == b[2] and norm(a[3])[:20] != norm(b[3])[:20]:
                conflicts.append((a[0], b[0], a[2][:32]))

    placeholder = [r for r in conn.execute(
        "SELECT id, case_no, cause FROM cards WHERE trim(cause) IN ('见 tags','见tags','待定','TODO','TBD')")]
    # 「无法校验」是信息不是错误（如会议纪要没有条号），只有真问题才返回非零
    problems = len(misplaced) + len(conflicts) + len(placeholder)
    if args.json:
        print(json.dumps(dict(ok=ok, misplaced=misplaced, missing=missing,
                             conflicts=conflicts, placeholder=placeholder),
                         ensure_ascii=False, indent=2))
    else:
        print(f"规则卡 {len(rows)} 张：条号与引文一致 {ok} 张")
        if misplaced:
            print(f"\n条号错位 {len(misplaced)} 张（引文正确，条号写错——最隐蔽的一类）：")
            for cid, cno, hit in misplaced:
                print(f"  ✗ #{cid} {cno}" + (f"  → 引文实为 {hit}" if hit else "  → 该法内未找到引文"))
        if missing:
            print(f"\n无法校验 {len(missing)} 张：")
            for cid, cno, why in missing:
                print(f"  ? #{cid} {cno} | {why}")
        if placeholder:
            print(f"\n占位值 {len(placeholder)} 张（cause 不是案由）：")
            for cid, cno, cause in placeholder:
                print(f"  ! #{cid} {cno[:30]} | cause={cause}")
        if conflicts:
            print(f"\n同组同争点、结论不同 {len(conflicts)} 对：")
            for a, b, iss in conflicts:
                print(f"  ! #{a} vs #{b} | {iss}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
