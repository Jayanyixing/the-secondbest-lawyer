#!/usr/bin/env python3
"""lawdb 四个已知 bug 的回归探针（12 条断言）。

默认检查仓库 ``tools/lawdb.py``；也可传入路径，或用 ``TSL_TOOLS_DIR`` 指向基线目录：
    python3 tests/test_lawdb_bugs.py
    TSL_TOOLS_DIR=<含 lawdb.py 的基线目录> python3 tests/test_lawdb_bugs.py

每项断言「bug 不存在」。对修复前的 lawdb.py 运行，4 个 bug 场景均至少有一条失败
（基线 3/12 通过）；对修复后的运行 12/12 全 PASS——因此它同时验证测试本身有辨别力。
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import sqlite3
import sys
import tempfile
import zipfile
from argparse import Namespace
from pathlib import Path

TOOLS_DIR = Path(
    os.environ.get("TSL_TOOLS_DIR", Path(__file__).resolve().parent.parent / "tools")
).resolve()
MOD_PATH = (
    Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else (TOOLS_DIR / "lawdb.py").resolve()
)
if not MOD_PATH.is_file():
    raise SystemExit(f"找不到 lawdb.py：{MOD_PATH}")


def load(path: Path):
    spec = importlib.util.spec_from_file_location("lawdb_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = load(MOD_PATH)
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))


# ---------------------------------------------------------------- 1. 简称查母法

LAW_NAMES = [
    "中华人民共和国民事诉讼法",
    "最高人民法院关于适用《中华人民共和国民事诉讼法》的解释",
    "最高人民法院关于适用《中华人民共和国民事诉讼法》执行程序若干问题的解释",
    "中华人民共和国刑事诉讼法",
    "最高人民法院关于适用《中华人民共和国刑事诉讼法》的解释",
    "中华人民共和国行政诉讼法",
    "最高人民法院关于适用《中华人民共和国行政诉讼法》的解释",
]


def test_resolve_laws() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE laws(id INTEGER PRIMARY KEY, name TEXT UNIQUE)")
    conn.executemany("INSERT INTO laws(name) VALUES(?)", [(n,) for n in LAW_NAMES])

    for hint, want in [
        ("民诉法", ["中华人民共和国民事诉讼法"]),
        ("刑诉法", ["中华人民共和国刑事诉讼法"]),
        ("行诉法", ["中华人民共和国行政诉讼法"]),
    ]:
        got = mod.resolve_laws(conn, hint)
        check(
            f"resolve_laws({hint}) 命中母法",
            got == want,
            f"实际 {got}",
        )

    # 带「解释」后缀时仍应落到司法解释，不能被这次修复带偏
    got = mod.resolve_laws(conn, "民诉法解释")
    check(
        "resolve_laws(民诉法解释) 仍命中司法解释",
        bool(got) and all("解释" in n for n in got),
        f"实际 {got}",
    )


# ---------------------------------------------------------------- 2. 折行引用不截断

PARA_TEXT = """第五十条 当事人依照本法规定主张解除合同的，应当通知对方。
合同自通知到达对方时解除。对方有异议的，可以请求人民法院确认解除行为的效力。
第五十条规定的期间届满后，当事人不得再行主张解除。
第五十一条 有下列情形之一的，当事人可以解除合同。
"""


def test_parse_articles() -> None:
    arts = mod.parse_articles(PARA_TEXT)
    nos = [a["article_no"] for a in arts]
    check(
        "parse_articles 不为折行引用另起条文",
        nos == ["第五十条", "第五十一条"],
        f"实际条号序列 {nos}",
    )
    art50 = next((a for a in arts if a["article_no"] == "第五十条"), None)
    check(
        "parse_articles 保留原条文后半段",
        art50 is not None and "第五十条规定的期间届满后" in art50["text"],
        f"第五十条正文尾部：…{(art50['text'][-24:] if art50 else '缺失')!r}",
    )
    # 只在“引用句在行首”时才算正文；真正的第X条仍须照常切开
    check(
        "parse_articles 仍能切开正常的相邻条文",
        art50 is not None and "当事人可以解除合同" in next(
            (a["text"] for a in arts if a["article_no"] == "第五十一条"), ""
        ),
    )


# ---------------------------------------------------------------- 2b. 入库端到端

def test_import_keeps_tail() -> None:
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "某法.md"
        src.write_text(PARA_TEXT, encoding="utf-8")
        db = Path(td) / "law.sqlite"
        args = Namespace(
            db=db, files=[str(src)], name="测试法", issuer="测试机关", doc_no=None,
            publish="2020-01-01", effective="2020-01-01", status="现行有效", url="",
            channel="官方页面", official_check="未核", note=None, date="2026-11-09",
        )
        with contextlib.redirect_stdout(io.StringIO()):
            mod.cmd_import(args)
        conn = sqlite3.connect(db)
        row = conn.execute("SELECT text FROM articles WHERE article_no='第五十条'").fetchone()
        conn.close()
    text = row[0] if row else ""
    check(
        "cmd_import 去重后不丢原条文后半段",
        "第五十条规定的期间届满后" in text,
        f"库内第五十条正文尾部：…{text[-24:]!r}",
    )


# ---------------------------------------------------------------- 3. docx 断行

def test_docx_to_text() -> None:
    doc = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p>
      <w:r><w:t>第五十条</w:t></w:r>
      <w:r><w:t xml:space="preserve"> 当事人一方</w:t></w:r>
      <w:r><w:t>行使解除权的，应当通知对方。</w:t></w:r>
    </w:p>
    <w:p>
      <w:r><w:t>第五十一条</w:t></w:r>
      <w:r><w:tab/></w:r>
      <w:r><w:t>有下列情形之一的</w:t></w:r>
    </w:p>
    <w:tbl>
      <w:tr><w:tc><w:p><w:r><w:t>第一百条 表格内条文</w:t></w:r></w:p></w:tc></w:tr>
    </w:tbl>
  </w:body>
</w:document>"""
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "t.docx"
        with zipfile.ZipFile(p, "w") as zf:
            zf.writestr("word/document.xml", doc)
        text = mod.docx_to_text(p)

    lines = [ln for ln in text.splitlines() if ln.strip()]
    check(
        "docx_to_text 不泄漏 XML 残渣",
        "</w:r>" not in text and "<w:t" not in text,
        f"实际 {text[:60]!r}",
    )
    check(
        "docx_to_text 段内 <w:r> 不被缩进换行切碎",
        any(ln.startswith("第五十条 当事人一方行使解除权") for ln in lines),
        f"实际行：{lines[:3]}",
    )
    check(
        "docx_to_text 表格内条文保留且可被条号正则命中",
        "第一百条 表格内条文" in text and bool(mod.ARTICLE_RE.search(text)),
    )


