#!/usr/bin/env python3
"""投标响应矩阵生成与覆盖检查：把「逐条响应」从人肉抄录变成机械比对。

标书废标，多来自漏条——采购文件 200 条要求，逐条抄进矩阵靠人做，总会丢。本工具做两件事：

1. 从采购文件抽候选要求行，按资格性／实质性／评分项分三类，产出一张带空列的 CSV 骨架
   （应答章节、证明文件、缺口、责任人由人填）。
2. 给了标书正文时，按 6 字片段重合率判断每条要求「采到了没有」，把未覆盖的挑出来。

它不做判断：条款是否真属实质性、评分办法怎么算、缺口能否补，仍要人定。分类靠关键词，
必然有误判——以采购文件原文和评标办法为准，工具只负责不漏。

用法：
    python3 tools/tender_matrix.py 采购文件.md --out matrix.csv
    python3 tools/tender_matrix.py 采购文件/ --body 标书/ --out matrix.csv
    python3 tools/tender_matrix.py 采购文件.md --body 标书.md --min-score 0.3 --json

退出码：0 正常；1 存在未被正文覆盖的要求（提示性，不等于废标）。无第三方依赖。
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import zipfile
from pathlib import Path

TEXT_SUFFIX = {".md", ".txt"}

STRONG_KW = ["★", "▲", "实质性", "否则", "无效", "废标", "不予受理", "视为不满足",
             "按无效投标处理", "拒绝"]
SCORE_KW = ["分值", "得分", "评分", "加分", "满分", "计分", "权重", "扣分"]
QUAL_KW = ["资质", "营业执照", "许可证", "执业许可", "业绩", "社保", "财务报告",
           "信用记录", "资格", "注册资本", "成立年限", "同类项目"]
REQ_KW = ["应当", "必须", "须", "不得", "不允许", "不接受", "要求", "应提供",
          "应提交", "需提供", "承诺"]

ID_RE = re.compile(r"^\s*(?:[（(]?([0-9]{1,3})[）)．.、]|[一二三四五六七八九十]{1,3}[、．.]|(第[一二三四五六七八九十百]{1,4}条))")


def docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        try:
            xml = z.read("word/document.xml").decode("utf-8", "ignore")
        except KeyError:
            return ""
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"<[^>]+>", "", xml)
    return xml.replace("&amp;", "&")


def read_text(path: Path) -> str:
    if path.suffix.lower() == ".docx":
        return docx_text(path)
    return path.read_text("utf-8", "ignore")


def gather(paths: list[Path]) -> list[Path]:
    out: list[Path] = []
    for p in paths:
        if p.is_dir():
            out += sorted(q for q in p.rglob("*")
                          if q.is_file() and q.suffix.lower() in TEXT_SUFFIX | {".docx"})
        else:
            out.append(p)
    return out


def classify(line: str) -> str:
    if any(k in line for k in STRONG_KW):
        return "实质性"
    if any(k in line for k in SCORE_KW):
        return "评分项"
    if any(k in line for k in QUAL_KW):
        return "资格性"
    return "其他"


TABLE_SEP = re.compile(r"^\|?[\s:|-]+\|?$")


def extract(path: Path) -> list[dict]:
    text = read_text(path)
    lines = text.splitlines()
    rows: list[dict] = []
    for idx, raw in enumerate(lines):
        lineno = idx + 1
        stripped = raw.strip()
        if TABLE_SEP.match(stripped) and "-" in stripped:
            continue
        is_table = stripped.count("|") >= 2
        if is_table and idx + 1 < len(lines) and TABLE_SEP.match(lines[idx + 1].strip()) and "-" in lines[idx + 1]:
            continue  # 表头行
        line = stripped.lstrip("-*#> ").strip()
        if is_table:
            line = re.sub(r"\s*\|\s*", "　", line).strip("　 ")
        if len(line) < 12 or len(line) > 400:
            continue
        if re.match(r"^第[一二三四五六七八九十百]+[章节]", line) and len(line) <= 40:
            continue
        kind = classify(line)
        if kind == "其他" and not any(k in line for k in REQ_KW):
            continue
        m = ID_RE.match(line.lstrip("★▲☆△□■*· "))
        rows.append({
            "文件": path.name,
            "行号": lineno,
            "采购编号": (m.group(1) or m.group(2) or m.group(3) or "").strip() if m else "",
            "类型": classify(line),
            "要求原文": line,
        })
    return rows


def shingles(text: str, n: int = 6) -> set[str]:
    clean = re.sub(r"[\s，。、；：（）()\"'“”‘’\-—·,.;:|*/\\]+", "", text)
    return {clean[i:i + n] for i in range(max(0, len(clean) - n + 1))}


def coverage(rows: list[dict], body_files: list[Path]) -> None:
    body_sh: set[str] = set()
    for p in body_files:
        body_sh |= shingles(read_text(p))
    for row in rows:
        req_sh = shingles(row["要求原文"])
        if not req_sh:
            row["覆盖"] = "无法判断"
            row["重合率"] = 0.0
            continue
        score = len(req_sh & body_sh) / len(req_sh)
        row["重合率"] = round(score, 2)
        row["覆盖"] = "已应答" if score >= 0.35 else ("弱匹配" if score >= 0.15 else "未找到")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="投标响应矩阵生成与覆盖检查")
    ap.add_argument("tender", nargs="+", type=Path, help="采购文件：文件或目录")
    ap.add_argument("--body", nargs="*", type=Path, default=[], help="标书正文：文件或目录")
    ap.add_argument("--out", type=Path, help="输出 CSV（默认打印摘要）")
    ap.add_argument("--min-score", type=float, default=0.35, help="判定已应答的重合率阈值")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = ap.parse_args(argv)

    tender_files = gather(args.tender)
    if not tender_files:
        print("没有找到采购文件", file=sys.stderr)
        return 2
    rows: list[dict] = []
    for p in tender_files:
        rows += extract(p)
    if not rows:
        print("未抽出候选要求行——确认文件有文本层（扫描件需先 OCR）", file=sys.stderr)
        return 2

    body_files = gather(args.body) if args.body else []
    if body_files:
        coverage(rows, body_files)

    for row in rows:
        row.setdefault("覆盖", "")
        row.setdefault("重合率", "")
        for col in ("应答章节", "证明文件", "缺口", "责任人"):
            row[col] = ""

    if args.out:
        cols = ["文件", "行号", "采购编号", "类型", "要求原文", "覆盖", "重合率",
                "应答章节", "证明文件", "缺口", "责任人"]
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)

    counts: dict[str, int] = {}
    for row in rows:
        counts[row["类型"]] = counts.get(row["类型"], 0) + 1
    missing = [r for r in rows if r["覆盖"] == "未找到"]

    if args.json:
        print(json.dumps({"total": len(rows), "by_type": counts,
                          "uncovered": len(missing),
                          "rows": rows[:200]}, ensure_ascii=False, indent=2))
    else:
        print(f"候选要求 {len(rows)} 条：" + "，".join(f"{k} {v}" for k, v in counts.items()))
        if args.out:
            print(f"矩阵骨架已写入 {args.out}")
        if body_files:
            weak = [r for r in rows if r["覆盖"] == "弱匹配"]
            print(f"未在正文找到对应：{len(missing)} 条（重合率<0.15）；另有弱匹配 {len(weak)} 条（0.15–{args.min_score}）")
            for r in missing[:10]:
                print(f"  - {r['文件']}:{r['行号']} {r['要求原文'][:60]}")
            if len(missing) > 10:
                print(f"  ……另有 {len(missing) - 10} 条，见 CSV")
            if weak:
                print("弱匹配（可能只是表述不同，需人工确认）：")
                for r in weak[:5]:
                    print(f"  ~ {r['文件']}:{r['行号']} {r['要求原文'][:50]}（{r['重合率']}）")
        else:
            print("未给 --body，跳过覆盖检查")
        print("提示：分类靠关键词，实质性／评分项以采购文件与评标办法原文为准。")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
