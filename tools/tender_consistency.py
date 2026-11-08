#!/usr/bin/env python3
"""投标文件一致性检查：抓「同一事实两种写法」。

标书最省事的废标来自低级不一致：大写金额与数字对不上、投标总价前后不同、
同一截止时间两处日期不同、暗标 Word 属性里留着作者名。这些都能机器查。

查的是形式矛盾，不是语义正确——金额是否合理、业绩是否真实、人员是否够格，
仍需人做。不要把「检查通过」当成「标书没问题」。

用法：
    python3 tools/tender_consistency.py 标书/            # 目录，递归 md/txt/docx
    python3 tools/tender_consistency.py 商务标.md 报价表.md
    python3 tools/tender_consistency.py 标书/ --anonymous  # 额外查暗标泄露

退出码：0 无疑似问题；1 有错误级问题。无第三方依赖。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path

# ---------------------------------------------------------------- 读文件

TEXT_SUFFIX = {".md", ".txt", ".csv"}
DOCX_SUFFIX = {".docx"}


def docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        try:
            xml = z.read("word/document.xml").decode("utf-8", "ignore")
        except KeyError:
            return ""
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"<w:tab[^>]*/>", "\t", xml)
    xml = re.sub(r"<[^>]+>", "", xml)
    return xml.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")


def docx_meta(path: Path) -> dict:
    with zipfile.ZipFile(path) as z:
        try:
            xml = z.read("docProps/core.xml").decode("utf-8", "ignore")
        except KeyError:
            return {}
    out = {}
    for key in ("creator", "lastModifiedBy", "title", "company"):
        m = re.search(rf"<{key}[^>]*>(.*?)</{key}>", xml, re.S)
        if m and m.group(1).strip():
            out[key] = m.group(1).strip()
    return out


def collect(paths: list[Path]) -> list[tuple[Path, str]]:
    files: list[Path] = []
    for p in paths:
        if p.is_dir():
            files += sorted(
                q for q in p.rglob("*")
                if q.suffix.lower() in TEXT_SUFFIX | DOCX_SUFFIX and q.is_file()
            )
        elif p.suffix.lower() in TEXT_SUFFIX | DOCX_SUFFIX:
            files.append(p)
        else:
            print(f"跳过（非文本）：{p}", file=sys.stderr)
    return [(f, f.read_text("utf-8", "ignore") if f.suffix.lower() in TEXT_SUFFIX else docx_text(f))
            for f in files]

# ---------------------------------------------------------------- 金额

CN_DIGITS = {"零": 0, "〇": 0, "壹": 1, "贰": 2, "叁": 3, "肆": 4, "伍": 5,
             "陆": 6, "柒": 7, "捌": 8, "玖": 9, "一": 1, "二": 2, "三": 3,
             "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "两": 2}
SMALL_UNITS = {"拾": 10, "十": 10, "佰": 100, "百": 100, "仟": 1000, "千": 1000}
CN_CHARS = "".join(CN_DIGITS) + "".join(SMALL_UNITS) + "万亿"
CN_RE = re.compile(rf"[{CN_CHARS}]{{1,20}}元(?:[{''.join(CN_DIGITS)}]角)?(?:[{''.join(CN_DIGITS)}]分)?(?:整)?")
NUM_RE = re.compile(r"(?:人民币|￥|¥|RMB)?\s*([0-9][0-9,，]*(?:\.[0-9]{1,2})?)\s*(万元|万|元)")


def cn_to_yuan(s: str) -> float | None:
    head, sep, tail = s.partition("元")
    if not sep:
        return None
    total = section = num = 0
    for ch in head:
        if ch in CN_DIGITS:
            num = CN_DIGITS[ch]
        elif ch in SMALL_UNITS:
            section += (num or 1) * SMALL_UNITS[ch]
            num = 0
        elif ch == "万":
            total += (section + num) * 10_000
            section = num = 0
        elif ch == "亿":
            total = (total + section + num) * 100_000_000
            section = num = 0
    value = float(total + section + num)
    frac = 0.0
    m = re.match(rf"([{''.join(CN_DIGITS)}])角", tail)
    if m:
        frac += CN_DIGITS[m.group(1)] * 0.1
    m = re.search(rf"([{''.join(CN_DIGITS)}])分", tail)
    if m:
        frac += CN_DIGITS[m.group(1)] * 0.01
    return round(value + frac, 2)


def num_to_yuan(raw: str, unit: str) -> float:
    v = float(raw.replace(",", "").replace("，", ""))
    return round(v * 10_000, 2) if unit in ("万元", "万") else round(v, 2)

# ---------------------------------------------------------------- 标签

PRICE_LABELS = ["投标总价", "投标报价", "总报价", "报价合计", "合同金额", "最高限价",
                "预算金额", "采购预算", "投标保证金", "保证金金额", "小写", "大写"]
DATE_LABELS = ["投标截止时间", "递交截止时间", "截止时间", "开标时间", "提交截止",
               "报价有效期", "投标有效期", "有效期至", "服务期限", "工期", "签署日期"]


def label_near(text: str, pos: int, labels: list[str], window: int = 40) -> str | None:
    lo = max(0, pos - window)
    seg = text[lo:pos]
    best, best_at = None, -1
    for lab in labels:
        at = seg.rfind(lab)
        if at > best_at:
            best, best_at = lab, at
    return best


DATE_RE = re.compile(r"(20\d{2})\s*[年\-/.]\s*(\d{1,2})\s*[月\-/.]\s*(\d{1,2})\s*日?")

# ---------------------------------------------------------------- 检查


class Findings:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def add(self, level: str, code: str, message: str, where: str) -> None:
        self.items.append({"level": level, "code": code, "message": message, "where": where})

    @property
    def errors(self) -> int:
        return sum(1 for i in self.items if i["level"] == "错误")

    @property
    def warns(self) -> int:
        return sum(1 for i in self.items if i["level"] == "提示")


def line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def check_file(path: Path, text: str, f: Findings, price_index: dict) -> None:
    where_prefix = path.name
    # 1) 大写 vs 数字（就近 30 字内配对）
    num_spans = [(m.start(), m.end(), num_to_yuan(m.group(1), m.group(2)))
                 for m in NUM_RE.finditer(text)]
    for m in CN_RE.finditer(text):
        raw = m.group(0)
        value = cn_to_yuan(raw)
        if value is None or value == 0:
            continue
        near = [v for (s, e, v) in num_spans if abs(s - m.start()) <= 30]
        line = line_of(text, m.start())
        if not near:
            f.add("提示", "C1", f"大写金额「{raw}」附近无对应数字金额", f"{where_prefix}:{line}")
            continue
        if all(abs(v - value) > 0.005 for v in near):
            f.add("错误", "C1",
                  f"大写「{raw}」= {value:.2f}，附近数字为 {near[0]:.2f}",
                  f"{where_prefix}:{line}")
    # 2) 同一价格标签多值
    by_label: dict[str, list[tuple[float, int]]] = {}
    for m in NUM_RE.finditer(text):
        lab = label_near(text, m.start(), PRICE_LABELS)
        if not lab:
            continue
        value = num_to_yuan(m.group(1), m.group(2))
        by_label.setdefault(lab, []).append((value, line_of(text, m.start())))
        price_index.setdefault(lab, []).append((value, path.name, line_of(text, m.start())))
    for lab, vals in by_label.items():
        distinct = {v for v, _ in vals}
        if len(distinct) > 1 and lab not in ("大写", "小写"):
            detail = "，".join(f"{v:.2f}（第{l}行）" for v, l in vals[:4])
            f.add("错误", "C2", f"「{lab}」出现不同金额：{detail}", where_prefix)
    # 3) 同一日期标签多值
    dates: dict[str, list[tuple[str, int]]] = {}
    for m in DATE_RE.finditer(text):
        lab = label_near(text, m.start(), DATE_LABELS)
        if not lab:
            continue
        y, mo, d = m.groups()
        dates.setdefault(lab, []).append((f"{int(y)}-{int(mo):02d}-{int(d):02d}",
                                          line_of(text, m.start())))
    for lab, vals in dates.items():
        distinct = {v for v, _ in vals}
        if len(distinct) > 1:
            detail = "，".join(f"{v}（第{l}行）" for v, l in vals[:4])
            f.add("提示", "C3", f"「{lab}」出现不同日期：{detail}", where_prefix)


def check_meta(path: Path, f: Findings, anonymous: bool) -> None:
    meta = docx_meta(path)
    if not meta:
        return
    risky = {k: v for k, v in meta.items() if k in ("creator", "lastModifiedBy", "company")}
    if not risky:
        return
    detail = "，".join(f"{k}={v}" for k, v in risky.items())
    level = "错误" if anonymous else "提示"
    msg = "文档属性残留身份信息（暗标可据此识别投标人）" if anonymous else "文档属性含身份信息"
    f.add(level, "C4", f"{msg}：{detail}", path.name)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="投标文件一致性检查")
    ap.add_argument("paths", nargs="+", type=Path, help="文件或目录")
    ap.add_argument("--anonymous", action="store_true", help="暗标模式：文档属性泄露按错误处理")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = ap.parse_args(argv)

    pairs = collect(args.paths)
    if not pairs:
        print("没有找到可检查的 md/txt/docx 文件", file=sys.stderr)
        return 2

    f = Findings()
    price_index: dict[str, list[tuple[float, str, int]]] = {}
    for path, text in pairs:
        check_file(path, text, f, price_index)
        if path.suffix.lower() in DOCX_SUFFIX:
            check_meta(path, f, args.anonymous)

    # 4) 同一价格标签跨文件不一致（多包号项目请自行排除）
    for lab, vals in price_index.items():
        if lab in ("大写", "小写", "小计"):
            continue
        if len({v for v, _, _ in vals}) > 1 and len({p for _, p, _ in vals}) > 1:
            detail = "，".join(f"{v:.2f}（{p}:{l}）" for v, p, l in vals[:5])
            f.add("错误", "C5", f"「{lab}」跨文件金额不同：{detail}（不同包号可忽略）", "多文件")

    if args.json:
        print(json.dumps({"files": [str(p) for p, _ in pairs], "findings": f.items,
                          "errors": f.errors, "warnings": f.warns}, ensure_ascii=False, indent=2))
    else:
        print(f"检查 {len(pairs)} 个文件")
        for item in f.items:
            print(f"[{item['level']}] {item['code']} {item['where']}  {item['message']}")
        if not f.items:
            print("未发现形式矛盾（不等于标书合格）")
        print(f"汇总：错误 {f.errors}，提示 {f.warns}")
    return 1 if f.errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
