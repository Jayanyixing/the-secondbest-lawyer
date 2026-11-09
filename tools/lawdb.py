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
CARDS_DB = ROOT / "data" / "cards.sqlite"   # 93 张脱敏卡，入库；全量在 cards.full.sqlite

CN_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
             "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
CN_UNITS = {"十": 10, "百": 100, "千": 1000}

ARTICLE_RE = re.compile(
    r"^\s*第([零〇一二三四五六七八九十百千两\d]{1,8})条(?:之([零〇一二三四五六七八九十百千两\d]{1,4}))?"
    # 跨行引用「第五十条」「第三十八条第一款」不带空格才排除：
    # 「第九十九条 和解协议…」这类正文本身就以「和/的/规定」开头的真条文必须放过
    r"(?!\s*(?:[、，,。；：）》]|第[零〇一二三四五六七八九十百千两\d]+[款项]))"
    r"(?!(?:规定|的|所称|所述|和|及|或|至))"
    r"[\s\u3000　]*(.*)$",
    re.M,
)
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
    xml = xml.replace("\r", "").replace("\n", "")
    xml = re.sub(r"</w:p>|<w:(?:br|cr)\b[^>]*/?>", "\n", xml)
    parts = re.findall(r"<w:t(?:\s[^>]*)?>(.*?)</w:t>|(\n)", xml)
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



_CN_DIGITS = "零一二三四五六七八九"


def cn_num(n: int) -> str:
    """1–9999 转中文条号用字：38→三十八，105→一百零五，1260→一千二百六十。"""
    if n <= 0:
        return str(n)
    units = ["", "十", "百", "千"]
    digits = [int(d) for d in str(n)]
    out, zero = "", False
    for i, d in enumerate(digits):
        pos = len(digits) - i - 1
        if d == 0:
            zero = True
            continue
        if zero and out:
            out += "零"
        zero = False
        out += _CN_DIGITS[d] + units[pos]
    if out.startswith("一十"):
        out = out[1:]
    return out


def normalize_article_no(raw: str) -> str:
    """把「38」「38条」「第38条」「第三十八条」「第38条之一」统一成库里的写法。"""
    s = (raw or "").strip().replace(" ", "")
    if not s:
        return s
    main, _, sub = s.partition("之")
    for suffix in ("条", "款", "项"):
        if main.endswith(suffix):
            main = main[: -len(suffix)]
    main = main.lstrip("第")
    if main.isdigit():
        main = cn_num(int(main))
    out = f"第{main}条"
    if sub:
        sub = sub.strip("条第款 ")
        if sub.isdigit():
            sub = cn_num(int(sub))
        out += f"之{sub}"
    return out

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
            sub_no = f"之{m.group(2)}" if m.group(2) else ""
            current = {
                "article_no": f"第{m.group(1)}条{sub_no}",
                "sort": cn2int(m.group(1)),
                "heading": hd or "",
                "text": m.group(3).strip(),
            }
        elif current:
            current["text"] += "\n" + ln
    if current:
        articles.append(current)

    # 「第一百三十三条之一」这类独立条号：刑法修正案常用，不能并进基础条
    out = []
    for a in articles:
        m = re.match(r"^之([一二三四五六七八九十]+)[\s\u3000]*(.*)$", a["text"], re.S)
        if m:
            a = dict(a)
            a["article_no"] = f"{a['article_no']}之{m.group(1)}"
            a["text"] = m.group(2).strip()
        out.append(a)

    for a in out:
        a["text"] = re.sub(r"\n{2,}", "\n", a["text"]).strip()
        a["text"] = re.sub(r"[ \t\u3000]+", " ", a["text"])
    return out


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
  key_point TEXT, source TEXT, quote TEXT, tags TEXT, created_at TEXT,
  verify_status TEXT DEFAULT 'pending',
  kind TEXT DEFAULT 'judgment'
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