# ---------------------------------------------------------------- 4. 同义词短词

def test_card_query_short_synonym() -> None:
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "cards.sqlite"
        conn = sqlite3.connect(db)
        conn.executescript(mod.CARDS_SCHEMA)
        rows = [
            ("(2024)京01民终1X号", "合同纠纷", "违约金是否过高", "约定违约金过高，应予调整"),
            ("(2024)京01民终2X号", "借款合同", "利息计算", "按LPR计付利息，逾期的加倍"),
        ]
        for no, cause, issues, holding in rows:
            conn.execute(
                "INSERT INTO cards(case_no,cause,issues,holding,source,created_at,verify_status,kind)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (no, cause, issues, holding, "测试", "2026-11-09", "verified", "judgment"),
            )
        conn.commit()
        conn.execute("INSERT INTO cards_fts(cards_fts) VALUES('rebuild')")
        conn.commit()
        conn.close()

        orig = mod.load_synonyms
        mod.load_synonyms = lambda: {"违约金": ["利息"]}  # 3 字词扩展出 2 字同义词
        try:
            args = Namespace(db=db, keyword=["违约金"], limit=10, status="", kind="")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = mod.cmd_card_query(args)
            out = buf.getvalue()
        finally:
            mod.load_synonyms = orig

        hit = out.count("【")
        check(
            "cmd_card_query 短同义词不静默丢结果",
            rc == 0 and hit == 2 and "利息计算" in out,
            f"命中 {hit} 张（应 2 张，含仅匹配「利息」的那张）",
        )


# ---------------------------------------------------------------- 主流程

for fn in (test_resolve_laws, test_parse_articles, test_import_keeps_tail,
           test_docx_to_text, test_card_query_short_synonym):
    try:
        fn()
    except Exception as exc:  # 探针自身异常也算不通过
        check(f"{fn.__name__} 运行异常", False, f"{type(exc).__name__}: {exc}")

print(f"被检对象：{MOD_PATH}")
fails = 0
for name, ok, detail in results:
    print(f"[{'通过' if ok else '失败'}] {name}" + (f"  ← {detail}" if not ok and detail else ""))
    fails += 0 if ok else 1
print(f"结果：{len(results) - fails}/{len(results)} 通过")
raise SystemExit(1 if fails else 0)
