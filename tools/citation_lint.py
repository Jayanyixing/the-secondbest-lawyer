#!/usr/bin/env python3
"""交付前引用校验器。

把「不许编造」从口号变成可执行检查。能查的是**形式一致性**：正文案号是否都有底稿、
底稿是否带摘录、摘录是否出现在引用处、摘录是否是真能证伪的原文、摘录是否被复用、
条目是否回读过、期限日期是否带状态、是否出现绝对化措辞。

不能查的是真伪——底稿里那条案例本身是不是真的，只有回读和律师本人能定。不要
把「校验通过」当成「已核实」。

用法：
    python3 tools/citation_lint.py 交付物.md --ledger citations.json
    python3 tools/citation_lint.py 交付物.md --ledger 底稿.md --mode review
    python3 tools/citation_lint.py 交付物.md --ledger 底稿.md --strict

退出码：0 通过；1 有错误。无第三方依赖。
"""

from __future__ import annotations

import argparse
import json
from datetime import date
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------- 词表与规则

WEAK_SCOPES = {"abstract", "title", "none"}
QUOTE_SCOPES = {"full", "excerpt"}
SCOPE_WORDS = [("全文", "full"), ("节选", "excerpt"), ("摘要", "abstract"), ("标题", "title"), ("未读", "none")]
CHECK_WORDS = [("已核", "verified"), ("未核", "unverified"), ("不适用", "na")]
EFFECT_WORDS = [("已确认生效", "effective"), ("未确认", "unconfirmed"), ("存在后续", "subsequent")]
NORM_STATUS_WORDS = [
    ("未确认", "unconfirmed"),
    ("已废止", "repealed"),
    ("已修改", "amended"),
    ("未施行", "not_effective"),
    ("现行有效", "current"),
]

REQUIRED_FIELDS = ["id", "type", "number", "location", "read_scope", "official_check", "channel"]

NORM_UNCONFIRMED = "unconfirmed"


def normalize_norm_status(raw):
    """规范效力统一取值：没填 → unknown；填了但不在词表 → unconfirmed（按「未确认」处理）。

    两个值语义不同，不要合并：unknown 表示「这一栏没登记」，unconfirmed 表示
    「登记了，结论就是没确认」。前者只触发缺字段警告，后者用于结论时是错误。
    """
    if raw is None or not str(raw).strip():
        return "unknown"
    if raw in ("unknown", "current", "unconfirmed", "repealed", "amended", "not_effective"):
        return str(raw)
    return pick(NORM_STATUS_WORDS, raw, NORM_UNCONFIRMED)


def _is_future(day: str) -> bool:
    try:
        return date.fromisoformat(day) > date.today()
    except ValueError:
        return False


NEG_MARKERS = re.compile(r"(不|非|无|未|勿|别|没有|并非|不是|不得|不能|不可|尚未)")
CLAUSE_BREAK = re.compile(r"[，,。；;、！!？?\n]")


def affirms_claim(text: str, word: str) -> bool:
    """正文是否**肯定地**声称了 word。

    否定只在**同一分句内**算数：「本稿不是可交付稿」「无一条已核实」不算声称，
    但「本稿未经回读，已核实」是在肯定第二分句，仍算声称。故先按逗号、句号、
    分号、顿号、换行切出所在分句，只看分句内 word 之前的部分有没有否定词。
    """
    for m in re.finditer(re.escape(word), text):
        start = 0
        for b in CLAUSE_BREAK.finditer(text, 0, m.start()):
            start = b.end()
        before = text[start:m.start()]
        if NEG_MARKERS.search(before):
            continue
        return True
    return False


CHECK_CANON = {"verified", "unverified", "na"}
CHANNEL_WORDS = [("官方", "official"), ("商业", "commercial"), ("导出", "user_export"), ("口述", "oral")]
CHANNEL_CANON = {"official", "commercial", "user_export", "oral"}
SCOPE_CANON = {"full", "excerpt", "abstract", "title", "none"}
EFFECT_CANON = {"effective", "unconfirmed", "subsequent"}


CHECK_NEG_RE = re.compile(r"(未|尚未|没有|无法|不能|不予)[^核]{0,6}核")


CHECK_VERIFIED_TEXT = {
    "verified",
    "已核",
    "已核实",
    "官方已核",
    "已核（与官方原文一致）",
}
CHECK_UNVERIFIED_TEXT = {
    "unverified",
    "未核",
    "未核（仅商业库或转载）",
    "未经核实",
    "未能核实",
    "尚未核",
}
CHECK_PENDING_RE = re.compile(r"(待核|待核实|核对中|核实中|核中|核对中)")


def normalize_check(raw, out_of_vocab: list[str] | None = None) -> str:
    """官方复核取值：**默认拒绝**——只有词表内的写法才可能被判为「已核」。

    1. 词表内英文值原样返回；已登记的肯定变体（已核／已核实／官方已核／
       「已核（与官方原文一致）」）返回 `verified`；已登记的否定变体返回 `unverified`。
    2. 其余任何写法，只要带「核」字（含「未经官方核实」「尚未经官方核对」
       「未能与官方原文核对」「未完成核对」「核对中」「待核」「基本核实」），
       一律按 `unverified` 处理，并把原写法交给调用方提示——宁可多标未核，
       不可凭「核」字猜测已核。
    """
    if raw is None or not str(raw).strip():
        return "unknown"
    v = str(raw).strip()
    if v in CHECK_CANON:
        return v
    if v in ("unknown", "na", "不适用"):
        return "na"
    if v in CHECK_VERIFIED_TEXT:
        return "verified"
    if v in CHECK_UNVERIFIED_TEXT:
        return "unverified"
    if CHECK_NEG_RE.search(v) or CHECK_PENDING_RE.search(v) or "核" in v:
        if out_of_vocab is not None:
            out_of_vocab.append(v)
        return "unverified"
    # 不含「核」的写法（「已比对一致」「与官方原文一致」「已验证」「已确认」
    # 「已查证」「一致」）同样不认——不认识的写法一律按未核，并提示写进汇总。
    if out_of_vocab is not None:
        out_of_vocab.append(v)
    return "unverified"


