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


NEG_MARKERS = re.compile(r"(不|非|无|未|勿|别|没有|并非|不是|不得|不能|不可|尚未)")


def affirms_claim(text: str, word: str) -> bool:
    """正文是否**肯定地**声称了 word。

    「本稿不是可交付稿」「无一条已核实」这类否定句不算声称——否则离线稿只要
    自我否认就会被打回。判定窗口取 word 前 8 个字，窗口内出现否定词即视为否定。
    """
    for m in re.finditer(re.escape(word), text):
        before = text[max(0, m.start() - 8):m.start()]
        if NEG_MARKERS.search(before):
            continue
        return True
    return False


def normalize_entries(entries: list[dict]) -> list[dict]:
    """统一各来源（JSON / markdown 表格 / 内联）的规范效力取值。"""
    for e in entries:
        if e.get("norm_status") not in (None, ""):
            e["norm_status"] = normalize_norm_status(e["norm_status"])
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


def load_ledger_inline(path: Path) -> list[dict]:
    """从交付物自身的表格里读底稿行（编号列写成 N-01 / 〔N-01〕 即可）。

    用于「底稿直接附在文书末尾、没有单独 ledger 文件」的常规写法：
    只要有 N-/C-/S-/M- 编号，就按行构造条目，缺的字段留空。
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    entries: list[dict] = []
    header: list[str] | None = None
    for line in lines + [""]:
        stripped = line.strip()
        if not stripped.startswith("|"):
            header = None
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if all(set(c) <= set("-: ") for c in cells):
            continue
        ident = None
        id_at = 0
        for i, c in enumerate(cells):
            m = INLINE_ID_RE.search(c.strip())
            if m:
                ident = f"{m.group(1)}-{int(m.group(2)):02d}"
                id_at = i
                break
        if ident is None:
            header = cells if header is None else header
            continue
        rest = [c for i, c in enumerate(cells) if i != id_at]
        quote = ""
        read_scope = "unknown"
        for c in rest:
            if "摘录" in c or "原文" in c:
                pass
            if len(c) >= 8 and not re.match(r"^(摘录来自|未回读|已回读|待取)", c) and not quote:
                quote = c
            if "摘录来自" in c:
                read_scope = "excerpt"
        id_cell = cells[id_at].strip()
        bare = re.fullmatch(r"[〔\[（(]?[NCSM]\s*-\s*\d{1,3}[〕\]）)]?", id_cell)
        label = (rest[0] if rest else "") if bare else id_cell
        num = ""
        mg = GUIDE_NO_RE.search(label)
        if mg:
            num = mg.group(0)
        else:
            mc = CASE_NO_RE.search(label)
            if mc:
                num = mc.group(0)
        entries.append(
            {
                "id": ident,
                "type": "",
                "number": num,
                "name": rest[0] if rest else "",
                "court": "",
                "date": "",
                "channel": "unknown",
                "location": "",
                "read_scope": read_scope,
                "quote": quote,
                "reread": "",
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


def lint(body_path: Path, ledger_path: Path | None, mode: str, strict: bool) -> Report:
    rep = Report()
    text = body_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    doc_norm = norm_quote(text)

    ledger = load_ledger(ledger_path) if ledger_path else []
    if not ledger:
        ledger = load_ledger_inline(body_path)
        if ledger:
            rep.warn("R0", f"未指定 --ledger，已从文书内表格读到底稿 {len(ledger)} 条（字段不全，只做编号与摘录检查）")
    by_id = {e["id"]: e for e in ledger if e.get("id")}
    known_numbers = {norm(e["number"]) for e in ledger if e.get("number")}
    ledger = normalize_entries(ledger)
    used_ids: dict[str, list[int]] = {}

    # R2 底稿字段完整性
    for entry in ledger:
        if entry.get("inline"):
            continue
        missing = [f for f in REQUIRED_FIELDS if not str(entry.get(f, "")).strip() or entry.get(f) in (None, "unknown")]
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
        # 与上一条独立判断：字段缺失不得屏蔽「未确认却用于结论」
        if entry.get("norm_status") == NORM_UNCONFIRMED and eid in used_ids:
            rep.error("R16", f"规范类条目 {eid} 的规范效力为「未确认」，却用于正文结论；先核效力或降为待取正文")

    # R18 来源渠道与官方复核矛盾：商业库/转载件不得记「已核」
    for entry in ledger:
        eid = entry.get("id") or ""
        if not eid:
            continue
        if entry.get("channel") == "commercial" and entry.get("official_check") == "verified":
            rep.error(
                "R18",
                f"条目 {eid} 来源为商业库，却把官方复核写成「已核」；商业库只能记「未核（仅商业库或转载）」",
            )

    # R0 官方复核未核条数（提示级：警告，不阻断交付）
    used_unverified = [
        e["id"]
        for e in ledger
        if e.get("id") and e["id"] in used_ids and e.get("official_check") == "unverified"
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
            rep.warn("R14", f"摘录被 {seen[q]} 与 {entry['id']} 同时使用，可能不是各自原文")
        else:
            seen[q] = entry["id"]

    # 离线模式：必须是草稿，首页要声明，文末要待回读清单
    if mode == "offline":
        if "〔草稿〕" not in text:
            rep.error("R15", "离线模式要求标题带〔草稿〕：离线稿是草稿，不可作为定稿")
        if "未经联网回读" not in text:
            rep.error("R15", "离线模式要求首页写明「本稿未经联网回读……回读率 0%」")
        if not re.search(r"待回读清单|待回读条目", text):
            rep.error("R15", "离线模式要求文末给「待回读清单」（条目编号＋建议核对的官方来源）")
        for word in ("可交付", "可直接使用", "已核实", "已核（与官方原文一致）"):
            if affirms_claim(text, word):
                rep.error("R15", f"离线稿不得出现「{word}」：离线只能出草稿")

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
    ap.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = ap.parse_args(argv)

    if not args.body.exists():
        print(f"找不到文件：{args.body}", file=sys.stderr)
        return 2
    if args.ledger and not args.ledger.exists():
        print(f"找不到底稿：{args.ledger}", file=sys.stderr)
        return 2
    if not args.ledger:
        print("提示：未提供 --ledger，只做措辞与标签检查（无法校验案号来源）。", file=sys.stderr)

    rep = lint(args.body, args.ledger, args.mode, args.strict)
    if args.json:
        print(json.dumps({"errors": rep.errors, "warnings": rep.warnings}, ensure_ascii=False, indent=2))
    else:
        print(render(rep, args.body, args.mode))
    return 1 if rep.errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
