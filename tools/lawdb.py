#!/usr/bin/env python3
"""本地法条库（L1）：把官方下载的法规文件索引成本地 SQLite，离线、毫秒级、可回读校验。

设计前提：本工具**不做爬虫**。法规文件由使用者从官方渠道获取（下载 Word/PDF/HTML、
另存网页、或商业库按许可导出），本工具只负责切条、建索引、检索与一致性校验。

用法：
    python3 tools/lawdb.py init
    python3 tools/lawdb.py import 民法典.docx --name 中华人民共和国民法典 \\
        --issuer 全国人民代表大会 --publish 2020-05-28 --effective 2021-01-01 \\
        --url https://flk.npc.gov.cn/detail2.html?ZmY4MDgw...
    python3 tools/lawdb.py query 违约金 调整 --limit 5
    python3 tools/lawdb.py article 中华人民共和国民法典 第五百八十五条
    python3 tools/lawdb.py stats
    python3 tools/lawdb.py verify

支持 .txt/.md/.html/.htm/.docx/.pdf（pdf 依赖系统 pdftotext，可选）。
无第三方依赖。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import subprocess
import sys
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "law.sqlite"

CN_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
             "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
CN_UNITS = {"十": 10, "百": 100, "千": 1000}

ARTICLE_RE = re.compile(r"^\s*第([零〇一二三四五六七八九十百千两\d]{1,8})条[\s\u3000　]*(.*)$", re.M)
HEADING_RE = re.compile(r"^\s*(第[零〇一二三四五六七八九十百千两\d]{1,6}[编章节])\s*(.*)$", re.M)


def cn2int(text: str) -> int:
    """把「五百八十五」「12」这类条号转成整数，用于排序。"""
    text = text.strip()
    if text.isdigit():
        return int(text)
    total, section, num = 0, 0, 0
    for ch in text:
        if ch in CN_DIGITS:
            num = CN_DIGITS[ch]
        elif ch in CN_UNITS:
            section += (num or 1) * CN_UNITS[ch]
            num = 0
        else:
            continue
    return total + section + num


# ---------------------------------------------------------------- 取文本


def html_to_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "\n", raw)
    raw = re.sub(r"(?i)<br\s*/?>", "\n", raw)
    raw = re.sub(r"(?i)</(p|div|h\d|li|tr|table|section)>", "\n", raw)
    raw = re.sub(r"<[^>]+>", "", raw)
    raw = raw.replace("&nbsp;", " ").replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    raw = re.sub(r"[ \t\u3000]+", " ", raw)
    return re.sub(r"\n{3,}", "\n\n", raw)


def docx_to_text(path: Path) -> str:
    """不用 python-docx：docx 就是 zip + XML，直接抽 <w:t>。"""
    with zipfile.ZipFile(path) as zf:
        xml = zf.read("word/document.xml").decode("utf-8", errors="ignore")
    xml = xml.replace("</w:p>", "\n")
    parts = re.findall(r"<w:t[^>]*>(.*?)</w:t>|(\n)", xml, flags=re.S)
    out = "".join(a or b for a, b in parts)
    return out.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")


def pdf_to_text(path: Path) -> str:
    try:
        return subprocess.run(["pdftotext", "-layout", str(path), "-"],
                              capture_output=True, text=True, check=True).stdout
    except (FileNotFoundError, subprocess.CalledProcessError):
        raise SystemExit("需要 pdftotext（macOS 可 brew install poppler），或先把 PDF 另存为 Word/txt")


def _store_path(path: Path) -> str:
    """仓库内的文件存相对路径，换机器仍可校验；仓库外存绝对路径。"""
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in (".html", ".htm"):
        return html_to_text(path.read_text(encoding="utf-8", errors="ignore"))
    if suffix == ".docx":
        return docx_to_text(path)
    if suffix == ".pdf":
        return pdf_to_text(path)
    return path.read_text(encoding="utf-8", errors="ignore")


# ---------------------------------------------------------------- 切条


ZWSP = "\u200b\u200c\u200d\u200e\u200f\ufeff"


def clean_text(text: str) -> str:
    """去掉零宽字符和行首残留空格——网页复制常见，不清会把「第X条」挤到行中。"""
    for ch in ZWSP:
        text = text.replace(ch, "")
    return text


def parse_articles(text: str) -> list[dict]:
    """按「第X条」切条，并把最近一层的编/章/节挂到条文上。"""
    lines = [ln.strip() for ln in clean_text(text).splitlines()]
    cleaned, heading = [], None
    for ln in lines:
        if not ln:
            continue
        m = HEADING_RE.match(ln)
        if m:
            head = re.sub(r"\[[^\]]{0,8}编辑[^\]]*\]", "", m.group(2))
            heading = f"{m.group(1)} {head}".strip()
            continue
        if re.fullmatch(r"\[?[^\]]{0,8}编辑\]?", ln):
            continue
        cleaned.append((ln, heading))

    articles, current = [], None
    for ln, hd in cleaned:
        m = ARTICLE_RE.match(ln)
        if m:
            if current:
                articles.append(current)
            current = {
                "article_no": f"第{m.group(1)}条",
                "sort": cn2int(m.group(1)),
                "heading": hd or "",
                "text": m.group(2).strip(),
            }
        elif current:
            current["text"] += "\n" + ln
    if current:
        articles.append(current)

    for a in articles:
        a["text"] = re.sub(r"\n{2,}", "\n", a["text"]).strip()
        a["text"] = re.sub(r"[ \t\u3000]+", " ", a["text"])
    return articles


# ---------------------------------------------------------------- 建库


SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS laws (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  issuer TEXT, doc_no TEXT,
  publish_date TEXT, effective_date TEXT, status TEXT,
  source_url TEXT, source_channel TEXT, official_check TEXT DEFAULT '未核',
  fetched_at TEXT, sha256 TEXT, file_name TEXT, note TEXT
);
CREATE TABLE IF NOT EXISTS articles (
  id INTEGER PRIMARY KEY,
  law_id INTEGER NOT NULL REFERENCES laws(id) ON DELETE CASCADE,
  article_no TEXT NOT NULL,
  sort_key INTEGER,
  heading TEXT,
  text TEXT NOT NULL,
  UNIQUE(law_id, article_no)
);
CREATE INDEX IF NOT EXISTS idx_articles_law ON articles(law_id, sort_key);
"""