CHECK_ALLOWED_FOREIGN = CHECK_UNVERIFIED_TEXT | {"", "na", "不适用", "unknown"}

# 与 citation.md「官方复核」清单保持一致的站点表：(主机名, 路径前缀)
# 匹配规则：主机名**等于**白名单域名，或以 "." + 白名单域名结尾；不认裸 gov.cn。
OFFICIAL_SITES: list[tuple[str, str | None]] = [
    ("court.gov.cn", None),
    ("npc.gov.cn", None),
    ("www.gov.cn", "/zhengce/xxgk/gjgzk/"),
    ("bjrd.gov.cn", None),
    ("beijing.gov.cn", None),
    ("bjcourt.gov.cn", None),
    ("spp.gov.cn", None),
]
URL_RE = re.compile(r"https?://[^\s，。；、）)\]】>\"']+")
HOST_RE = re.compile(r"(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+(?:cn|com|net|org|gov|edu|io|hk|tw|info)")


def sites_in(text: str) -> list[tuple[str, str | None]]:
    """取出出处分里的 (主机名, 路径)：带协议的取真正 host，裸域名 path 记为 None。"""
    out: list[tuple[str, str | None]] = []
    rest = text or ""
    for m in URL_RE.finditer(rest):
        url = m.group(0)
        mh = HOST_RE.search(url)
        if not mh:
            continue
        host = mh.group(0).lower()
        tail = url[mh.end():]
        path = tail.split("?")[0].split("#")[0] if tail else ""
        out.append((host, path or "/"))
    rest = URL_RE.sub(" ", rest)
    for mh in HOST_RE.finditer(rest):
        host = mh.group(0).lower()
        if not any(h == host for h, _ in out):
            out.append((host, None))
    return out


def site_ok(host: str, path: str | None) -> bool:
    for domain, prefix in OFFICIAL_SITES:
        if not (host == domain or host.endswith("." + domain)):
            continue
        if prefix is None:
            return True
        if path is not None and path.startswith(prefix):
            return True
        return False
    return False


def domains_in(text: str) -> list[str]:
    return [h for h, _ in sites_in(text)]


def official_domain_ok(text: str) -> bool | None:
    """True＝出处都在官方白名单；False＝有不规范域名；None＝根本没写域名。"""
    found = sites_in(text)
    if not found:
        return None
    return all(site_ok(h, p) for h, p in found)


def has_official_site(text: str) -> bool:
    return any(site_ok(h, p) for h, p in sites_in(text))


def check_allowed_for_channel(raw, channel: str = "", source: str = "") -> bool:
    """非官方渠道的官方复核栏：只接受未核词表、不适用或留空。

    不认识的肯定写法（「已比对一致」「已验证」「基本核实」）一律不许出现，
    否则调用方会在 R18 报错——渠道拿不出官方原文，就没有资格写「已核」。
    """
    if raw is None:
        return True
    v = str(raw).strip()
    if v in CHECK_ALLOWED_FOREIGN:
        return True
    # 官方站点下载的导出件：出处写明官方链接时才可记「已核」
    if channel == "user_export" and has_official_site(source):
        return True
    return False


def claims_official_verified(raw) -> bool:
    """文字本身是否在声称「已与官方原文核对过」。

    与 normalize_check 分工不同：归一按默认拒绝（拿不准就记未核），这里问的是
    「这句话读起来像不像声称已核」——「基本核实」虽不在词表内，仍算声称，商业库
    来源就该报 R18；「待核」「核对中」「未经核实」不算声称。
    """
    v = str(raw or "").strip()
    if not v:
        return False
    if v in CHECK_VERIFIED_TEXT:
        return True
    if CHECK_NEG_RE.search(v) or CHECK_PENDING_RE.search(v):
        return False
    return "核" in v


def normalize_enum(raw, words, canon: set[str], default: str = "unknown") -> str:
    """JSON 里可能写中文（「已核（与官方原文一致）」），表格里可能写英文，两边都归一。"""
    if raw is None or not str(raw).strip():
        return default
    v = str(raw).strip()
    if v in canon:
        return v
    return pick(words, v, default)


def normalize_entries(entries: list[dict], out_of_vocab: list[str] | None = None) -> list[dict]:
    """统一各来源（JSON / markdown 表格 / 内联）的枚举取值。"""
    for e in entries:
        if e.get("norm_status") not in (None, ""):
            e["norm_status"] = normalize_norm_status(e["norm_status"])
        if e.get("official_check") is not None:
            e["official_check_raw"] = e["official_check"]
            e["official_check"] = normalize_check(e["official_check"], out_of_vocab)
        if e.get("channel") is not None:
            e["channel"] = normalize_enum(e["channel"], CHANNEL_WORDS, CHANNEL_CANON)
        if e.get("read_scope") is not None:
            e["read_scope"] = normalize_enum(e["read_scope"], SCOPE_WORDS, SCOPE_CANON)
        if e.get("effectiveness") is not None:
            e["effectiveness"] = normalize_enum(e["effectiveness"], EFFECT_WORDS, EFFECT_CANON)
    return entries

BOILERPLATE_QUOTES = [
    "本院认为",
    "依照法律规定",
    "本院经审理查明",
    "综上所述",
    "本院予以支持",
    "依法应予支持",
    "事实清楚证据充分",
]

ABSOLUTE_CLAIMS = [
    "无任何风险", "没有任何风险", "无任何债务", "没有任何诉讼", "无任何诉讼",
    "肯定胜诉", "必然胜诉", "保证胜诉", "一定能赢", "百分之百", "保证回款", "保证中标",
]
VAGUE_CITATIONS = [
    "根据相关规定", "根据有关法律规定", "依照有关规定", "相关法律法规规定",
    "司法实践普遍认为", "有判例支持", "某法院认为", "司法实践中一般认为",
]
DEADLINE_WORDS = ["截止", "期限", "届满", "上诉期", "答辩期", "举证期", "时效", "过期", "最后一日", "到期"]
DATE_RE = re.compile(r"\d{4}\s*[-/年]\s*\d{1,2}\s*[-/月]\s*\d{1,2}\s*日?|\d{4}-\d{2}-\d{2}")
CASE_NO_RE = re.compile(r"[（(]\s*(?:19|20)\d{2}\s*[）)][^\s，。；：、（）()]{2,32}?号")
GUIDE_NO_RE = re.compile(r"指导案例\s*\d+\s*号|入库编号\s*[\w\-]{4,}")
REREAD_RE = re.compile(r"已回读[（(](\d{4}-\d{2}-\d{2}|日期待补)[）)]")
TAG_RE = re.compile(r"[\[〔【]\s*([NCM]-\d{1,3})\s*[\]〕】]|(?<![\w\-])([NCM]-\d{1,3})(?![\w\-])")


