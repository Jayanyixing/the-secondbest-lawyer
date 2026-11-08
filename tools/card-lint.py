#!/usr/bin/env python3
"""卡入库前校验：字段完整性、quote 长度、脱敏、库内去重。
用法：
  python3 tools/card-lint.py cards.json [--db data/law.sqlite] [--out cards.clean.json]
不通过的行不写入 clean 文件；报告打到 stdout，并写 cards.lint.md。
"""
import json, sys, re, sqlite3, argparse
from pathlib import Path

REQUIRED = ["case_no", "cause", "issues", "holding", "our_side", "key_point", "source", "quote", "tags"]
QUOTE_MIN, QUOTE_MAX = 8, 60
CASE_RE = re.compile(r'（\d{4}）[\u4e00-\u9fa5]{1,4}\d{0,6}[\u4e00-\u9fa5]{1,6}\d*号$')
MASK_TOKENS = ("XXXX", "XX", "***", "××", "某")

def check(rows, existing):
    ok, bad = [], []
    seen = set()
    for i, r in enumerate(rows, 1):
        errs = []
        for k in REQUIRED:
            v = r.get(k)
            if v is None or str(v).strip() == "":
                errs.append(f"缺字段 {k}")
        q = str(r.get("quote", "") or "").strip()
        if q and not (QUOTE_MIN <= len(q) <= QUOTE_MAX):
            errs.append(f"quote 长度 {len(q)} 字，要求 {QUOTE_MIN}-{QUOTE_MAX}")
        cn = str(r.get("case_no", "") or "").strip()
        if cn:
            if not any(t in cn for t in MASK_TOKENS):
                errs.append("case_no 未见脱敏标记（XXXX/XX/***/某）")
            elif not CASE_RE.match(cn):
                errs.append("case_no 不符合案号格式（示例：（2023）京0105民初XXXX号）")
        tg = str(r.get("tags", "") or "")
        if tg and re.search(r'\s', tg):
            errs.append("tags 含空格（应为英文逗号分隔）")
        key = (cn, str(r.get("issues", "") or "").strip())
        if key in seen:
            errs.append("本批次内重复（同案号+同争点）")
        if key in existing:
            errs.append("库中已存在（同案号+同争点）")
        seen.add(key)
        (bad if errs else ok).append((i, r, errs))
    return ok, bad

def load_existing(db):
    try:
        conn = sqlite3.connect(db)
        cur = conn.execute("SELECT case_no, issues FROM cards")
        s = {(a or "", b or "") for a, b in cur}
        conn.close()
        return s
    except Exception:
        return set()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--db", default="data/law.sqlite")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    data = json.loads(Path(a.file).read_text(encoding="utf-8"))
    rows = data if isinstance(data, list) else [data]
    ok, bad = check(rows, load_existing(a.db))
    out = a.out or str(Path(a.file).with_suffix(".clean.json"))
    Path(out).write_text(json.dumps([r for _, r, _ in ok], ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [f"# 卡片校验报告：{Path(a.file).name}", "",
             f"- 总行数 {len(rows)}，通过 {len(ok)}，不通过 {len(bad)}", ""]
    for i, r, errs in bad:
        lines.append(f"- 第 {i} 行（{r.get('case_no') or '无案号'}）：" + "；".join(errs))
    if not bad:
        lines.append("- 全部通过。可直接 `python3 tools/lawdb.py card-add --file %s`" % out)
    Path(Path(out).with_suffix(".lint.md")).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if not bad else 1

if __name__ == "__main__":
    sys.exit(main())