CARDS_SCHEMA = """
CREATE TABLE IF NOT EXISTS cards (
  id INTEGER PRIMARY KEY,
  case_no TEXT, cause TEXT, issues TEXT, holding TEXT, our_side TEXT,
  key_point TEXT, source TEXT, quote TEXT, tags TEXT, created_at TEXT
);
CREATE VIRTUAL TABLE IF NOT EXISTS cards_fts USING fts5(
  cause, issues, holding, key_point, quote, content='cards', content_rowid='id', tokenize='trigram'
);
"""

FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(
  article_no, text, content='articles', content_rowid='id', tokenize='trigram'
);
"""


def open_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(path)


def norm_quote(text: str) -> str:
    return "".join(ch for ch in text if ch.isalnum())


def too_short(keyword: str) -> bool:
    """trigram 索引只索引 3 字以上；更短的词走 LIKE，否则会查不到。"""
    return len(norm_quote(keyword)) < 3


def has_fts(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT name FROM sqlite_master WHERE name='articles_fts'").fetchone()
    return bool(row)


def cmd_init(args) -> int:
    conn = open_db(args.db)
    conn.executescript(SCHEMA)
    conn.executescript(CARDS_SCHEMA)
    try:
        conn.executescript(FTS_SCHEMA)
    except sqlite3.OperationalError:
        print("当前 SQLite 不支持 trigram 分词，检索将退回 LIKE（较慢）", file=sys.stderr)
    conn.commit()
    print(f"已初始化 {args.db}")
    return 0


def cmd_import(args) -> int:
    conn = open_db(args.db)
    conn.executescript(SCHEMA)
    if not has_fts(conn):
        try:
            conn.executescript(FTS_SCHEMA)
        except sqlite3.OperationalError:
            pass

    for path in args.files:
        p = Path(path)
        if not p.exists():
            print(f"跳过（不存在）：{p}", file=sys.stderr)
            continue
        text = extract_text(p)
        articles = parse_articles(text)
        if len(articles) < 2:
            print(f"跳过 {p.name}：未切出条文（可能不是法规全文）", file=sys.stderr)
            continue

        name = args.name or p.stem
        sha = hashlib.sha256(p.read_bytes()).hexdigest()
        conn.execute(
            """INSERT INTO laws(name,issuer,doc_no,publish_date,effective_date,status,source_url,
                                source_channel,official_check,fetched_at,sha256,file_name,note)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(name) DO UPDATE SET
                 issuer=excluded.issuer, doc_no=excluded.doc_no,
                 publish_date=excluded.publish_date, effective_date=excluded.effective_date,
                 status=excluded.status, source_url=excluded.source_url,
                 source_channel=excluded.source_channel, official_check=excluded.official_check,
                 fetched_at=excluded.fetched_at, sha256=excluded.sha256, file_name=excluded.file_name,
                 note=excluded.note""",
            (name, args.issuer, args.doc_no, args.publish, args.effective, args.status or "现行有效",
             args.url, args.channel, args.official_check, args.date or date.today().isoformat(),
             sha, _store_path(p), getattr(args, "note", None)),
        )
        law_id = conn.execute("SELECT id FROM laws WHERE name=?", (name,)).fetchone()[0]
        conn.execute("DELETE FROM articles WHERE law_id=?", (law_id,))
        # 同一法条可能被正文引用重复切出（如「依照第X条的规定」另起一行），
        # 按条号去重，保留正文最长的一条
        uniq = {}
        for a in articles:
            old = uniq.get(a["article_no"])
            if old is None or len(a["text"]) > len(old["text"]):
                uniq[a["article_no"]] = a
        articles = list(uniq.values())
        conn.executemany(
            "INSERT INTO articles(law_id,article_no,sort_key,heading,text) VALUES(?,?,?,?,?)",
            [(law_id, a["article_no"], a["sort"], a["heading"], a["text"]) for a in articles],
        )
        print(f"导入 {name}：{len(articles)} 条（{p.name}）")
    conn.commit()

    if has_fts(conn):
        conn.execute("INSERT INTO articles_fts(articles_fts) VALUES('rebuild')")
        conn.commit()
    return 0


def _caveat(check: str) -> str:
    if (check or "") == "已核":
        return ""
    return ("  ⚠ 检索索引：版本日期已标注但未与官方原件逐字比对，引用前须按 citation.md 回读官方原文")


def cmd_query(args) -> int:
    words = args.keyword if isinstance(args.keyword, list) else [args.keyword]
    keyword = " ".join(words)
    match_expr = " AND ".join(f'"{w}"' for w in words if w.strip())
    conn = open_db(args.db)
    if has_fts(conn) and not any(too_short(w) for w in words):
        rows = conn.execute(
            """SELECT l.name, a.article_no, a.heading, a.text, l.source_url, l.fetched_at, l.official_check
               FROM articles_fts f
               JOIN articles a ON a.id = f.rowid
               JOIN laws l ON l.id = a.law_id
               WHERE articles_fts MATCH ? AND (? = '' OR l.name LIKE ?)
               ORDER BY bm25(articles_fts) LIMIT ?""",
            (match_expr, args.law or "", f"%{args.law}%" if args.law else "", args.limit),
        ).fetchall()
    else:
        conds = ["a.text LIKE ?"] * len(words)
        params = [f"%{w}%" for w in words]
        conds.append("(? = '' OR l.name LIKE ?)")
        params += [args.law or "", f"%{args.law}%" if args.law else ""]
        params.append(args.limit)
        rows = conn.execute(
            "SELECT l.name, a.article_no, a.heading, a.text, l.source_url, l.fetched_at, l.official_check "
            "FROM articles a JOIN laws l ON l.id = a.law_id WHERE " + " AND ".join(conds) + " LIMIT ?",
            params,
        ).fetchall()

    if args.json:
        print(json.dumps([{
            "law": r[0], "article_no": r[1], "heading": r[2], "text": r[3],
            "source_url": r[4], "fetched_at": r[5], "official_check": r[6],
        } for r in rows], ensure_ascii=False, indent=2))
        return 0 if rows else 1

    if not rows:
        print(f"未命中：{keyword}（本地库无此内容，请联网检索或补充导入）")
        return 1
    for law, no, heading, text, url, fetched, check in rows:
        print(f"\n【{law}】{no}" + (f"  〔{heading}〕" if heading else ""))
        body = args.chars if hasattr(args, "chars") else 300
        print(text[: body] + ("…" if len(text) > body else ""))
        print(f"  来源：{url or '未记录'}｜导入：{fetched}｜官方复核：{check or '未核'}")
        print(_caveat(check))
    return 0


ABBREV = {
    "刑诉法": "刑事诉讼法", "民诉法": "民事诉讼法", "行诉法": "行政诉讼法",
    "刑诉": "刑事诉讼法", "民诉": "民事诉讼法", "行诉": "行政诉讼法",
    "公司法解释": "公司法", "公司法规定": "公司法",
}


def resolve_laws(conn, hint: str) -> list[str]:
    """把「民诉法解释」「公司法解释（二）」这类简称解析到法规全称。"""
    def q(sql, *params):
        return [r[0] for r in conn.execute(sql, params).fetchall()]

    if not hint:
        return []
    rows = q("SELECT name FROM laws WHERE name LIKE ?", f"%{hint}%")
    if rows:
        return rows

    for short, full in ABBREV.items():
        if hint.startswith(short):
            hint = full + hint[len(short):]
            break

    m = re.search(r"[（(]([一二三四五六七八九十]+)[）)]", hint)
    bracket = m.group(1) if m else ""
    stem = re.sub(r"[（(][一二三四五六七八九十]+[）)]", "", hint)
    stem = re.sub(r"(解释|规定|条例|办法|规则)$", "", stem).strip() or stem

    sql = "SELECT name FROM laws WHERE name LIKE ?"
    params = [f"%{stem}%"]
    if bracket:
        sql += " AND (name LIKE ? OR name LIKE ?)"
        params += [f"%（{bracket}）%", f"%({bracket})%"]
    if stem.endswith("法") and not bracket:
        sql += " AND name LIKE ?"
        params.append("%解释%")
    rows = q(sql, *params)
    if rows:
        return rows

    if len(hint) >= 4:
        return q("SELECT name FROM laws WHERE name LIKE ?", f"%{hint[:4]}%")
    return []


def cmd_article(args) -> int:
    conn = open_db(args.db)
    names = resolve_laws(conn, args.law)
    if names:
        placeholders = ",".join("?" * len(names))
        rows = conn.execute(
            f"""SELECT a.article_no, a.heading, a.text, l.name, l.source_url, l.fetched_at, l.official_check,
                       l.publish_date, l.effective_date
                FROM articles a JOIN laws l ON l.id=a.law_id
                WHERE l.name IN ({placeholders}) AND a.article_no = ?""",
            (*names, args.no),
        ).fetchall()
        if rows:
            for no, heading, text, law, url, fetched, check, pub, eff in rows:
                print(f"【{law}】{no}" + (f"  〔{heading}〕" if heading else ""))
                print(text)
                print(f"\n来源：{url or '未记录'}｜导入：{fetched}｜复核：{check}｜公布：{pub or '-'}｜施行：{eff or '-'}")
                print(_caveat(check))
            return 0
        print(f"已定位到《{names[0]}》，但没有 {args.no}")
        return 1
    rows = conn.execute(
        """SELECT a.article_no, a.heading, a.text, l.name, l.source_url, l.fetched_at, l.official_check,
                  l.publish_date, l.effective_date
           FROM articles a JOIN laws l ON l.id=a.law_id
           WHERE (l.name LIKE ?) AND a.article_no = ?""",
        (f"%{args.law}%", args.no),
    ).fetchall()
    if not rows:
        print("未找到该条，请核对法名与条号（用 query 试关键词）")
        return 1
    for no, heading, text, law, url, fetched, check, pub, eff in rows:
        print(f"【{law}】{no}" + (f"  〔{heading}〕" if heading else ""))
        print(text)
        print(f"\n来源：{url or '未记录'}｜导入：{fetched}｜复核：{check}｜公布：{pub or '-'}｜施行：{eff or '-'}")
        print(_caveat(check))
    return 0


def cmd_stats(args) -> int:
    conn = open_db(args.db)
    laws = conn.execute("SELECT COUNT(*) FROM laws").fetchone()[0]
    arts = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    try:
        cards = conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
    except sqlite3.OperationalError:
        cards = 0
    print(f"法规 {laws} 部，条文 {arts} 条，结案卡片 {cards} 张，库：{args.db}")
    for name, n, fetched in conn.execute(
        """SELECT l.name, COUNT(a.id), l.fetched_at FROM laws l
           LEFT JOIN articles a ON a.law_id=l.id GROUP BY l.id ORDER BY l.id"""):
        print(f"  - {name}：{n} 条（导入 {fetched}）")
    return 0


def cmd_card_add(args) -> int:
    """登记结案卡片：把一次办案的判断沉淀成可检索的东西。"""
    conn = open_db(args.db)
    conn.executescript(CARDS_SCHEMA)
    rows = []
    if args.file:
        data = json.loads(Path(args.file).read_text(encoding="utf-8"))
        rows = data if isinstance(data, list) else [data]
    else:
        rows = [{
            "case_no": args.case_no, "cause": args.cause, "issues": args.issues,
            "holding": args.holding, "our_side": args.our_side, "key_point": args.key_point,
            "source": args.source, "quote": args.quote, "tags": args.tags,
        }]
    for r in rows:
        conn.execute(
            """INSERT INTO cards(case_no,cause,issues,holding,our_side,key_point,source,quote,tags,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (r.get("case_no"), r.get("cause"), r.get("issues"), r.get("holding"), r.get("our_side"),
             r.get("key_point"), r.get("source"), r.get("quote"), r.get("tags"),
             r.get("created_at") or date.today().isoformat()),
        )
    conn.commit()
    conn.execute("INSERT INTO cards_fts(cards_fts) VALUES('rebuild')")
    conn.commit()
    print(f"已登记 {len(rows)} 张卡片")
    return 0