def find_tags(line: str) -> list[str]:
    """取出引用标签：〔N-01〕与裸写 N-01 两种写法都认。"""
    out = []
    for m in TAG_RE.finditer(line):
        out.append(m.group(1) or m.group(2))
    return out
PLACEHOLDER_RE = re.compile(r"[（(]\s*(?:[XxｘＸ]{2,}|20[XxｘＸ]{2}|\d{2}[XxｘＸ]{2})\s*[）)][^\n]{0,30}?号")
TODO_SECTION_RE = re.compile(r"待取|线索|待补|待核")

# ---------------------------------------------------------------- 交付物表格解析

HEADING_RE = re.compile(r"^(#{1,6})\s*(.+?)\s*$")
RISK_LEVEL_RE = re.compile(r"^\**\s*(高|中|低)")
MUST_FIX_ROW_RE = re.compile(r"^必改\s*\d+")
CONDITIONAL_RE = re.compile(r"条件式\s*[（(]\s*待补材料")
PENDING_MATERIAL_ID_RE = re.compile(r"E-\d{1,3}")
CONDITIONAL_COUNT_RES = [re.compile(r"条件式[^。；\n]{0,16}?(\d+)\s*项")]
DETERMINATE_COUNT_RES = [re.compile(r"文本内(?:可)?确定(?:缺陷)?[^。；\n]{0,10}?(\d+)\s*项")]


def parse_tables(lines: list[str]) -> list[dict]:
    """切出 markdown 表格，并记住表格上方最近的标题。

    区分「风险表」「必改表」「底稿表」只能看表头与小节标题，不能看出现顺序：
    同一份报告里表格顺序会变，靠位置判断必然错。
    """
    tables: list[dict] = []
    heading = ""
    i, n = 0, len(lines)
    while i < n:
        stripped = lines[i].strip()
        m = HEADING_RE.match(stripped)
        if m:
            heading = m.group(2)
            i += 1
            continue
        if not stripped.startswith("|"):
            i += 1
            continue
        block: list[tuple[int, list[str]]] = []
        while i < n and lines[i].strip().startswith("|"):
            cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
            block.append((i + 1, cells))
            i += 1
        header = block[0][1]
        rows = [
            (ln, cells)
            for ln, cells in block[1:]
            if not all(set(c) <= set("-: ") for c in cells)
        ]
        tables.append({"heading": heading, "header": header, "rows": rows})
    return tables


def cell_at(cells: list[str], idx: int | None) -> str:
    if idx is None or idx < 0 or idx >= len(cells):
        return ""
    return cells[idx]


# 首页计数声明：写成散文，不写成表格；数字必须能和表行数对上
TOTAL_RES = [
    re.compile(r"(?:共|合计|总计)\s*(\d+)\s*项(?:问题|风险|缺陷)"),
    re.compile(r"(\d+)\s*项(?:问题|风险点|缺陷)"),
]
MUST_RES = [
    re.compile(r"必改\s*(\d+)\s*项"),
    re.compile(r"(\d+)\s*项必改"),
]
LEVEL_RES = [
    re.compile(r"(\d+)\s*项\s*(?:属|为|系)?\s*(高|中|低)风险"),
    re.compile(r"(高|中|低)风险\s*(\d+)\s*项"),
]


def first_int(patterns, text: str, group: int = 1) -> int | None:
    for pat in patterns:
        m = pat.search(text)
        if m:
            return int(m.group(group))
    return None


def homepage_text(lines: list[str], limit: int = 60) -> str:
    """首页＝文首若干行里的散文；表格行是数据，不参与数字声明。"""
    return "\n".join(l for l in lines[:limit] if not l.strip().startswith("|"))


