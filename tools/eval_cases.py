#!/usr/bin/env python3
"""跑 eval/cases 的基准集。

两种用法：

1）自检（默认）——每个案例都有一份「金标」和一份「反例」：
   金标必须全过、反例必须被拦下。两者都成立才算这个案例有判别力，
   否则说明断言写空了（金标都过不了，或反例也能过）。

       python3 tools/eval_cases.py
       python3 tools/eval_cases.py --case E03          # 只看一个案例

2）判一份真实产出（模型跑出来的答案）：

       python3 tools/eval_cases.py --case E03 --answer /path/to/answer.md

断言类型（写在 case.json 的 checks 里）：

  must_include      {"values": [正则…]}      每条正则都要命中
  must_not_include  {"values": [正则…]}      每条正则都不许命中
  must_not_affirm   {"values": [词…]}        不得「肯定地」声称；同一分句内有否定词不算
  max_lines         {"value": n}             行数上限
  case_no_allow     {"values": [案号…]}       正文出现的案号必须都在白名单内
  lint              {"mode": "self", "strict": true, "contract": "x.md",
                     "absent": ["R19"], "present": ["R5"]}
                                             跑 citation_lint，按规则号判
  docgen            {"template": "complaint", "input": "x.json", "placeholders": n}
                                             从 JSON 生成 docx，校验 XML 合法与占位符数

无第三方依赖，Python 3.8+。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT / "eval" / "cases"
TOOLS = ROOT / "tools"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


CL = load_module("citation_lint_for_eval", TOOLS / "citation_lint.py")
DG = load_module("docgen_for_eval", TOOLS / "docgen.py")


def rule_codes(items: list[str]) -> set[str]:
    out = set()
    for item in items:
        m = re.match(r"\[?(R\d+)\]?", str(item).strip())
        if m:
            out.add(m.group(1))
    return out


def check_one(chk: dict, text: str, base: Path) -> tuple[bool, str]:
    kind = chk.get("type")

    if kind == "must_include":
        for pat in chk.get("values", []):
            try:
                if not re.search(pat, text):
                    return False, f"缺「{pat}」"
            except re.error as exc:
                return False, f"正则无效「{pat}」：{exc}"
        return True, ""

    if kind == "must_not_include":
        for pat in chk.get("values", []):
            try:
                m = re.search(pat, text)
            except re.error as exc:
                return False, f"正则无效「{pat}」：{exc}"
            if m:
                return False, f"出现不该有的「{m.group(0)[:40]}」"
        return True, ""

    if kind == "must_not_affirm":
        # 复用 lint 的分句否定判断：金标写「不能写成『不存在任何债务』」不算声称
        for word in chk.get("values", []):
            if CL.affirms_claim(text, word):
                return False, f"出现肯定声称「{word}」"
        return True, ""

    if kind == "max_lines":
        try:
            limit = int(chk["value"])
        except (KeyError, TypeError, ValueError):
            return False, f"max_lines 配置无效：{chk.get('value')!r}"
        n = len(text.splitlines())
        return (n <= limit), ("" if n <= limit else f"{n} 行 > 上限 {limit}")

    if kind == "case_no_allow":
        allow = {CL.norm(x) for x in chk.get("values", [])}
        found = {CL.norm(m.group(0)) for m in CL.CASE_NO_RE.finditer(text)}
        extra = found - allow
        return (not extra), (f"出现未登记案号：{'、'.join(sorted(extra))}" if extra else "")

    if kind == "lint":
        mode = chk.get("mode", "self")
        strict = bool(chk.get("strict", False))
        contract = None
        if chk.get("contract"):
            contract = base / chk["contract"]
            if not contract.is_file():
                return False, f"契约文件不存在：{contract}"
        try:
            with tempfile.TemporaryDirectory() as tmp:
                body = Path(tmp) / "answer.md"
                body.write_text(text, encoding="utf-8")
                rep = CL.lint(body, None, mode, strict, contract)
        except Exception as exc:  # 单个 lint 用例失败不应拖垮整批
            return False, f"lint 执行失败：{type(exc).__name__}: {exc}"
        codes = rule_codes(rep.errors) | rule_codes(rep.warnings)
        hits = {c: [x for x in rep.errors + rep.warnings if f"[{c}]" in x] for c in codes}
        absent = chk.get("absent", [])
        bad = [c for c in absent if c in codes]
        if bad:
            sample = hits[bad[0]][0][:120]
            return False, f"{'、'.join(bad)} 命中：{sample}"
        missing = [c for c in chk.get("present", []) if c not in codes]
        if missing:
            return False, f"应触发但未触发：{'、'.join(missing)}"
        return True, ""

    if kind == "docgen":
        try:
            src = base / chk["input"]
            if not src.is_file():
                return False, f"docgen 输入不存在：{src}"
            data = json.loads(src.read_text(encoding="utf-8"))
            template = chk["template"]
            if template not in DG.TEMPLATES:
                return False, f"未知 docgen 模板：{template}"
            blocks = DG.TEMPLATES[template](data)
            got = sum(blk.count("【待补") for blk in blocks)
            want = chk.get("placeholders")
            if want is not None and got != want:
                return False, f"占位符 {got} 处，期望 {want} 处"
            with tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / "out.docx"
                DG.build_docx(blocks, out)
                import zipfile

                with zipfile.ZipFile(out) as zf:
                    xml_bytes = zf.read("word/document.xml")
            try:
                ET.fromstring(xml_bytes)
            except ET.ParseError as exc:
                return False, f"生成的 document.xml 非法：{exc}"
            if b"\x0c" in xml_bytes:
                return False, "document.xml 残留换页符 \\x0c"
        except (OSError, ValueError, KeyError, TypeError) as exc:
            return False, f"docgen 执行失败：{type(exc).__name__}: {exc}"
        return True, ""

    return False, f"未知断言类型 {kind!r}"


def run_answer(case: dict, answer: Path, base: Path | None = None) -> list[tuple[str, bool, str]]:
    text = answer.read_text(encoding="utf-8")
    base = base or answer.parent
    results = []
    for chk in case.get("checks", []):
        ok, detail = check_one(chk, text, base)
        results.append((chk.get("id") or chk.get("type", "?"), ok, detail))
    return results


def load_cases(only: str | None = None) -> list[tuple[Path, dict]]:
    out: list[tuple[Path, dict]] = []
    seen: dict[str, Path] = {}
    for path in sorted(CASES.glob("*.case.json")):
        try:
            case = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            case = {
                "case_id": path.name.split(".")[0],
                "title": "（用例文件无法解析）",
                "_load_error": f"{type(exc).__name__}: {exc}",
            }
        cid = str(case.get("case_id") or path.name.split(".")[0])
        if only and cid != only:
            continue
        if cid in seen:
            case["_duplicate"] = f"case_id 与 {seen[cid].name} 重复"
        else:
            seen[cid] = path
        out.append((path, case))
    return out


def selfcheck(only: str | None) -> int:
    cases = load_cases(only)
    if not cases:
        print(f"没有找到案例：{CASES}")
        return 1

    total_ok = 0
    problems: list[str] = []

    for path, case in cases:
        cid = case.get("case_id", path.stem)
        title = case.get("title", "")
        try:
            if case.get("_load_error"):
                raise ValueError(f"用例文件无法解析：{case['_load_error']}")
            if case.get("_duplicate"):
                raise ValueError(case["_duplicate"])
            if not case.get("checks"):
                raise ValueError("checks 为空，无法判定")
            if not case.get("gold"):
                raise ValueError("缺少 gold 字段")
            if not case.get("bad"):
                raise ValueError("缺少 bad 反例，无法判定判别力")
            gold = path.parent / case["gold"]
            bad = path.parent / case["bad"]
            if not gold.is_file():
                raise FileNotFoundError(f"金标不存在：{gold}")
            if not bad.is_file():
                raise FileNotFoundError(f"反例不存在：{bad}")

            g = run_answer(case, gold, path.parent)
            g_pass = sum(1 for _, ok, _ in g if ok)
            b = run_answer(case, bad, path.parent)
            b_bad = sum(1 for _, ok, _ in b if not ok)
            b_detail = next((f"{n}：{d}" for n, ok, d in b if not ok), "")

            discriminating = bool(g) and g_pass == len(g) and b_bad > 0
            total_ok += 1 if discriminating else 0
            flag = "✓" if discriminating else "✗"
            print(f"  {flag} {cid} {title}")
            print(f"      金标 {g_pass}/{len(g)} 通过｜反例被拦 {b_bad}/{len(b)} 条：{b_detail}")
            for name, ok, detail in g:
                if not ok:
                    print(f"      金标未过 → {name}：{detail}")
            if b_bad == 0:
                print("      反例未被拦下 → 断言没咬住这一类错误")
            if not discriminating:
                problems.append(cid)
        except Exception as exc:
            print(f"  ✗ {cid} {title}")
            print(f"      用例异常 → {type(exc).__name__}: {exc}")
            problems.append(cid)

    print(f"\n判别力：{total_ok}/{len(cases)} 个案例（金标全过且反例被拦）")
    if problems:
        print("不合格：" + "、".join(problems))
        return 1
    return 0


def grade_one(only: str, answer: Path) -> int:
    cases = load_cases(only)
    if not cases:
        print(f"没有找到案例 {only}")
        return 1
    path, case = cases[0]
    try:
        if case.get("_load_error"):
            raise ValueError(f"用例文件无法解析：{case['_load_error']}")
        if not case.get("checks"):
            raise ValueError("checks 为空，无法判定")
        results = run_answer(case, answer, path.parent)
    except Exception as exc:
        print(f"{case.get('case_id')} 执行失败：{type(exc).__name__}: {exc}")
        return 1
    passed = sum(1 for _, ok, _ in results if ok)
    print(f"{case.get('case_id')} {case.get('title')}")
    for name, ok, detail in results:
        print(f"  {'✓' if ok else '✗'} {name}" + ("" if ok else f"  → {detail}"))
    print(f"\n{passed}/{len(results)} 条断言通过")
    return 0 if passed == len(results) else 1


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="跑 eval/cases 基准集")
    ap.add_argument("--case", help="只跑某个案例编号，如 E03")
    ap.add_argument("--answer", help="判一份产出（缺省则跑金标/反例自检）")
    ap.add_argument("--list", action="store_true", help="列出案例")
    args = ap.parse_args(argv)

    if args.list:
        for path, case in load_cases():
            print(f"{case.get('case_id')}  {case.get('title')}  （{path.name}）")
        return 0
    if args.answer:
        if not args.case:
            ap.error("--answer 需要配合 --case 使用")
        return grade_one(args.case, Path(args.answer))
    return selfcheck(args.case)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