def ensure_cards_schema(conn: sqlite3.Connection) -> None:
    """补 verify_status 列（老库升级用），并保证 FTS 存在。"""
    conn.executescript(CARDS_SCHEMA)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(cards)").fetchall()]
    if "kind" not in cols:
        conn.execute("ALTER TABLE cards ADD COLUMN kind TEXT DEFAULT 'judgment'")
        conn.execute("UPDATE cards SET kind='judgment' WHERE kind IS NULL")
        conn.commit()
    if "verify_status" not in cols:
        conn.execute("ALTER TABLE cards ADD COLUMN verify_status TEXT DEFAULT 'pending'")
        conn.execute("UPDATE cards SET verify_status='pending' WHERE verify_status IS NULL")
        conn.commit()


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
    "道交": "道路交通事故", "建工": "建设工程", "执异": "执行异议",
}


def resolve_laws(conn, hint: str) -> list[str]:
    """把「民诉法解释」「公司法解释（二）」这类简称解析到法规全称。"""
    def q(sql, *params):
        return [r[0] for r in conn.execute(sql, params).fetchall()]

    if not hint:
        return []
    has_sub_suffix = bool(re.search(r"(解释|规定|条例|办法|规则|纪要|意见|批复)$", hint))
    rows = q("SELECT name FROM laws WHERE name LIKE ?", f"%{hint}%")
    if rows:
        return rows

    for short, full in ABBREV.items():
        if hint.startswith(short):
            hint = full + hint[len(short):]
            break

    m = re.search(r"[（(]([一二三四五六七八九十]+)[）)]", hint)
    bracket = m.group(1) if m else ""
    if not has_sub_suffix and not bracket:
        rows = (
            q("SELECT name FROM laws WHERE name LIKE ? AND name NOT LIKE '%解释%' AND name NOT LIKE '%规定%'", f"%{hint}%")
            or q("SELECT name FROM laws WHERE name LIKE ?", f"%{hint}%")
        )
        if rows:
            return rows
    stem = re.sub(r"[（(][一二三四五六七八九十]+[）)]", "", hint)
    stem = re.sub(r"(解释|规定|条例|办法|规则)$", "", stem).strip() or stem

    sql = "SELECT name FROM laws WHERE name LIKE ?"
    params = [f"%{stem}%"]
    if bracket:
        sql += " AND (name LIKE ? OR name LIKE ?)"
        params += [f"%（{bracket}）%", f"%({bracket})%"]
    if has_sub_suffix and stem.endswith("法") and not bracket:
        sql += " AND name LIKE ?"
        params.append("%解释%")
    rows = q(sql, *params)
    if rows:
        return rows

    # 「公司法时间效力规定」这类：《法名》+ 主题词，允许跨书名号匹配
    for i, ch in enumerate(hint):
        if ch == "法" and len(hint) - i > 3:
            a, b = hint[: i + 1], hint[i + 1:]
            b = re.sub(r"(解释|规定|条例|办法|规则)$", "", b).strip()
            if len(a) >= 2 and len(b) >= 2:
                rows = q("SELECT name FROM laws WHERE name LIKE ? AND name LIKE ?", f"%{a}%", f"%{b}%")
                if rows:
                    return rows

    # 去掉顿号/标点后再比一次（「查封扣押冻结」vs「查封、扣押、冻结」）
    def strip_punct(x: str) -> str:
        return re.sub(r"[、，,．.·\s]", "", x)

    rows = q(
        "SELECT name FROM laws WHERE replace(replace(replace(name,'、',''),'，',''),' ','') LIKE ?",
        f"%{strip_punct(hint)}%",
    )
    if rows:
        return rows
    if len(hint) >= 4:
        rows = q("SELECT name FROM laws WHERE name LIKE ?", f"%{hint[:4]}%")
        if rows:
            return rows

    # 最后一招：疑似度匹配，容忍「的」「、」等差异
    import difflib

    names = q("SELECT name FROM laws")
    scored = sorted(((difflib.SequenceMatcher(None, hint, n).ratio(), n) for n in names), reverse=True)
    return [scored[0][1]] if scored and scored[0][0] >= 0.45 else []