def check_review_counts(rep: "Report", lines: list[str], tables: list[dict], mode: str) -> None:
    """R19：合同审查类交付的首页数字必须由风险表与必改表计数得出。

    只对含「等级」列的风险表生效；解析不到首页数字时只提示，不猜。
    """
    risk_tables = [t for t in tables if any("等级" in h for h in t["header"])]
    if not risk_tables:
        return

    total_rows = 0
    level_counts = {"高": 0, "中": 0, "低": 0}
    unparsed: list[int] = []
    for t in risk_tables:
        lvl_at = next((i for i, h in enumerate(t["header"]) if "等级" in h), None)
        total_rows += len(t["rows"])
        for ln, cells in t["rows"]:
            m = RISK_LEVEL_RE.match(cell_at(cells, lvl_at))
            if m:
                level_counts[m.group(1)] += 1
            else:
                unparsed.append(ln)
    if unparsed:
        shown = "、".join(str(x) for x in unparsed[:6])
        rep.warn("R19", f"第 {shown} 行的风险等级无法解析（单元格应以 高／中／低 开头），未计入分级统计")

    must_tables = [
        t
        for t in tables
        if "必改项" in t["heading"]
        or (t["rows"] and MUST_FIX_ROW_RE.match(cell_at(t["rows"][0][1], 0)))
    ]
    must_rows = sum(
        1 for t in must_tables for _, cells in t["rows"] if MUST_FIX_ROW_RE.match(cell_at(cells, 0))
    )

    # 条件式（待补材料）：风险成立与否取决于未到手材料，必须链到 E- 编号
    conditional: list[int] = []
    for t in risk_tables:
        for ln, cells in t["rows"]:
            joined = " ".join(cells)
            if not CONDITIONAL_RE.search(joined):
                continue
            conditional.append(ln)
            if not PENDING_MATERIAL_ID_RE.search(joined):
                rep.warn(
                    "R19",
                    f"第 {ln} 行标了「条件式（待补材料）」但没有链到待补材料编号（E-xx）；"
                    "补上 E- 编号，否则材料缺口无从追踪",
                )

    head = homepage_text(lines)
    total = first_int(TOTAL_RES, head)
    must = first_int(MUST_RES, head)
    cond_declared = first_int(CONDITIONAL_COUNT_RES, head)
    determinate_declared = first_int(DETERMINATE_COUNT_RES, head)
    levels: dict[str, int] = {}
    for m in LEVEL_RES[0].finditer(head):  # 「5 项属高风险」
        levels.setdefault(m.group(2), int(m.group(1)))
    for m in LEVEL_RES[1].finditer(head):  # 「高风险 5 项」
        levels.setdefault(m.group(1), int(m.group(2)))
    if not total and not must and not levels and cond_declared is None and determinate_declared is None:
        rep.warn(
            "R19",
            "有风险表，但首页没解析到问题总数／必改数／分级数，无法核对（建议写成「共 N 项问题，其中高风险 a 项……必改 b 项」）",
        )
        return

    def bad(msg: str) -> None:
        if mode == "self":
            rep.error("R19", msg)
        else:
            rep.warn("R19", msg)

    if total is not None and total != total_rows:
        bad(f"首页声明共 {total} 项问题，风险表实有 {total_rows} 行；首页数字应由表计数得出，不得手填")
    for lv, num in sorted(levels.items()):
        if num != level_counts[lv]:
            bad(f"首页声明{lv}风险 {num} 项，风险表实有 {level_counts[lv]} 行；首页数字应由表计数得出")
    cond_rows = len(conditional)
    if determinate_declared is not None:
        actual = total_rows - cond_rows
        if determinate_declared != actual:
            bad(
                f"首页声明文本内可确定的缺陷 {determinate_declared} 项，风险表实有 {actual} 行；"
                "条件式风险已单列，不得与确定缺陷混计"
            )
    if cond_declared is not None and cond_declared != cond_rows:
        bad(f"首页声明条件式（待补材料）{cond_declared} 项，风险表实有 {cond_rows} 行")
    if (
        cond_declared is not None
        and determinate_declared is not None
        and total is not None
        and total != cond_declared + determinate_declared
    ):
        bad(
            f"首页总数为 {total}，但「确定 {determinate_declared}＋条件式 {cond_declared}」不等于总数；两处须对得上"
        )
    if must is not None:
        if not must_tables:
            rep.warn(
                "R19",
                f"首页声明必改 {must} 项，但未找到必改清单（小节标题含「必改项」，或首列写「必改 N」），无法核对",
            )
        elif must != must_rows:
            bad(f"首页声明必改 {must} 项，必改清单实有 {must_rows} 行；首页数字应由表计数得出")



def norm(text: str) -> str:
    """案号比较用的归一化：去空白、全角括号转半角、只留字母数字与汉字。"""
    text = text.replace("（", "(").replace("）", ")")
    return "".join(ch for ch in text if ch.isalnum())


def norm_quote(text: str) -> str:
    """摘录比较用的归一化：去空白与标点，只留汉字数字字母。"""
    return "".join(ch for ch in text if ch.isalnum())


def pick(words, cell: str, default: str) -> str:
    for word, value in words:
        if word in cell:
            return value
    return default


# ---------------------------------------------------------------- 底稿读取