def cmd_card_query(args) -> int:
    conn = open_db(args.db)
    try:
        if too_short(args.keyword):
            raise sqlite3.OperationalError("short")
        rows = conn.execute(
            """SELECT c.case_no,c.cause,c.issues,c.holding,c.key_point,c.quote,c.source,c.created_at
               FROM cards_fts f JOIN cards c ON c.id=f.rowid
               WHERE cards_fts MATCH ? ORDER BY bm25(cards_fts) LIMIT ?""",
            (args.keyword, args.limit),
        ).fetchall()
    except sqlite3.OperationalError:
        rows = conn.execute(
            """SELECT case_no,cause,issues,holding,key_point,quote,source,created_at FROM cards
               WHERE cause LIKE ? OR issues LIKE ? OR key_point LIKE ? OR quote LIKE ? LIMIT ?""",
            tuple([f"%{args.keyword}%"] * 4 + [args.limit]),
        ).fetchall()
    if not rows:
        print(f"未命中卡片：{args.keyword}")
        return 1
    for r in rows:
        print(f"\n【{r[1] or '-'}】{r[0] or '未记案号'}（{r[7]}）")
        if r[2]: print(f"  争点：{r[2]}")
        if r[3]: print(f"  裁判：{r[3]}")
        if r[4]: print(f"  我方要点：{r[4]}")
        if r[5]: print(f"  摘录：{r[5][:80]}")
        if r[6]: print(f"  来源：{r[6]}")
    return 0