def cmd_article(args) -> int:
    args.no = normalize_article_no(args.no)
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
    cards = 0
    try:
        if CARDS_DB.exists():
            cc = sqlite3.connect(CARDS_DB)
            cards = cc.execute("SELECT COUNT(*) FROM cards WHERE verify_status='verified'").fetchone()[0]
            pend = cc.execute("SELECT COUNT(*) FROM cards WHERE verify_status!='verified'").fetchone()[0]
            cards = f"{cards}（另 {pend} 张待核）"
    except sqlite3.OperationalError:
        pass
    print(f"法规 {laws} 部，条文 {arts} 条，结案卡片 {cards} 张，库：{args.db}")
    for name, n, fetched in conn.execute(
        """SELECT l.name, COUNT(a.id), l.fetched_at FROM laws l
           LEFT JOIN articles a ON a.law_id=l.id GROUP BY l.id ORDER BY l.id"""):
        print(f"  - {name}：{n} 条（导入 {fetched}）")
    return 0


CARD_FIELDS = ["case_no", "cause", "issues", "holding", "our_side", "key_point", "quote", "source", "tags"]
CASE_NO_RE = re.compile(
    r"^(?:"
    r"[（(](?:19|20)\d{2}[）)][^\s]{2,30}号"                    # 法院：（2024）京03民终16167号
    r"|[^\s]{2,20}[［\[（(](?:19|20)\d{2}[］\]）)][^\s]{0,20}号"  # 仲裁：京朝劳人仲字［2022］第27149号
    r")$"
)
MASK_RE = re.compile(r"[XxＸｘ＊*]")
# 来源编号（典型案例、指导案例、入库编号）不是真实案号，不涉及个人信息，无须遮罩
SOURCE_ID_RE = re.compile(r"典型案例|指导案例|指导性案例|公报案例|入库编号|参考案例")
# 规则卡：规范名称或审判指导文件，没有案号
RULE_ID_RE = re.compile(r"《[^》]{2,50}》|纪要|指导意见|批复|会议纪要")


def validate_card(c: dict) -> list[str]:
    """卡片入库前的硬校验。任何一条不过，整批不入库。"""
    errs = [f"缺字段 {f}" for f in CARD_FIELDS if not str(c.get(f) or "").strip()]
    kind_hint = str(c.get("kind") or "judgment").strip()
    hi = 120 if kind_hint == "rule" else 60
    quote = str(c.get("quote") or "").strip()
    if quote and not 8 <= len(quote) <= hi:
        errs.append(f"摘录长度 {len(quote)} 字（{kind_hint} 要求 8–{hi}，必须是原文，概述不算）")
    kind = str(c.get("kind") or "judgment").strip()
    if kind not in ("judgment", "rule"):
        errs.append(f"kind 取值不合规：{kind}（judgment / rule）")
    no = str(c.get("case_no") or "").strip()
    if no:
        if kind == "rule":
            if not RULE_ID_RE.search(no):
                errs.append(f"规则卡来源标识不合规：{no}（须为《法规名》或会议纪要/指导意见名称）")
        elif SOURCE_ID_RE.search(no):
            pass  # 来源编号放行：保留 01/02 等序号，检索才有区分度
        elif not CASE_NO_RE.match(no):
            errs.append(f"案号格式不符：{no}（应为「（年份）…号」或来源编号）")
        elif not MASK_RE.search(no):
            errs.append(f"案号未脱敏：{no}（真实案号须保留 X 或 ＊ 作遮罩）")
    side = str(c.get("our_side") or "").strip()
    if side and side not in ("原告", "被告", "第三人", "上诉人", "被上诉人", "申请人", "被申请人",
                             "再审申请人", "被申请人（再审）", "辩护人", "被害人代理",
                             "劳动者", "用人单位", "承包人", "发包人", "实际施工人", "买受人", "出卖人",
                             "出租人", "承租人", "保证人", "债权人", "债务人", "其他"):
        errs.append(f"立场取值不规范：{side}")
    return errs