def load_ledger_json(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("citations", [])
    return [dict(item) for item in data]


def load_ledger_md(path: Path) -> list[dict]:
    """从 markdown 表格读底稿：按表头关键词映射列，容忍列顺序变化。"""
    lines = path.read_text(encoding="utf-8").splitlines()
    entries: list[dict] = []
    header: list[str] | None = None
    for line in lines + [""]:
        stripped = line.strip()
        if not stripped.startswith("|"):
            header = None
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if header is None:
            header = cells
            continue
        if all(set(c) <= set("-: ") for c in cells):
            continue
        row = dict(zip(header, cells))
        ident = next((v for k, v in row.items() if "编号" in k and v), None)
        if not ident:
            continue
        joined = " ".join(row.keys())
        id_key = next((k for k in row if "编号" in k), "")

        def get(*keys, skip_id: bool = False) -> str:
            for k, v in row.items():
                if skip_id and k == id_key:
                    continue
                if any(key in k for key in keys) and v:
                    return v
            return ""

        entries.append(
            {
                "id": ident,
                "type": get("类型", "类别"),
                "number": get("案号", "文号", skip_id=True) or get("编号", skip_id=True),
                "name": get("名称", "案名", "全称"),
                "court": get("法院", "机关"),
                "date": get("裁判日期", "日期", "施行"),
                "channel": pick([("官方", "official"), ("商业", "commercial"), ("导出", "user_export"), ("口述", "oral")], joined + " " + get("来源渠道", "来源"), "unknown"),
                "location": get("定位", "页码", "出处", "页段"),
                "read_scope": pick(SCOPE_WORDS, get("读取范围", "范围"), "unknown"),
                "quote": get("摘录", "原文"),
                "reread": get("回读"),
                "official_check": pick(CHECK_WORDS, get("官方复核", "复核"), "unknown"),
                "effectiveness": pick(EFFECT_WORDS, get("生效", "后续"), "unknown"),
                "norm_status": normalize_norm_status(get("规范效力")),
                "apply_time": get("适用时点"),
            }
        )
    return entries



INLINE_ID_RE = re.compile(r"([NCSM])\s*-\s*(\d{1,3})")
INLINE_ID_CELL_RE = re.compile(r"^[〔\[（(]?\s*([NCSM])\s*-\s*(\d{1,3})\s*[〕\]）)]?")
LEDGER_HEADING_RE = re.compile(r"引用底稿|底稿表|引用与底稿")


def is_ledger_table(t: dict) -> bool:
    """没有「引用底稿」小节时的兜底：表头带摘录／回读／编号，且首列是编号。"""
    header = " ".join(t["header"])
    if not re.search(r"摘录|回读|底稿", header):
        return False
    return any(cells and INLINE_ID_CELL_RE.match(cell_at(cells, 0)) for _, cells in t["rows"])


def load_ledger_inline(path: Path) -> list[dict]:
    """从交付物自身的底稿表读条目。

    只认「引用底稿」类小节的表，且编号必须在**首列**：正文与风险表里的
    〔N-xx〕是引用，不是条目——把它们也当条目会把条数算多、同一编号重复计。
    没写小节标题的老稿子退化为「表头像底稿表、首列是编号」，仍然只读首列。
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    tables = parse_tables(lines)
    picked = [t for t in tables if LEDGER_HEADING_RE.search(t["heading"])]
    if not picked:
        picked = [t for t in tables if is_ledger_table(t)]

    entries: list[dict] = []
    seen: set[str] = set()
    for t in picked:
        header = t["header"]
        quote_at = next((i for i, h in enumerate(header) if "摘录" in h or "原文" in h), None)
        scope_at = next((i for i, h in enumerate(header) if "读取范围" in h), None)
        reread_at = next((i for i, h in enumerate(header) if "回读" in h), None)
        for _, cells in t["rows"]:
            first = cell_at(cells, 0).strip()
            m = INLINE_ID_CELL_RE.match(first)
            if not m:
                continue
            ident = f"{m.group(1)}-{int(m.group(2)):02d}"
            if ident in seen:  # 同一编号多行只算一条
                continue
            seen.add(ident)
            rest = cells[1:]
            label = first[len(m.group(0)):].strip() or cell_at(cells, 1)
            num = ""
            mg = GUIDE_NO_RE.search(label)
            if mg:
                num = mg.group(0)
            else:
                mc = CASE_NO_RE.search(label)
                if mc:
                    num = mc.group(0)
            quote = cell_at(cells, quote_at) if quote_at is not None else ""
            if not quote:
                quote = next(
                    (
                        c
                        for c in rest
                        if len(c) >= 8
                        and not re.match(r"^(摘录来自|未回读|已回读|待取|待补|已核|未核|不适用)", c)
                    ),
                    "",
                )
            if scope_at is not None:
                read_scope = pick(SCOPE_WORDS, cell_at(cells, scope_at), "unknown")
            else:
                read_scope = "excerpt" if "摘录来自" in " ".join(cells) else "unknown"
            entries.append(
                {
                    "id": ident,
                    "type": "",
                    "number": num,
                    "name": label,
                    "court": "",
                    "date": "",
                    "channel": "unknown",
                    "location": "",
                    "read_scope": read_scope,
                    "quote": quote,
                    "reread": cell_at(cells, reread_at) if reread_at is not None else "",
                    "official_check": "unknown",
                    "effectiveness": "unknown",
                    "inline": True,
                }
            )
    return entries

def load_ledger(path: Path) -> list[dict]:
    if path.suffix.lower() == ".json":
        return load_ledger_json(path)
    return load_ledger_md(path)


# ---------------------------------------------------------------- 校验


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, rule: str, msg: str) -> None:
        entry = f"[{rule}] {msg}"
        if entry not in self.errors:
            self.errors.append(entry)

    def warn(self, rule: str, msg: str) -> None:
        entry = f"[{rule}] {msg}"
        if entry not in self.warnings:
            self.warnings.append(entry)


CLAUSE_REF_RE = re.compile(r"第\s*(\d+(?:\.\d+)*)\s*条")
DOTTED_NO_RE = re.compile(r"(?<![\d.])(\d+(?:\.\d+)+)(?![\d.])")
DEFINED_NO_RE = re.compile(r"(?:^|<br\s*/?>)\s*(\d+(?:\.\d+)+)[\u3000\s]")


def numbers_in(text: str) -> set[str]:
    """取出文本里的条款号：第 x.y 条 与裸写的 x.y 都算。"""
    if not text:
        return set()
    return {m.group(1) for m in CLAUSE_REF_RE.finditer(text)} | {
        m.group(1) for m in DOTTED_NO_RE.finditer(text)
    }


def inside_book_title(text: str, pos: int) -> bool:
    """条号是否落在《…》里面：那是在引法条，不是引合同条款。"""
    return text.rfind("《", 0, pos) > text.rfind("》", 0, pos)


# R21 用：这些词出现即在作法律结论，必须能指回底稿
CONCLUSION_WORDS = ["不发生效力", "不生效", "可撤销", "可调减", "无效"]
NO_CONCLUSION_MARKERS = ["法律判断待核", "待核（未登记依据）", "未登记依据", "待取正文", "待补材料", "本项待核"]
SENTENCE_SPLIT = re.compile(r"[。；]")
QUOTED_RE = re.compile(r"「[^」]*」|『[^』]*』|“[^”]*”|\"[^\"]*\"|'[^']*'")


def check_clause_refs(
    rep: "Report", tables: list[dict], contract_text: str, strict: bool
) -> None:
    """R20：替换条款里的「第 x.y 条」必须能在原合同或映射表里找到。

    只看阿拉伯数字条号：法条用汉字（第五百六十五条），不会落进来；
    紧跟《…》之后的条号跳过，避免把法条误当合同条款。
    """
    risk_tables = [t for t in tables if any("等级" in h for h in t["header"])]
    if not risk_tables:
        return

    known: set[str] = set()
    for t in risk_tables:
        pos_at = next((i for i, h in enumerate(t["header"]) if "位置" in h), None)
        for _, cells in t["rows"]:
            known |= numbers_in(cell_at(cells, pos_at))
    for t in tables:
        o = next((i for i, h in enumerate(t["header"]) if "原编号" in h), None)
        n = next((i for i, h in enumerate(t["header"]) if "新编号" in h), None)
        if o is None or n is None:
            continue
        for _, cells in t["rows"]:
            known |= numbers_in(cell_at(cells, o)) | numbers_in(cell_at(cells, n))
    if contract_text:
        known |= numbers_in(contract_text)

    for t in risk_tables:
        rep_at = next(
            (i for i, h in enumerate(t["header"]) if "可替换" in h or "替换条款" in h), None
        )
        if rep_at is None:
            continue
        for ln, cells in t["rows"]:
            cell = cell_at(cells, rep_at)
            if not cell:
                continue
            defined = {m.group(1) for m in DEFINED_NO_RE.finditer(cell)}
            for m in CLAUSE_REF_RE.finditer(cell):
                if inside_book_title(cell, m.start()):
                    continue
                num = m.group(1)
                if num in known or num in defined:
                    continue
                msg = (
                    f"第 {ln} 行替换条款引用了原合同与映射表中都不存在的编号「第 {num} 条」；"
                    "补「原编号／新编号／说明」映射表，或改为整条替换"
                )
                if strict:
                    rep.error("R20", msg)
                else:
                    rep.warn("R20", msg)


def check_conclusion_sources(rep: "Report", tables: list[dict]) -> None:
    """R21：风险表里的法律结论必须挂 N-／C- 编号，否则提示。

    启发式，只警告：按分句判断（。；切分），本句或前一句有引用即算挂上；
    「」与引号内是引来的原文，不当作本报告的主张。宁可多提示，不因为
    拿不准就放过——但绝不阻断交付。
    """
    risk_tables = [t for t in tables if any("等级" in h for h in t["header"])]
    if not risk_tables:
        return
    for t in risk_tables:
        for ln, cells in t["rows"]:
            row_text = "。".join(c for c in cells if c).replace("<br>", "。").replace("<br/>", "。")
            segs = [QUOTED_RE.sub("", s) for s in SENTENCE_SPLIT.split(row_text)]
            for i, seg in enumerate(segs):
                word = next((w for w in CONCLUSION_WORDS if w in seg), None)
                if not word:
                    continue
                if any(k in seg for k in NO_CONCLUSION_MARKERS):
                    continue
                window = segs[i - 1] if i else ""
                if find_tags(seg) or find_tags(window):
                    continue
                rep.warn(
                    "R21",
                    f"第 {ln} 行出现法律结论「{word}」但没有 N-／C- 编号："
                    f"{seg.strip()[:40]}；补底稿编号，或改写为「法律判断待核（未登记依据）」",
                )
                break


def lint(body_path: Path, ledger_path: Path | None, mode: str, strict: bool,
         contract_path: Path | None = None) -> Report:
    rep = Report()
    text = body_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    doc_norm = norm_quote(text)
    tables = parse_tables(lines)
    contract_text = contract_path.read_text(encoding="utf-8") if contract_path else ""

    ledger = load_ledger(ledger_path) if ledger_path else []
    if not ledger:
        ledger = load_ledger_inline(body_path)
        if ledger:
            rep.warn("R0", f"未指定 --ledger，已从文书内表格读到底稿 {len(ledger)} 条（字段不全，只做编号与摘录检查）")
    by_id = {e["id"]: e for e in ledger if e.get("id")}
    known_numbers = {norm(e["number"]) for e in ledger if e.get("number")}
    out_of_vocab: list[str] = []
    ledger = normalize_entries(ledger, out_of_vocab)
    used_ids: dict[str, list[int]] = {}

    # R2 底稿字段完整性
    for entry in ledger:
        if entry.get("inline"):
            continue
        required = list(REQUIRED_FIELDS)
        if (entry.get("channel") or "unknown") != "official":
            # 非官方渠道本就不该有官方复核结论，留空合法
            required = [f for f in required if f != "official_check"]
        missing = [f for f in required if not str(entry.get(f, "")).strip() or entry.get(f) in (None, "unknown")]
        if missing:
            rep.error("R2", f"底稿 {entry.get('id', '?')} 缺字段：{', '.join(missing)}")

    heading = ""
    for idx, line in enumerate(lines, start=1):
        if line.lstrip().startswith("#"):
            heading = line.strip()
        in_todo = bool(TODO_SECTION_RE.search(heading))

        # R1 正文案号必须登记（待取正文小节允许只作线索）
        placeholder = PLACEHOLDER_RE.search(line)
        if placeholder:
            rep.error("R1", f"第 {idx} 行出现占位案号，不得出现在交付物：{placeholder.group(0)}")
        for match in CASE_NO_RE.finditer(line):
            token = match.group(0)
            if norm(token) in known_numbers:
                continue
            if in_todo:
                rep.warn("R1", f"第 {idx} 行待取正文里的案号未登记（建议也进底稿并标「标题」）：{token}")
            else:
                rep.error("R1", f"第 {idx} 行案号未在任何底稿条目中登记：{token}")
        for match in GUIDE_NO_RE.finditer(line):
            if norm(match.group(0)) not in {norm(e.get("number", "")) for e in ledger}:
                rep.error("R1", f"第 {idx} 行案例编号未登记：{match.group(0)}")

        # 引用标签
        for tag in find_tags(line):
            used_ids.setdefault(tag, []).append(idx)
            entry = by_id.get(tag)
            if entry is None:
                rep.error("R8", f"第 {idx} 行引用了不存在的底稿条目 [{tag}]")
                continue

            # R3 摘要级材料不得支撑结论
            if entry.get("read_scope") in WEAK_SCOPES and not in_todo:
                rep.error("R3", f"第 {idx} 行用「{entry.get('read_scope')}」级材料 [{tag}] 支撑正文（所在小节：{heading or '开头'}）")

            # R4 效力状态
            if entry.get("effectiveness") not in ("effective",) and re.search(r"生效判决|生效裁判|终审判决|已生效", line):
                rep.warn("R4", f"第 {idx} 行宣称生效，但 [{tag}] 的生效状态为 {entry.get('effectiveness')}")

            # R11 支撑结论的条目必须带摘录
            quote = (entry.get("quote") or "").strip()
            if not in_todo and entry.get("read_scope") in QUOTE_SCOPES and not quote:
                rep.error("R11", f"第 {idx} 行引用的 [{tag}] 缺少原文摘录（摘录必填，概述不算）")

            if quote and not entry.get("inline"):
                q = norm_quote(quote)
                # R13 摘录过短或套话
                if len(q) < 8:
                    rep.error("R13", f"[{tag}] 的摘录过短（{len(q)} 字），不能证明读过原文")
                elif any(b in quote for b in BOILERPLATE_QUOTES) and len(q) < 16:
                    rep.error("R13", f"[{tag}] 的摘录是套话（{quote}），任何判决都有，无法证伪")

                # R12 摘录应出现在引用处附近
                window = norm_quote("\n".join(lines[max(0, idx - 3): idx + 2]))
                if q not in window:
                    if q in doc_norm:
                        rep.warn("R12", f"第 {idx} 行引用的摘录不在该处附近，请确认摘录与结论是同一段")
                    else:
                        rep.error("R12", f"第 {idx} 行引用的摘录在全文找不到：{quote[:24]}…")

            # R15 用于结论的条目应已回读
            if entry.get("inline"):
                pass
            elif entry.get("read_scope") in QUOTE_SCOPES and not in_todo:
                reread = str(entry.get("reread") or "")
                if not reread.startswith("已回读"):
                    msg = f"第 {idx} 行引用的 [{tag}] 未回读原文（交付前应回读并记录日期）"
                    if strict and mode != "offline":
                        rep.error("R15", msg)
                    else:
                        rep.warn("R15", msg)
                elif (m_date := REREAD_RE.search(reread)) and _is_future(m_date.group(1)):
                    rep.error(
                        "R15",
                        f"[{tag}] 的回读日期 {m_date.group(1)} 晚于今天（{date.today().isoformat()}）：回读只能记已发生的日期",
                    )
                elif not REREAD_RE.search(reread):
                    rep.warn(
                        "R15",
                        f"[{tag}] 的回读记录缺日期：写「已回读（YYYY-MM-DD）」，取不到日期写「已回读（日期待补）」",
                    )

        # R5 期限日期必须带状态标签
        if any(w in line for w in DEADLINE_WORDS) and DATE_RE.search(line):
            if not re.search(r"已核|〔假设|\[假设|待核|未核", line):
                rep.error("R5", f"第 {idx} 行给出期限日期但没有状态标签（已核／〔假设〕／待核）：{line.strip()[:60]}")

        # R6 绝对化措辞
        for phrase in ABSOLUTE_CLAIMS:
            if phrase in line:
                rep.error("R6", f"第 {idx} 行出现绝对化结论「{phrase}」")

        # R7 无据引用
        for phrase in VAGUE_CITATIONS:
            if phrase in line:
                rep.error("R7", f"第 {idx} 行出现无具体依据的引用「{phrase}」")

    # R19 首页计数必须与风险表、必改清单对得上
    check_review_counts(rep, lines, tables, mode)

    # R20 替换条款不得引用原合同与映射表中都不存在的编号
    check_clause_refs(rep, tables, contract_text, strict)

    # R21 风险表里的法律结论必须挂底稿编号（启发式，只警告）
    check_conclusion_sources(rep, tables)

    # R9 复核表述与模式
    claims_review = re.search(r"已复核|经复核|独立核验|已通过独立审查", text)
    if claims_review and mode != "review":
        rep.error("R9", f"当前为自查模式，但正文出现「{claims_review.group(0)}」；改为「已完成自查」或改用独立复核")
    if mode == "self" and "〔自查〕" not in text and claims_review:
        rep.warn("R9", "自查模式建议在标题后标注〔自查〕")

    # R10 底稿条目未被引用
    for entry in ledger:
        if entry.get("id") and entry["id"] not in used_ids:
            rep.warn("R10", f"底稿条目 {entry['id']} 未在正文引用（可能多余）")

    # R16 规范类条目缺效力与适用时点；效力未确认却用于结论
    for entry in ledger:
        eid = entry.get("id") or ""
        if entry.get("inline") or not eid.startswith("N"):
            continue
        missing = []
        if entry.get("norm_status") in (None, "", "unknown"):
            missing.append("规范效力")
        if not str(entry.get("apply_time") or "").strip():
            missing.append("适用时点")
        if missing:
            rep.warn("R16", f"规范类条目 {eid} 缺字段：{'、'.join(missing)}（旧底稿可先补后交）")
        # 严格模式：用于结论却连「规范效力」都没登记，按错误处理（普通模式只警告）
        if strict and "规范效力" in missing and eid in used_ids:
            rep.error(
                "R16",
                f"严格模式：规范类条目 {eid} 未登记「规范效力」却用于正文结论；补登记或降为待取正文",
            )
        # 与上一条独立判断：字段缺失不得屏蔽「未确认却用于结论」
        if entry.get("norm_status") == NORM_UNCONFIRMED and eid in used_ids:
            rep.error("R16", f"规范类条目 {eid} 的规范效力为「未确认」，却用于正文结论；先核效力或降为待取正文")

    # R16 内联底稿：有 N- 编号但没登记规范效力 → 一条汇总，不逐条刷屏
    inline_missing = [
        e.get("id") or ""
        for e in ledger
        if e.get("inline")
        and (e.get("id") or "").startswith("N")
        and e.get("norm_status") in (None, "", "unknown")
    ]
    if inline_missing:
        shown = "、".join(inline_missing[:10])
        more = "…" if len(inline_missing) > 10 else ""
        msg = (
            f"内联底稿有 {len(inline_missing)} 条规范类条目未登记「规范效力」：{shown}{more}；"
            "内联表加一列「规范效力」即可，不必逐条补"
        )
        if strict:
            rep.warn("R16", msg)
        else:
            rep.warn("R0", msg)

    # R18 渠道与出处／官方复核不符
    for entry in ledger:
        eid = entry.get("id") or ""
        if not eid:
            continue
        channel = entry.get("channel") or "unknown"
        source = " ".join(str(entry.get(k) or "") for k in ("location", "court", "name", "source", "url"))
        if channel == "official":
            verdict = official_domain_ok(source)
            if verdict is None:
                rep.error(
                    "R18",
                    f"条目 {eid} 渠道写「官方」，但出处只有"
                    f"「{entry.get('location') or ''}」，没有任何官方站点链接；"
                    "补官方链接，或把渠道改成「商业」「导出」「口述」",
                )
                continue
            if not verdict:
                bad = [h for h, pth in sites_in(source) if not site_ok(h, pth)]
                rep.error(
                    "R18",
                    f"条目 {eid} 渠道写「官方」，但出处主机名 {'、'.join(dict.fromkeys(bad))} 不在官方白名单内"
                    f"（{'、'.join(d for d, _ in OFFICIAL_SITES)}，其中 www.gov.cn 限 /zhengce/xxgk/gjgzk/）；"
                    "用户导出件请把渠道写成「导出」并在出处写明官方链接",
                )
                continue
            if not any(pth and pth not in ("", "/") for _, pth in sites_in(source)):
                rep.error(
                    "R2",
                    f"条目 {eid} 出处只有官方站点的主机名或根路径"
                    f"（{entry.get('location') or ''}），没有具体原文路径；"
                    "引用须写能定位到原文的完整链接",
                )
                continue
        if channel != "official" and not check_allowed_for_channel(
            entry.get("official_check_raw"), channel, source
        ):
            rep.error(
                "R18",
                f"条目 {eid} 渠道非官方（{entry.get('channel') or '未填'}），官方复核却写成"
                f"「{entry.get('official_check_raw') or entry.get('official_check')}」；"
                "非官方渠道只能记「未核（仅商业库或转载）」或不适用或留空"
                "（官方站点下载的导出件须在出处写明官方链接）",
            )

    if out_of_vocab:
        distinct = list(dict.fromkeys(out_of_vocab))
        rep.warn(
            "R0",
            f"官方复核写法不在词表内，已按未核处理：{'、'.join(distinct[:6])}"
            f"{' 等' if len(distinct) > 6 else ''}",
        )

    # R0 官方复核未核条数（提示级：警告，不阻断交付）
    used_unverified = [
        e["id"]
        for e in ledger
        if e.get("id")
        and e["id"] in used_ids
        and (
            e.get("official_check") == "unverified"
            # 非官方渠道且官方复核留空：没有官方原文可核，同样计入
            or ((e.get("channel") or "unknown") != "official" and e.get("official_check") in (None, "", "unknown"))
        )
    ]
    if used_unverified:
        rep.warn(
            "R0",
            f"官方复核未核 {len(used_unverified)} 条（{', '.join(used_unverified[:6])}"
            f"{' 等' if len(used_unverified) > 6 else ''}）：回读已通过，但官方原文未亲核；"
            "正式诉讼材料请单列「提交前须核」清单",
        )

    # R14 同一摘录被不同条目复用
    seen: dict[str, str] = {}
    for entry in ledger:
        q = norm_quote(entry.get("quote") or "")
        if len(q) < 8:
            continue
        if q in seen and seen[q] != entry["id"]:
            msg = f"摘录被 {seen[q]} 与 {entry['id']} 同时使用，可能不是各自原文"
            if strict:
                rep.error("R14", f"严格模式：{msg}")
            else:
                rep.warn("R14", msg)
        else:
            seen[q] = entry["id"]

    # R17 离线草稿形态：必须是草稿，首页要声明，文末要待回读清单
    if mode == "offline":
        if "〔草稿〕" not in text:
            rep.error("R17", "离线模式要求标题带〔草稿〕：离线稿是草稿，不可作为定稿")
        if "未经联网回读" not in text:
            rep.error("R17", "离线模式要求首页写明「本稿未经联网回读……回读率 0%」")
        if not re.search(r"待回读清单|待回读条目", text):
            rep.error("R17", "离线模式要求文末给「待回读清单」（条目编号＋建议核对的官方来源）")
        for word in ("可交付", "可直接使用", "已核实", "已核（与官方原文一致）"):
            if affirms_claim(text, word):
                rep.error("R17", f"离线稿不得出现「{word}」：离线只能出草稿")

    return rep


def render(rep: Report, body: Path, mode: str = "self") -> str:
    out = [f"引用校验：{body}"]
    if rep.errors:
        out.append(f"\n错误 {len(rep.errors)} 条：")
        out += [f"  - {e}" for e in rep.errors]
    if rep.warnings:
        out.append(f"\n警告 {len(rep.warnings)} 条：")
        out += [f"  - {w}" for w in rep.warnings]
    if mode == "offline":
        if rep.errors:
            out.append("\n未通过：离线稿本身不合规，先补〔草稿〕标注、首页声明与待回读清单。")
        else:
            out.append("\n通过（离线草稿）：只能作为草稿提交，回读后转定稿，不得标「可交付」。")
        return "\n".join(out)
    if not rep.errors and not rep.warnings:
        out.append("\n通过：形式一致性检查无问题。注意——通过≠已核实，真伪仍需回读与律师复核。")
    elif not rep.errors:
        out.append("\n通过（有警告）：可以交付，但建议处理警告项。")
    else:
        out.append("\n未通过：修正后再标注可交付。")
    return "\n".join(out)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="法律交付物引用校验器")
    ap.add_argument("body", type=Path, help="待校验的交付物（markdown）")
    ap.add_argument("--ledger", type=Path, help="引用底稿：citations.json 或 markdown 表格")
    ap.add_argument("--mode", choices=["self", "review", "offline"], default="self", help="自查／独立复核／离线草稿模式")
    ap.add_argument("--strict", action="store_true", help="未回读按错误处理")
    ap.add_argument("--contract", type=Path, help="原合同文件（文本），用于核对替换条款引用的条款号")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = ap.parse_args(argv)

    if not args.body.exists():
        print(f"找不到文件：{args.body}", file=sys.stderr)
        return 2
    if args.ledger and not args.ledger.exists():
        print(f"找不到底稿：{args.ledger}", file=sys.stderr)
        return 2
    if args.contract and not args.contract.exists():
        print(f"找不到原合同：{args.contract}", file=sys.stderr)
        return 2
    if not args.ledger:
        print("提示：未提供 --ledger，只做措辞与标签检查（无法校验案号来源）。", file=sys.stderr)

    rep = lint(args.body, args.ledger, args.mode, args.strict, args.contract)
    if args.json:
        print(json.dumps({"errors": rep.errors, "warnings": rep.warnings}, ensure_ascii=False, indent=2))
    else:
        print(render(rep, args.body, args.mode))
    return 1 if rep.errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
