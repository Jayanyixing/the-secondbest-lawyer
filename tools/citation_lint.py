#!/usr/bin/env python3
"""交付前引用校验器。

把「不许编造」从口号变成可执行检查：正文里出现的每个案号都必须能在引用底稿中
找到；底稿缺来源/定位/读取范围/复核状态就报错；摘要级材料不得支撑结论；期限
日期必须带状态标签；绝对化措辞直接失败。

用法：
    python3 tools/citation_lint.py 交付物.md --ledger citations.json
    python3 tools/citation_lint.py 交付物.md --ledger 底稿.md      # 也支持 markdown 表格底稿
    python3 tools/citation_lint.py 交付物.md --mode review          # 独立复核模式

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
SCOPE_WORDS = [("全文", "full"), ("节选", "excerpt"), ("摘要", "abstract"), ("标题", "title"), ("未读", "none")]
CHECK_WORDS = [("已核", "verified"), ("未核", "unverified"), ("不适用", "na")]
EFFECT_WORDS = [("已确认生效", "effective"), ("未确认", "unconfirmed"), ("存在后续", "subsequent")]

REQUIRED_FIELDS = ["id", "type", "number", "location", "read_scope", "official_check", "channel"]

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
TAG_RE = re.compile(r"[\[〔【]\s*([NCM]-\d{1,3})\s*[\]〕】]")
PLACEHOLDER_RE = re.compile(r"[（(]\s*(?:[XxｘＸ]{2,}|20[XxｘＸ]{2}|\d{2}[XxｘＸ]{2})\s*[）)][^\n]{0,30}?号")


def norm(text: str) -> str:
    """案号比较用的归一化：去空白、全角括号转半角、只留字母数字与汉字。"""
    text = text.replace("（", "(").replace("）", ")")
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
                "official_check": pick(CHECK_WORDS, get("官方复核", "复核"), "unknown"),
                "effectiveness": pick(EFFECT_WORDS, get("生效", "后续"), "unknown"),
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


def lint(body_path: Path, ledger_path: Path | None, mode: str) -> Report:
    rep = Report()
    text = body_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    ledger = load_ledger(ledger_path) if ledger_path else []
    by_id = {e["id"]: e for e in ledger if e.get("id")}
    known_numbers = {norm(e["number"]) for e in ledger if e.get("number")}

    # R2 底稿字段完整性
    for entry in ledger:
        missing = [f for f in REQUIRED_FIELDS if not str(entry.get(f, "")).strip() or entry.get(f) in (None, "unknown", "")]
        if missing:
            rep.error("R2", f"底稿 {entry.get('id', '?')} 缺字段：{', '.join(missing)}")

    heading = ""
    for idx, line in enumerate(lines, start=1):
        if line.lstrip().startswith("#"):
            heading = line.strip()

        # R1 正文案号必须登记
        placeholder = PLACEHOLDER_RE.search(line)
        if placeholder:
            rep.error("R1", f"第 {idx} 行出现占位案号，不得出现在交付物：{placeholder.group(0)}")
        for match in CASE_NO_RE.finditer(line):
            token = match.group(0)
            if re.search(r"[Xx]{2,}", token):
                rep.error("R1", f"第 {idx} 行案号含占位符：{token}")
                continue
            if norm(token) not in known_numbers:
                rep.error("R1", f"第 {idx} 行案号未在任何底稿条目中登记：{token}")
        for match in GUIDE_NO_RE.finditer(line):
            if norm(match.group(0)) not in {norm(e.get("number", "")) for e in ledger}:
                rep.error("R1", f"第 {idx} 行案例编号未登记：{match.group(0)}")

        # R8 引用标签必须指向存在的底稿条目
        for tag in TAG_RE.findall(line):
            if tag not in by_id:
                rep.error("R8", f"第 {idx} 行引用了不存在的底稿条目 [{tag}]")
                continue
            entry = by_id[tag]
            # R3 摘要级材料不得支撑结论
            if entry.get("read_scope") in WEAK_SCOPES and not re.search(r"待取|线索|待补", heading):
                rep.error("R3", f"第 {idx} 行用「{entry.get('read_scope')}」级材料 [{tag}] 支撑正文（所在小节：{heading or '开头'}）")
            # R4 效力状态
            if entry.get("effectiveness") not in ("effective",) and re.search(r"生效判决|生效裁判|终审判决|已生效", line):
                rep.warn("R4", f"第 {idx} 行宣称生效，但 [{tag}] 的生效状态为 {entry.get('effectiveness')}")

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
    used = set(TAG_RE.findall(text))
    for entry in ledger:
        if entry.get("id") and entry["id"] not in used:
            rep.warn("R10", f"底稿条目 {entry['id']} 未在正文引用（可能多余）")

    return rep


def render(rep: Report, body: Path) -> str:
    out = [f"引用校验：{body}"]
    if rep.errors:
        out.append(f"\n错误 {len(rep.errors)} 条：")
        out += [f"  - {e}" for e in rep.errors]
    if rep.warnings:
        out.append(f"\n警告 {len(rep.warnings)} 条：")
        out += [f"  - {w}" for w in rep.warnings]
    if not rep.errors and not rep.warnings:
        out.append("\n通过：引用可追溯，未发现编造迹象。")
    elif not rep.errors:
        out.append("\n通过（有警告）：可以交付，但建议处理警告项。")
    else:
        out.append("\n未通过：修正后再标注可交付。")
    return "\n".join(out)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="法律交付物引用校验器")
    ap.add_argument("body", type=Path, help="待校验的交付物（markdown）")
    ap.add_argument("--ledger", type=Path, help="引用底稿：citations.json 或 markdown 表格")
    ap.add_argument("--mode", choices=["self", "review"], default="self", help="自查或独立复核模式")
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

    rep = lint(args.body, args.ledger, args.mode)
    if args.json:
        print(json.dumps({"errors": rep.errors, "warnings": rep.warnings}, ensure_ascii=False, indent=2))
    else:
        print(render(rep, args.body))
    return 1 if rep.errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