def cmd_card_list(args) -> int:
    conn = open_db(args.db)
    conn.executescript(CARDS_SCHEMA)
    rows = conn.execute("SELECT case_no,cause,key_point,created_at FROM cards ORDER BY id DESC LIMIT ?",
                        (args.limit,)).fetchall()
    print(f"卡片 {conn.execute('SELECT COUNT(*) FROM cards').fetchone()[0]} 张")
    for r in rows:
        print(f"  - {r[1] or '-'}｜{r[0] or '未记案号'}｜{(r[2] or '')[:30]}｜{r[3]}")
    return 0


def cmd_seed(args) -> int:
    """按 data/manifest.json 批量导入——建库只需一条命令。"""
    manifest = Path(args.manifest)
    if not manifest.exists():
        print(f"找不到 {manifest}", file=sys.stderr)
        return 2
    entries = json.loads(manifest.read_text(encoding="utf-8"))
    ok = 0
    for e in entries:
        f = ROOT / e["file"] if not Path(e["file"]).is_absolute() else Path(e["file"])
        if not f.exists():
            print(f"跳过（文件缺失）：{e['file']}", file=sys.stderr)
            continue
        args.files, args.name = [str(f)], e.get("name")
        args.issuer, args.doc_no = e.get("issuer"), e.get("doc_no")
        args.publish, args.effective = e.get("publish"), e.get("effective")
        args.status, args.url = e.get("status"), e.get("url")
        args.channel = e.get("channel", "官方页面")
        args.official_check = e.get("official_check", "未核")
        args.note = e.get("note")
        args.date = e.get("fetched_at")
        cmd_import(args)
        ok += 1
    print(f"共处理 {ok} 部")
    return 0


