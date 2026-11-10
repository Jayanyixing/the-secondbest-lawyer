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
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lawdb import normalize_article_no  # noqa: E402

# tags 首项 → 案由关键词族；首项与案由必须同族，否则说明标签比案由还粗
# 只做「同族/不同族」判断，不追求字面相等：商品房预售合同纠纷属于买卖族，
# 地面施工、地下设施损害责任纠纷属于侵权族——这些是更具体的案由，不是错。
TAG2CAUSE = {
    "建工": ("建设工程",), "工程": ("建设工程",),
    "分包": ("建设工程",), "挂靠": ("建设工程",),
    "买卖": ("买卖", "商品房"), "消费": ("买卖",),
    "商品房": ("商品房",),
    "劳动": ("劳动", "竞业", "工伤"), "工伤": ("劳动", "工伤"),
    "竞业": ("竞业", "劳动"), "新业态": ("劳动", "保险"),
    "公司": ("公司", "股权"), "股权": ("公司", "股权"),
    "担保": ("担保", "保证"), "保证": ("保证", "担保"), "抵押": ("担保", "抵押"),
    "保全": ("保全", "执行"),
    "执行": ("执行",), "破产": ("破产",),
    "知产": ("知识产权", "商标", "专利", "著作权"),
    "商标": ("商标",), "专利": ("专利",), "著作权": ("著作权",),
    "侵权": ("侵权", "责任纠纷"), "租赁": ("租赁",),
    "借贷": ("借贷",), "保险": ("保险",), "合同": ("合同",),
}

# 语义越界的可疑措辞：条文里没有的前提，key_point 却写成硬条件
OVERCLAIM = ("必须以", "须以", "一律", "均须", "前提是", "必然", "一定")

CASE_RE = re.compile(
    r"^(.*?)(第[零〇一二三四五六七八九十百千两\d]+条(?:之[一二三四五六七八九十\d]+)?)"
    r"(?:第[零〇一二三四五六七八九十百千两\d]+[款项])*$"
)
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


def find_law(articles: dict[str, dict[str, str]], law_hint: str) -> str | None:
    """先按法名定位，不看条号——否则条号写错时会被当成「库里没有这部法」而漏报。

    容忍《民法典》与《中华人民共和国民法典》这类简称差异：
    - 完全相等 > 法名包含简称 > 简称包含法名；
    - 「法名包含简称」同分时取**最短**的（《民法典》→ 民法典本身，而不是某部民法典解释）；
    - 「简称包含法名」同分时取最长的（离简称最近）。
    """
    hint = norm_law(law_hint)
    if not hint:
        return None
    best, best_key = None, None
    for name in articles:
        norm_name = norm_law(name)
        if norm_name == hint:
            key = (3, 0)
        elif hint in norm_name:
            key = (2, -len(norm_name))
        elif norm_name in hint:
            key = (1, len(norm_name))
        else:
            continue
        if best_key is None or key > best_key:
            best, best_key = name, key
    return best


def find_article(articles: dict[str, dict[str, str]], law_hint: str, no: str):
    """返回 (法名, 条文)；法找到但无此条时条文为 None，法都找不到时两者皆 None。"""
    name = find_law(articles, law_hint)
    if name is None:
        return None, None
    return name, articles[name].get(no)


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

    misplaced, missing, no_article, ok = [], [], [], 0
    for cid, no_, issues, holding, quote, kind in rows:
        m = CASE_RE.search((no_ or "").strip())
        if not m:
            # 会议纪要、指导意见、典型案例本来就没有条号，不属于"校验失败"
            no_article.append((cid, no_))
            continue
        law, art_no = m.group(1).strip(), normalize_article_no(m.group(2))
        law = law.strip("《》〈〉") if law.count("《") <= 1 else law.strip("《》")
        name, text = find_article(articles, law, art_no)
        if name is None:
            missing.append((cid, no_, f"库中找不到 {law}"))
            continue
        q = norm(quote)
        q = ART_PREFIX_RE.sub("", q)
        if text is not None and q and q in text:
            ok += 1
            continue
        # 引文不在声称的条里（或该法根本没有这一条）——去同一部法的其他条找
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

    cause_mismatch = []
    composite_cause = []
    for cid, cause, tags in conn.execute("SELECT id, cause, tags FROM cards"):
        first = (tags or "").split(",")[0].strip()
        family = TAG2CAUSE.get(first)
        if family and cause and not any(k in cause for k in family):
            cause_mismatch.append((cid, cause[:18], first, "／".join(family)))
        if cause and "/" in cause:
            composite_cause.append((cid, cause[:24]))

    overclaim = []
    for cid, kp in conn.execute("SELECT id, key_point FROM cards WHERE kind='rule'"):
        for w in OVERCLAIM:
            if w in (kp or ""):
                overclaim.append((cid, w, (kp or "")[:40]))
                break

    placeholder = [r for r in conn.execute(
        "SELECT id, case_no, cause FROM cards WHERE trim(cause) IN ('见 tags','见tags','待定','TODO','TBD')")]
    # 「无法校验」是信息不是错误（如会议纪要没有条号），只有真问题才返回非零
    # 案由比标签更具体（分包 vs 施工合同、商品房预售 vs 买卖）是合理的，只作提示
    problems = len(misplaced) + len(conflicts) + len(placeholder)
    if args.json:
        print(json.dumps(dict(ok=ok, misplaced=misplaced, missing=missing,
                             conflicts=conflicts, placeholder=placeholder,
                             no_article=no_article,
                             cause_mismatch=cause_mismatch, composite_cause=composite_cause,
                             overclaim=overclaim),
                         ensure_ascii=False, indent=2))
    else:
        print(f"规则卡 {len(rows)} 张：条号与引文一致 {ok} 张")
        if misplaced:
            print(f"\n条号错位 {len(misplaced)} 张（引文正确，条号写错——最隐蔽的一类）：")
            for cid, cno, hit in misplaced:
                print(f"  ✗ #{cid} {cno}" + (f"  → 引文实为 {hit}" if hit else "  → 该法内未找到引文"))
        if no_article:
            names = "、".join(f"#{cid} {n[:24]}" for cid, n in no_article[:4])
            more = f" 等 {len(no_article)} 张" if len(no_article) > 4 else ""
            print(f"\n无条号（会议纪要／典型案例，不适用条号校验）：{names}{more}")
        if missing:
            print(f"\n无法校验 {len(missing)} 张：")
            for cid, cno, why in missing:
                print(f"  ? #{cid} {cno} | {why}")
        if overclaim:
            print(f"\n提示：key_point 出现绝对化表述 {len(overclaim)} 张（需核条文是否真有该前提）：")
            for cid, w, kp in overclaim[:8]:
                print(f"  ? #{cid} 「{w}」 {kp}")
        if cause_mismatch:
            print(f"\n提示：标签首项与案由不同族 {len(cause_mismatch)} 张（不是错误，建议调标签顺序）：")
            for cid, cause, tag, want in cause_mismatch[:12]:
                print(f"  ! #{cid} 首标签「{tag}」≠ 案由「{cause}」（{want} 族）")
        if composite_cause:
            print(f"\n提示：案由带「/」{len(composite_cause)} 张，检索与统计会分叉，建议取其一：")
            for cid, cause in composite_cause:
                print(f"  ! #{cid} {cause}")
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
