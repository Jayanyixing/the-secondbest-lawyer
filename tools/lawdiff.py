#!/usr/bin/env python3
"""条文级比对：拿官方原件和库内文本逐条对，找出差在哪。

用途：版本风险分档后，第一档法律要做「逐字比对」。把官方下载件（docx/pdf/html/txt）
和库内源文件（data/sources/...）一起丢进来，输出：

- 两部文本各自条数、缺号；
- 只有一边有的条号；
- 内容不一致的条号（含差异片段）；
- 结论：完全一致 / 有 N 处差异。

用法：
    python3 tools/lawdiff.py 官方-民法典.docx data/sources/lawrefbook/30-中华人民共和国民法典.md
    python3 tools/lawdiff.py A.txt B.txt --limit 10

无第三方依赖（docx 直接解 zip+XML，pdf 需系统 pdftotext）。
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lawdb import cn2int, extract_text, normalize_article_no, parse_articles  # noqa: E402


def norm(text: str) -> str:
    return re.sub(r"[\s\u3000]+", "", text or "")


def strip_md(text: str) -> str:
    """去掉 markdown 标题，包括被整理件粘到条文末尾的行内标题（…除外。####第三节…）。"""
    text = re.sub(r"(?m)^#{1,6}[^\n]*$", "", text)
    text = re.sub(r"#{2,}[^#\n]*", "", text)
    return re.sub(r"#+", "", text)


def load(path: Path) -> tuple[dict[str, str], list[int]]:
    text = extract_text(path)
    if path.suffix.lower() in {".md", ".markdown"}:
        text = strip_md(text)
    arts = parse_articles(text)
    # 与 lawdb.cmd_import 保持一致：同条号被正文引用重复切出时，保留正文最长的一条
    book: dict[str, str] = {}
    for a in arts:
        if a["sort"] <= 0:
            continue
        no = normalize_article_no(a["article_no"])
        body = norm(a["text"])
        if no not in book or len(body) > len(book[no]):
            book[no] = body
    nums = sorted({a["sort"] for a in arts if a["sort"] > 0})
    return book, nums


HEAD_TAIL = re.compile(
    r"(?:第[零〇一二三四五六七八九十百千两\d]+(?:分)?编"
    r"|第[零〇一二三四五六七八九十百千两\d]+[章节]"
    r"|附则)[^。；，、]{0,24}$"
)


def strip_tail_heading(text: str) -> str:
    """去掉粘在条文末尾的目录标题（官方 docx 的「第三分编用益物权」、库内的「####第二节」残留）。"""
    prev = None
    while prev != text:
        prev = text
        text = HEAD_TAIL.sub("", text)
    return text


def is_heading_glue(a: str, b: str) -> bool:
    """两边只差末尾目录标题时，算标题粘连，不算正文差异。"""
    if a == b:
        return False
    return strip_tail_heading(a) == strip_tail_heading(b)


def snippet(a: str, b: str, width: int = 24) -> tuple[str, str]:
    sm = difflib.SequenceMatcher(None, a, b)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag != "equal":
            return (a[max(0, i1 - width): i2 + width], b[max(0, j1 - width): j2 + width])
    return "", ""


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="条文级比对")
    ap.add_argument("official", type=Path, help="官方原件")
    ap.add_argument("local", type=Path, help="库内文本")
    ap.add_argument("--limit", type=int, default=10, help="最多列出多少处差异")
    ap.add_argument("--only", help="只比这些条号，逗号分隔，如 第九条,第三十条")
    ap.add_argument("--anchors", type=Path, help="锚点文件 anchors.json")
    ap.add_argument("--law", help="锚点文件里的法名")
    args = ap.parse_args(argv)

    for p in (args.official, args.local):
        if not p.exists():
            print(f"找不到 {p}", file=sys.stderr)
            return 2

    a, a_nums = load(args.official)
    b, b_nums = load(args.local)

    only = None
    if args.anchors:
        import json

        anchors = json.loads(args.anchors.read_text(encoding="utf-8"))
        if args.law:
            only = anchors.get(args.law)
        else:
            only = next((v for k, v in anchors.items() if k in str(args.local) or k in str(args.official)), None)
        if not only:
            print(f"锚点文件里没有找到对应条目：{args.law or '自动匹配失败'}", file=sys.stderr)
            return 2
    if args.only:
        only = [x.strip() for x in args.only.split(",") if x.strip()]
    if only:
        # 锚点与 --only 都可能写成「9」「第9条」「第九条」，统一成库里的写法再比对
        only = [normalize_article_no(x) for x in only]
        a = {k: v for k, v in a.items() if k in only}
        b = {k: v for k, v in b.items() if k in only}
        a_nums = sorted({cn2int(k.lstrip("第").split("条")[0]) for k in a})
        b_nums = sorted({cn2int(k.lstrip("第").split("条")[0]) for k in b})
        print(f"抽查模式：{len(only)} 个锚点条号")
    print(f"A（官方）：{len(a)} 条，最大 {a_nums[-1] if a_nums else 0}")
    print(f"B（库内）：{len(b)} 条，最大 {b_nums[-1] if b_nums else 0}")

    only_a = [n for n in a if n not in b]
    only_b = [n for n in b if n not in a]
    raw_changed = [n for n in a if n in b and a[n] != b[n]]
    glue = [n for n in raw_changed if is_heading_glue(a[n], b[n])]
    changed = [n for n in raw_changed if n not in glue]

    def label(no: str) -> str:
        return no

    if only_a:
        print(f"\n只在官方件里：{len(only_a)} 条 → {', '.join(label(x) for x in only_a[:8])}")
    if only_b:
        print(f"只在库内：{len(only_b)} 条 → {', '.join(label(x) for x in only_b[:8])}")

    if glue:
        print(f"\n只差末尾目录标题（非正文差异）：{len(glue)} 条 → {', '.join(glue[:8])}")
    if changed:
        print(f"\n内容不一致：{len(changed)} 条")
        for no in changed[: args.limit]:
            x, y = snippet(a[no], b[no])
            print(f"\n  {no}")
            print(f"    官方：…{x}…")
            print(f"    库内：…{y}…")
    elif not only_a and not only_b and not glue:
        print("\n结论：条号与内容完全一致 ✓")
        return 0

    identical = len([n for n in a if n in b and a[n] == b[n]])
    print(f"\n一致 {identical} 条｜标题粘连 {len(glue)} 条｜实质不一致 {len(changed)} 条｜单边 {len(only_a) + len(only_b)} 条")
    return 0 if not changed and not only_a and not only_b else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