def cmd_verify(args) -> int:
    """校验库内记载的 sha256 与磁盘文件是否一致——回读校验的机器版。"""
    conn = open_db(args.db)
    rows = conn.execute("SELECT name, file_name, sha256 FROM laws").fetchall()
    ok = miss = bad = 0
    for name, file_name, sha in rows:
        path = Path(file_name)
        if not path.is_absolute():
            path = (ROOT / path).resolve()
        if not path.exists():
            miss += 1
            continue
        if hashlib.sha256(path.read_bytes()).hexdigest() == sha:
            ok += 1
        else:
            bad += 1
            print(f"  ✗ 已变更：{name}（{file_name}）——需重新导入并复查引用")
    print(f"一致性：一致 {ok}／文件缺失 {miss}／内容变更 {bad}")
    return 1 if bad else 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="本地法条库")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="初始化数据库").set_defaults(func=cmd_init)

    p = sub.add_parser("import", help="导入法规文件")
    p.add_argument("files", nargs="+")
    p.add_argument("--name")
    p.add_argument("--issuer")
    p.add_argument("--doc-no")
    p.add_argument("--publish")
    p.add_argument("--effective")
    p.add_argument("--status")
    p.add_argument("--url")
    p.add_argument("--channel", default="官方页面")
    p.add_argument("--official-check", default="未核")
    p.add_argument("--note", help="来源与限制说明")
    p.add_argument("--date")
    p.set_defaults(func=cmd_import)

    q = sub.add_parser("query", help="全文检索")
    q.add_argument("keyword", nargs="+", help="一个或多个关键词（自动按 AND 组合）")
    q.add_argument("--law")
    q.add_argument("--limit", type=int, default=5)
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=cmd_query)

    a = sub.add_parser("article", help="按条号取原文")
    a.add_argument("law")
    a.add_argument("no", help="如 第五百八十五条")
    a.set_defaults(func=cmd_article)

    sd = sub.add_parser("seed", help="按 data/manifest.json 批量导入")
    sd.add_argument("--manifest", default=str(ROOT / "data" / "manifest.json"))
    sd.set_defaults(func=cmd_seed)

    ca = sub.add_parser("card-add", help="登记结案卡片")
    ca.add_argument("--file", help="JSON 文件（单条或数组）")
    ca.add_argument("--case-no"); ca.add_argument("--cause"); ca.add_argument("--issues")
    ca.add_argument("--holding"); ca.add_argument("--our-side"); ca.add_argument("--key-point")
    ca.add_argument("--source"); ca.add_argument("--quote"); ca.add_argument("--tags")
    ca.set_defaults(func=cmd_card_add)

    cq = sub.add_parser("card-query", help="检索卡片")
    cq.add_argument("keyword"); cq.add_argument("--limit", type=int, default=5)
    cq.set_defaults(func=cmd_card_query)

    cl = sub.add_parser("card-list", help="卡片列表")
    cl.add_argument("--limit", type=int, default=10)
    cl.set_defaults(func=cmd_card_list)

    sub.add_parser("stats", help="库概况").set_defaults(func=cmd_stats)
    sub.add_parser("verify", help="校验导入文件与库内哈希").set_defaults(func=cmd_verify)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
