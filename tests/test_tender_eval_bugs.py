#!/usr/bin/env python3
"""投标四工具与 eval_cases 的核心回归探针。

覆盖这次修复的关键点：中文序号、--min-score、短强条款、C1 就近配对、
C6 金额列/合计、C4 app.xml、C5 限价软提示、C3 日历、价格分公式与去极值、
业绩授权口径、eval 答案路径/空 checks/坏正则/顿号肯定。

默认跑仓库 tools/；用 TSL_TOOLS_DIR 指向修复前基线目录，可验证基线全挂。
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = Path(os.environ.get("TSL_TOOLS_DIR", ROOT / "tools")).resolve()
CASES = ROOT / "eval" / "cases"


def run_tool(name: str, *args: str) -> tuple[int, str]:
    p = subprocess.run(
        [sys.executable, str(TOOLS / name), *args],
        capture_output=True, text=True, encoding="utf-8",
    )
    return p.returncode, p.stdout + p.stderr


def load_mod(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def make_docx(path: Path, company: str) -> None:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body><w:p><w:r><w:t>投标文件</w:t></w:r></w:p></w:body></w:document>",
        )
        z.writestr(
            "docProps/core.xml",
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:creator></dc:creator></cp:coreProperties>',
        )
        z.writestr(
            "docProps/app.xml",
            '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
            f"<Company>{company}</Company><Manager>张三</Manager></Properties>",
        )


def probes() -> int:
    results: list[tuple[str, bool, str]] = []

    def check(title: str, fn) -> None:
        try:
            fn()
            results.append((title, True, "OK"))
        except Exception as exc:
            results.append((title, False, f"{type(exc).__name__}: {exc}"))

    with tempfile.TemporaryDirectory() as tmp:
        td = Path(tmp)

        def t_matrix_id_and_short() -> None:
            src = td / "tender.md"
            src.write_text("一、投标人必须提供有效的营业执照副本。\n★不得转包。\n", encoding="utf-8")
            code, out = run_tool("tender_matrix.py", str(src), "--json")
            assert code == 0, out[-500:]
            data = json.loads(out)
            ids = [r["采购编号"] for r in data["rows"]]
            assert "一" in ids, ids
            assert any("★不得转包" in r["要求原文"] for r in data["rows"]), data["rows"]

        check("matrix 中文序号 + 短强条款", t_matrix_id_and_short)

        def t_matrix_min_score() -> None:
            src = td / "req.md"
            body = td / "body.md"
            src.write_text("必须提供有效的营业执照副本。\n", encoding="utf-8")
            body.write_text("必须提供有效的营业执照。\n", encoding="utf-8")
            code, out = run_tool("tender_matrix.py", str(src), "--body", str(body), "--min-score", "0.9", "--json")
            assert code == 0, out[-500:]
            data = json.loads(out)
            assert data["rows"][0]["覆盖"] != "已应答", data["rows"][0]

        check("matrix --min-score 生效", t_matrix_min_score)

        def t_c6_amount_col() -> None:
            src = td / "c6.md"
            src.write_text(
                "| 项目 | 金额（元） | 数量 |\n|---|---|---|\n"
                "| 甲 | 300 | 1 |\n| 乙 | 300 | 1 |\n| 合计 | 999 |  |\n",
                encoding="utf-8",
            )
            code, out = run_tool("tender_consistency.py", str(src))
            assert "C6" in out and code == 1, out[-800:]

        check("consistency C6 金额列与合计", t_c6_amount_col)

        def t_c1_clause() -> None:
            src = td / "c1.md"
            src.write_text("违约金 5 万元；合同总价壹佰万元整。\n", encoding="utf-8")
            code, out = run_tool("tender_consistency.py", str(src))
            assert "[错误] C1" not in out, out[-800:]
            assert code == 0, out[-800:]

        check("consistency C1 同分句配对", t_c1_clause)

        def t_c4_app_xml() -> None:
            src = td / "meta.docx"
            make_docx(src, "某某投标公司")
            code, out = run_tool("tender_consistency.py", str(src), "--anonymous")
            assert "C4" in out and code == 1, out[-800:]

        check("consistency C4 读 app.xml", t_c4_app_xml)

        def t_c5_soft() -> None:
            a = td / "a.md"
            b = td / "b.md"
            a.write_text("最高限价：100万元。\n", encoding="utf-8")
            b.write_text("最高限价：120万元。\n", encoding="utf-8")
            code, out = run_tool("tender_consistency.py", str(a), str(b))
            assert "C5" in out and "提示" in out, out[-800:]
            assert code == 0, out[-800:]

        check("consistency C5 限价差异仅提示", t_c5_soft)

        def t_c3_date() -> None:
            src = td / "c3.md"
            src.write_text("开标时间：2026-02-31。\n", encoding="utf-8")
            code, out = run_tool("tender_consistency.py", str(src))
            assert "日期不存在" in out and code == 0, out[-800:]

        check("consistency C3 日历校验", t_c3_date)

        def score_sheet(name: str, payload: dict) -> Path:
            p = td / name
            p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            return p

        def t_score_formula() -> None:
            p = score_sheet("s1.json", {
                "项目": "t", "投标价": 100, "最高限价": 150,
                "价格分": {"分值": 30, "方法": "基准价"},
                "对手价": [100, 101],
            })
            code, out = run_tool("tender_score.py", str(p), "--json")
            assert code == 0, out[-500:]
            data = json.loads(out)
            assert abs(data["价格分"] - 29.67) < 0.01, data["价格分"]

        check("score 每 1% 扣 k 分", t_score_formula)

        def t_score_trim() -> None:
            p = score_sheet("s2.json", {
                "项目": "t", "投标价": 100, "最高限价": 200,
                "价格分": {"分值": 30, "方法": "基准价"},
                "对手价": [100, 100, 100, 200],
            })
            code, out = run_tool("tender_score.py", str(p), "--json")
            assert code == 0, out[-500:]
            data = json.loads(out)
            assert data["价格分"] == 30, data["价格分"]
            assert "已去极值" in data["基准价口径"], data["基准价口径"]

        check("score 5 家去极值", t_score_trim)

        def t_score_null_and_cap() -> None:
            p = score_sheet("s3.json", {
                "项目": "t", "投标价": "100万", "最高限价": 2000000,
                "价格分": {"分值": 30, "方法": "基准价"},
                "对手价": [None, "100万"],
            })
            code, out = run_tool("tender_score.py", str(p), "--json")
            assert code == 0, out[-500:]
            assert json.loads(out)["价格分"] >= 0
            p2 = score_sheet("s4.json", {
                "项目": "t", "投标价": 100, "最高限价": 0,
                "价格分": {"分值": 30, "方法": "基准价"}, "对手价": [100],
            })
            code2, _ = run_tool("tender_score.py", str(p2), "--json")
            assert code2 == 1, code2

        check("score null/万元/限价 0", t_score_null_and_cap)

        def t_credits_gap() -> None:
            p = td / "credits.json"
            p.write_text(json.dumps({"credits": [
                {"id": "1", "project": "顾问", "year": 2023, "amount": 300000, "credits_use": "yes"},
                {"id": "2", "project": "合同", "year": 2024, "amount": 200000, "credits_use": "need_auth"},
            ]}, ensure_ascii=False), encoding="utf-8")
            code, out = run_tool("tender_credits.py", "--credits", str(p), "--need", "3", "--years", "2023-2025")
            assert "缺 1 项" in out and code == 1, out[-800:]
            code2, out2 = run_tool("tender_credits.py", "--credits", str(p), "--need", "2", "--years", "2023-2025")
            assert "需补齐授权" in out2 and code2 == 1, out2[-800:]

        check("credits 授权缺口退出码", t_credits_gap)

        def t_credits_list_and_wan() -> None:
            p = td / "list.json"
            p.write_text(json.dumps([
                {"id": "1", "project": "p", "year": "22", "amount": "100万", "credits_use": "yes"},
            ], ensure_ascii=False), encoding="utf-8")
            code, out = run_tool("tender_credits.py", "--credits", str(p), "--need", "1",
                                 "--min-amount", "1", "--years", "2020-2025")
            assert code == 0, out[-800:]

        check("credits 顶层数组/22/100万", t_credits_list_and_wan)

        def t_eval_answer_path() -> None:
            ec = load_mod("eval_under_test", TOOLS / "eval_cases.py")
            ec.CASES = CASES
            case_path = next(CASES.glob("E02*.case.json"))
            case = json.loads(case_path.read_text(encoding="utf-8"))
            copied = td / "E02-answer.md"
            copied.write_text((case_path.parent / case["gold"]).read_text(encoding="utf-8"), encoding="utf-8")
            res = ec.run_answer(case, copied, case_path.parent)
            assert all(ok for _, ok, _ in res), res

        check("eval --answer 相对案例目录", t_eval_answer_path)

        def t_eval_empty_checks() -> None:
            ec = load_mod("eval_empty", TOOLS / "eval_cases.py")
            with tempfile.TemporaryDirectory() as sub:
                d = Path(sub)
                (d / "X.gold.md").write_text("金标", encoding="utf-8")
                (d / "X.bad.md").write_text("反例", encoding="utf-8")
                (d / "X.case.json").write_text(json.dumps({
                    "case_id": "X", "title": "空", "gold": "X.gold.md", "bad": "X.bad.md", "checks": [],
                }, ensure_ascii=False), encoding="utf-8")
                ec.CASES = d
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = ec.selfcheck(None)
                assert code == 1 and "checks 为空" in buf.getvalue(), buf.getvalue()

        check("eval 空 checks 不计判别力", t_eval_empty_checks)

        def t_eval_bad_regex() -> None:
            ec = load_mod("eval_regex", TOOLS / "eval_cases.py")
            ok, detail = ec.check_one({"type": "must_include", "values": ["["]}, "abc", td)
            assert not ok and "正则无效" in detail, (ok, detail)

        check("eval 坏正则隔离", t_eval_bad_regex)

        def t_eval_dunhao() -> None:
            ec = load_mod("eval_dun", TOOLS / "eval_cases.py")
            assert ec.CL.affirms_claim("本案不是终审判决、已生效", "已生效") is True
            assert ec.CL.affirms_claim("不可作为定稿、可交付件或可直接使用文本", "可直接使用") is False

        check("eval 顿号肯定/否定", t_eval_dunhao)

    passed = sum(1 for _, ok, _ in results if ok)
    for title, ok, detail in results:
        print(f"  {'✓' if ok else '✗'} {title}" + ("" if ok else f" → {detail}"))
    print(f"\n结果：{passed}/{len(results)} 通过")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(probes())