def cmd_card_add(args) -> int:
    """登记结案卡片。整批校验通过才入库；重复（同案号+同争点）跳过。"""
    conn = open_db(args.db)
    ensure_cards_schema(conn)

    if args.file:
        data = json.loads(Path(args.file).read_text(encoding="utf-8"))
        rows = data if isinstance(data, list) else [data]
    else:
        rows = [{
            "case_no": args.case_no, "cause": args.cause, "issues": args.issues,
            "holding": args.holding, "our_side": args.our_side, "key_point": args.key_point,
            "source": args.source, "quote": args.quote, "tags": args.tags,
            "kind": getattr(args, "kind", "judgment"),
        }]

    problems, seen, batch_dupes = [], set(), set()
    for i, r in enumerate(rows, start=1):
        errs = validate_card(r)
        if errs:
            problems.append((i, r.get("case_no") or "-", errs))
        key = (str(r.get("case_no") or "").strip(), str(r.get("issues") or "").strip())
        if key in seen:
            batch_dupes.add(key)
        seen.add(key)

    if batch_dupes:
        for no, issue in batch_dupes:
            problems.append((0, no, [f"批次内重复：案号 {no} + 争点「{issue}」"]))

    if problems:
        print(f"校验未通过：{len(problems)} 处，整批不入库")
        for i, no, errs in problems:
            where = f"第 {i} 条" if i else "批次"
            print(f"  - {where}（{no}）：" + "；".join(errs))
        return 1

    inserted = skipped = 0
    for r in rows:
        key = (str(r.get("case_no") or "").strip(), str(r.get("issues") or "").strip())
        exists = conn.execute(
            "SELECT id FROM cards WHERE case_no=? AND issues=?", key
        ).fetchone()
        if exists:
            if not args.replace:
                skipped += 1
                continue
            conn.execute("DELETE FROM cards WHERE id=?", (exists[0],))
        conn.execute(
            """INSERT INTO cards(case_no,cause,issues,holding,our_side,key_point,source,quote,tags,created_at,verify_status,kind)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (r.get("case_no"), r.get("cause"), r.get("issues"), r.get("holding"), r.get("our_side"),
             r.get("key_point"), r.get("source"), r.get("quote"), r.get("tags"),
             r.get("created_at") or date.today().isoformat(),
             r.get("verify_status") or "pending", r.get("kind") or "judgment"),
        )
        inserted += 1
    conn.commit()
    conn.execute("INSERT INTO cards_fts(cards_fts) VALUES('rebuild')")
    conn.commit()
    msg = f"已登记 {inserted} 张卡片"
    if skipped:
        msg += f"，跳过 {skipped} 张已存在（同案号+同争点）"
    print(msg)
    return 0


def load_synonyms() -> dict:
    f = ROOT / "data" / "card-synonyms.txt"
    syn = {}
    if not f.exists():
        return syn
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        syn[k.strip()] = [x.strip() for x in v.split(",") if x.strip()]
    return syn


def expand(word: str, syn: dict) -> list[str]:
    return [word] + [x for x in syn.get(word, []) if x != word]


def cmd_card_query(args) -> int:
    conn = open_db(args.db)
    ensure_cards_schema(conn)
    words = args.keyword if isinstance(args.keyword, list) else [args.keyword]
    kw = " ".join(words)
    syn = load_synonyms()
    groups = [expand(w, syn) for w in words]
    match_expr = " AND ".join("(" + " OR ".join(f'"{x}"' for x in g) + ")" for g in groups if g)
    try:
        if any(too_short(x) for g in groups for x in g):
            raise sqlite3.OperationalError("short")
        rows = conn.execute(
            """SELECT c.case_no,c.cause,c.issues,c.holding,c.key_point,c.quote,c.source,c.created_at,c.verify_status,c.kind
               FROM cards_fts f JOIN cards c ON c.id=f.rowid
               WHERE cards_fts MATCH ? AND (? = '' OR c.verify_status = ?) AND (? = '' OR c.kind = ?)
               ORDER BY bm25(cards_fts) LIMIT ?""",
            (match_expr, args.status or "", args.status or "", getattr(args,"kind",None) or "", getattr(args,"kind",None) or "", args.limit),
        ).fetchall()
        if not rows:
            raise sqlite3.OperationalError("fts-empty")
    except sqlite3.OperationalError:
        blob = ("coalesce(cause,'')||coalesce(issues,'')||coalesce(holding,'')"
                "||coalesce(key_point,'')||coalesce(quote,'')||coalesce(tags,'')")
        conds = " AND ".join("(" + " OR ".join([f"{blob} LIKE ?"] * len(g)) + ")" for g in groups)
        sql = ("SELECT case_no,cause,issues,holding,key_point,quote,source,created_at,verify_status,kind "
               f"FROM cards WHERE {conds} AND (? = '' OR verify_status = ?) AND (? = '' OR kind = ?) LIMIT ?")
        params = [f"%{x}%" for g in groups for x in g] + [args.status or "", args.status or "",
                                              getattr(args, "kind", None) or "", getattr(args, "kind", None) or "",
                                              args.limit]
        rows = conn.execute(sql, params).fetchall()
    if not rows:
        print(f"未命中卡片：{kw}")
        return 1
    for r in rows:
        print(f"\n【{r[1] or '-'}】{r[0] or '未记案号'}（{r[7]}）〔{r[8] or 'pending'}｜{r[9] or 'judgment'}〕")
        if r[2]: print(f"  争点：{r[2]}")
        if r[3]: print(f"  裁判：{r[3]}")
        if r[4]: print(f"  我方要点：{r[4]}")
        if r[5]: print(f"  摘录：{r[5][:80]}")
        if r[6]: print(f"  来源：{r[6]}")
    return 0


def cmd_card_export(args) -> int:
    """把卡片导出成可入库的 JSON（供版本管理／备份／换机）。"""
    conn = open_db(args.db)
    ensure_cards_schema(conn)
    cols = ["case_no", "cause", "issues", "holding", "our_side", "key_point",
            "quote", "source", "tags", "kind", "verify_status", "created_at"]
    rows = conn.execute(f"SELECT {','.join(cols)} FROM cards ORDER BY id").fetchall()
    data = [dict(zip(cols, r)) for r in rows]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"已导出 {len(data)} 张 → {out}")
    return 0


def cmd_card_review(args) -> int:
    """批量复核：拿 pending 卡的摘录去快照／本地法条库里找，命中即标 verified。"""
    conn = open_db(args.db)
    ensure_cards_schema(conn)
    snaps = sorted(Path(args.snapshots).glob("*.txt")) if Path(args.snapshots).exists() else []
    laws = sorted((ROOT / "data" / "sources" / "lawrefbook").glob("*.md"))
    corpus = {}
    for f in snaps + laws:
        corpus[f.name] = norm_quote(f.read_text(encoding="utf-8", errors="ignore"))

    rows = conn.execute("SELECT id, case_no, issues, quote, source, kind FROM cards WHERE verify_status!='verified'").fetchall()
    ok, miss = [], []
    for cid, no, issues, quote, source, kind in rows:
        q = norm_quote(quote or "")
        hit = next((name for name, text in corpus.items() if q and q in text), None)
        if hit:
            conn.execute("UPDATE cards SET verify_status='verified', source=source||? WHERE id=?",
                         (f"｜复核命中快照/本地库：{hit}", cid))
            ok.append((cid, no, hit))
        else:
            miss.append((cid, no, issues[:30]))
    conn.commit()
    print(f"复核：命中并标 verified {len(ok)} 张；仍未命中 {len(miss)} 张")
    for cid, no, hit in ok:
        print(f"  ✓ {cid} {no[:26]} ← {hit}")
    for cid, no, iss in miss:
        print(f"  ✗ {cid} {no[:26]} | {iss}")
    return 0 if not miss else 1


def cmd_card_verify(args) -> int:
    """把卡片的摘录核验状态置为 verified / pending。"""
    conn = open_db(args.db)
    ensure_cards_schema(conn)
    sql = "SELECT id FROM cards WHERE case_no LIKE ?"
    params = [f"%{args.case_no}%"]
    if args.issues:
        sql += " AND issues LIKE ?"
        params.append(f"%{args.issues}%")
    ids = [r[0] for r in conn.execute(sql, params).fetchall()]
    if not ids:
        print("没有匹配的卡片")
        return 1
    conn.executemany("UPDATE cards SET verify_status=? WHERE id=?", [(args.status, i) for i in ids])
    conn.commit()
    print(f"已把 {len(ids)} 张卡片标记为 {args.status}")
    return 0


def cmd_card_list(args) -> int:
    conn = open_db(args.db)
    ensure_cards_schema(conn)
    conn.executescript(CARDS_SCHEMA)
    rows = conn.execute("SELECT case_no,cause,key_point,created_at,verify_status,kind FROM cards ORDER BY id DESC LIMIT ?",
                        (args.limit,)).fetchall()
    print(f"卡片 {conn.execute('SELECT COUNT(*) FROM cards').fetchone()[0]} 张")
    for r in rows:
        print(f"  - [{r[4] or 'pending'}｜{r[5] or 'judgment'}] {r[1] or '-'}｜{r[0] or '未记案号'}｜{(r[2] or '')[:30]}｜{r[3]}")
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
    ca.add_argument("--replace", action="store_true", help="同案号+同争点已存在时覆盖（默认跳过）")
    ca.add_argument("--kind", choices=["judgment", "rule"], default="judgment", help="judgment 判例卡 / rule 规则卡")
    ca.set_defaults(func=cmd_card_add)

    cq = sub.add_parser("card-query", help="检索卡片")
    cq.add_argument("keyword", nargs="+", help="一个或多个关键词（自动 AND）")
    cq.add_argument("--limit", type=int, default=5)
    cq.add_argument("--status", choices=["verified", "pending"], help="只看已核／待核")
    cq.add_argument("--kind", choices=["judgment", "rule"], help="只看判例卡／规则卡")
    cq.set_defaults(func=cmd_card_query)

    ce = sub.add_parser("card-export", help="导出卡片 JSON（可入库／备份）")
    ce.add_argument("--out", default=str(ROOT / "data" / "cards.json"))
    ce.set_defaults(func=cmd_card_export)

    cr = sub.add_parser("card-review", help="批量复核 pending 卡（对照快照/本地库）")
    cr.add_argument("--snapshots", default=str(ROOT / "templates" / "snapshots"))
    cr.set_defaults(func=cmd_card_review)

    cv = sub.add_parser("card-verify", help="标记摘录核验状态")
    cv.add_argument("--case-no", required=True, help="案号（支持模糊匹配）")
    cv.add_argument("--issues", help="限定争点关键词")
    cv.add_argument("--status", choices=["verified", "pending"], default="verified")
    cv.set_defaults(func=cmd_card_verify)

    cl = sub.add_parser("card-list", help="卡片列表")
    cl.add_argument("--limit", type=int, default=10)
    cl.set_defaults(func=cmd_card_list)

    sub.add_parser("stats", help="库概况").set_defaults(func=cmd_stats)
    sub.add_parser("verify", help="校验导入文件与库内哈希").set_defaults(func=cmd_verify)

    args = ap.parse_args(argv)
    # 卡片含当事人信息：默认写独立库，避免随仓库外泄
    if args.cmd.startswith("card") and "--db" not in argv:
        args.db = CARDS_DB
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
