#!/usr/bin/env python3
"""citation_lint.py（7 项）与 docgen.py（4 项）的 11 条回归探针。

用法：
    python3 tests/test_lint_docgen_bugs.py
    python3 tests/test_lint_docgen_bugs.py tools/citation_lint.py tools/docgen.py
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_mod(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def run_probes(lint_path: Path, docgen_path: Path) -> int:
    cl = load_mod("citation_lint_under_test", lint_path)
    dg = load_mod("docgen_under_test", docgen_path)

    results: list[tuple[str, bool, str]] = []

    def check(title: str, fn) -> None:
        try:
            fn()
            results.append((title, True, "OK"))
        except Exception as exc:
            results.append((title, False, str(exc)))

    with tempfile.TemporaryDirectory() as tmp:
        td = Path(tmp)

        # 1. load_ledger_md 表头含「官方复核」不污染「来源渠道」
        def t1():
            md = td / "ledger1.md"
            md.write_text(
                "| 编号 | 类型 | 文号 | 来源渠道 | 定位 | 读取范围 | 摘录 | 回读 | 官方复核 | 规范效力 | 适用时点 |\n"
                "|---|---|---|---|---|---|---|---|---|---|---|\n"
                "| N-01 | 法规 | 第五百八十五条 | 商业库 | 第五百八十五条 | 全文 | 当事人可以约定一方违约时应当根据违约情况向对方支付一定数额的违约金 | 已回读(2026-05-01) | 未核 | 现行有效 | 2026 |\n",
                encoding="utf-8",
            )
            entries = cl.load_ledger_md(md)
            assert entries[0]["channel"] == "commercial", f"期望 commercial，实得 {entries[0]['channel']}"

        check("1. [citation_lint] load_ledger_md 表头『官方复核』不污染渠道列", t1)

        # 2. load_ledger_md 分列写「定位」与「出处」时不丢官方链接
        def t2():
            md = td / "ledger2.md"
            md.write_text(
                "| 编号 | 类型 | 文号 | 来源渠道 | 定位 | 出处 | 读取范围 | 摘录 | 回读 | 官方复核 | 规范效力 | 适用时点 |\n"
                "|---|---|---|---|---|---|---|---|---|---|---|---|\n"
                "| N-01 | 法规 | 第五百八十五条 | 官方 | 第五百八十五条 | https://flk.npc.gov.cn/detail2.html?abc | 全文 | 当事人可以约定一方违约时应当根据违约情况向对方支付一定数额的违约金 | 已回读(2026-05-01) | 已核 | 现行有效 | 2026 |\n",
                encoding="utf-8",
            )
            body = td / "body2.md"
            body.write_text(
                "# 意见书〔自查〕\n"
                "依[N-01]，「当事人可以约定一方违约时应当根据违约情况向对方支付一定数额的违约金」。\n",
                encoding="utf-8",
            )
            rep = cl.lint(body, md, "self", False)
            r18 = [e for e in rep.errors if "[R18]" in e]
            assert not r18, f"分列写定位与出处不应报 R18：{r18}"

        check("2. [citation_lint] load_ledger_md 定位与出处分列时不丢官方 URL", t2)

        # 3. 内联「## 引用底稿」表不误触 R3、不掩盖 R10 与 R12
        def t3():
            ledger = td / "ledger3.json"
            ledger.write_text(
                json.dumps([
                    {
                        "id": "N-01", "type": "法规", "number": "第五百八十五条",
                        "location": "https://flk.npc.gov.cn/detail2.html?abc",
                        "read_scope": "full", "official_check": "verified", "channel": "official",
                        "quote": "当事人可以约定一方违约时应当根据违约情况向对方支付一定数额的违约金",
                        "reread": "已回读(2026-05-01)", "norm_status": "current", "apply_time": "2026",
                    },
                    {
                        "id": "C-02", "type": "案例", "number": "（2024）京01民终999号",
                        "location": "裁判文书网", "read_scope": "abstract",
                        "official_check": "unverified", "channel": "commercial",
                        "quote": "", "reread": "",
                    },
                ], ensure_ascii=False),
                encoding="utf-8",
            )
            body = td / "body3.md"
            body.write_text(
                "# 法律意见〔自查〕\n"
                "本案应支持违约金调整请求 [N-01]。\n\n"
                "## 引用底稿\n"
                "| 编号 | 名称 | 读取范围 | 摘录 | 回读 |\n"
                "|---|---|---|---|---|\n"
                "| N-01 | 民法典585条 | 全文 | 当事人可以约定一方违约时应当根据违约情况向对方支付一定数额的违约金 | 已回读(2026-05-01) |\n"
                "| C-02 | （2024）京01民终999号 | 摘要 | 仅读摘要未取全文 | 未回读 |\n",
                encoding="utf-8",
            )
            rep = cl.lint(body, ledger, "self", False)
            r3 = [e for e in rep.errors if "[R3]" in e]
            r10 = [w for w in rep.warnings if "[R10]" in w and "C-02" in w]
            r12_err = [e for e in rep.errors if "[R12]" in e]
            assert not r3, f"底稿表自身定义行不应触发 R3：{r3}"
            assert r10, f"正文未引用的 C-02 应触发 R10 警告，实得 warnings={rep.warnings}"
            assert r12_err, f"正文未出现摘录（仅底稿表有）应报 R12 错误而非降级警告，实得 errors={rep.errors}"

        check("3. [citation_lint] 排除文末内联引用底稿表干扰（R3/R10/R12）", t3)

        # 4. 自查模式写「未经复核」不触发 R9 错误
        def t4():
            body = td / "body4.md"
            body.write_text("# 咨询意见〔自查〕\n本稿已完成自查，未经复核（未做独立核验）。\n", encoding="utf-8")
            rep = cl.lint(body, None, "self", False)
            r9 = [e for e in rep.errors if "[R9]" in e]
            assert not r9, f"否定句『未经复核』不应报 R9：{r9}"

        check("4. [citation_lint] R9 识别『未经复核／未做独立核验』否定语境", t4)

        # 5. affirms_claim 顿号并列否定与「禁止」不触发 R17
        def t5():
            body = td / "body5.md"
            body.write_text(
                "# 意见书〔草稿〕\n"
                "本稿未经联网回读，回读率 0%，不可作为定稿、可交付件或可直接使用文本，禁止标为已核实。\n"
                "## 待回读清单\n- N-01\n",
                encoding="utf-8",
            )
            rep = cl.lint(body, None, "offline", False)
            r17 = [e for e in rep.errors if "[R17]" in e]
            assert not r17, f"并列否定与禁止句不应报 R17：{r17}"

        check("5. [citation_lint] affirms_claim 支持顿号并列否定与『禁止/严禁』", t5)

        # 6. [S-01] 标准标签识别与〔N-1〕→ N-01 编号归一
        def t6():
            md = td / "ledger6.md"
            md.write_text(
                "| 编号 | 类型 | 文号 | 来源渠道 | 定位 | 读取范围 | 摘录 | 回读 | 官方复核 | 规范效力 | 适用时点 |\n"
                "|---|---|---|---|---|---|---|---|---|---|---|\n"
                "| 〔N-1〕 | 法规 | 第十条 | 商业 | 第十条 | 全文 | 当事人订立合同可以采取书面形式口头形式或者其他形式 | 已回读(2026-05-01) | 未核 | 现行有效 | 2026 |\n"
                "| S-1 | 标准 | GB/T 1-2020 | 商业 | 4.1 | 全文 | 产品的技术要求应当符合本标准第四章列明的全部指标 | 已回读(2026-05-01) | 未核 | 现行有效 | 2026 |\n",
                encoding="utf-8",
            )
            body = td / "body6.md"
            body.write_text(
                "# 意见〔自查〕\n"
                "依 [N-01]，「当事人订立合同可以采取书面形式口头形式或者其他形式」。\n"
                "依 [S-01]，「产品的技术要求应当符合本标准第四章列明的全部指标」。\n",
                encoding="utf-8",
            )
            rep = cl.lint(body, md, "self", False)
            r8 = [e for e in rep.errors if "[R8]" in e]
            r10 = [w for w in rep.warnings if "[R10]" in w]
            assert not r8 and not r10, f"编号归一与 S- 标签失败：errors={rep.errors}, warnings={rep.warnings}"

        check("6. [citation_lint] 支持 [S-xx] 标签及底稿编号自动去括号补零归一", t6)

        # 7. 大写带端口官方域名 + R19 局部「其中 1 项缺陷」与「必改 0 项」
        def t7():
            assert cl.official_domain_ok("https://WWW.GOV.CN:443/zhengce/xxgk/gjgzk/test.htm") is True, "大写+端口域名未识别"
            body = td / "body7.md"
            body.write_text(
                "# 合同审查〔自查〕\n"
                "本合同存在显著漏洞，其中 1 项缺陷属高风险，必改 0 项。\n\n"
                "## 风险表\n"
                "| 序号 | 等级 | 位置 | 问题描述 |\n"
                "|---|---|---|---|\n"
                "| 1 | 高 | 第1条 | 付款节点不明 |\n"
                "| 2 | 低 | 第2条 | 通知地址缺邮编 |\n\n"
                "## 必改项\n"
                "| 编号 | 事项 |\n"
                "|---|---|\n"
                "| 无 | 暂无必改 |\n",
                encoding="utf-8",
            )
            rep = cl.lint(body, None, "self", False)
            r19_err = [e for e in rep.errors if "[R19]" in e]
            assert not r19_err, f"不应把『其中 1 项缺陷属高风险』误判为总数 1：{r19_err}"

        check("7. [citation_lint] 大小写端口 URL 解析与 R19 计数边界", t7)

        # 8. docgen 过滤 XML 非法控制字符（如 \x0c 换页符）
        def t8():
            out_docx = td / "t8.docx"
            blocks = dg.tpl_complaint({"facts": ["第一页内容\x0c第二页内容\x07"]})
            dg.build_docx(blocks, out_docx)
            with zipfile.ZipFile(out_docx) as zf:
                xml_bytes = zf.read("word/document.xml")
            ET.fromstring(xml_bytes)  # 含 \x0c 或 \x07 时直接抛 ParseError

        check("8. [docgen] 过滤 \\x0c 等非法控制字符，确保生成的 XML 合法", t8)

        # 9. docgen 将段内 \n 转为 <w:br/>
        def t9():
            r_xml = dg.run("第一行\n第二行")
            assert "<w:br/>" in r_xml, f"换行符未转为 <w:br/>：{r_xml}"

        check("9. [docgen] run() 将换行符 \\n 转为 OpenXML <w:br/>", t9)

        # 10. docgen <w:pPr> 子节点顺序符合 ECMA-376（spacing -> ind -> jc）
        def t10():
            p_xml = dg.para("正文段落", align="both", indent=True)
            i_sp = p_xml.index("<w:spacing")
            i_ind = p_xml.index("<w:ind")
            i_jc = p_xml.index("<w:jc")
            assert i_sp < i_ind < i_jc, f"w:pPr 子节点顺序违规：{p_xml}"

        check("10. [docgen] para() 中 w:pPr 子节点严格按 spacing -> ind -> jc 排序", t10)

        # 11. docgen main() 准确统计同一块内的多处【待补】占位符
        def t11():
            in_json = td / "ev.json"
            out_docx = td / "ev.docx"
            in_json.write_text(
                json.dumps({"items": [{"name": "【待补：证据1】", "purpose": "【待补：证明目的】"}]}, ensure_ascii=False),
                encoding="utf-8",
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                dg.main(["evidence", "--input", str(in_json), "--out", str(out_docx)])
            output = buf.getvalue()
            # 案号(1) + 提交方(1) + 表格内(2) + 提交人(1) + 日期(1) = 6 处
            assert "仍有 6 处【待补】" in output, f"多占位符漏计，输出为：{output.strip()}"

        check("11. [docgen] main() 按实际出现次数统计【待补】占位符", t11)

    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\n探针结果：{passed}/{len(results)} 通过")
    for title, ok, detail in results:
        mark = "✓" if ok else "✗"
        print(f"  {mark} {title}" + ("" if ok else f"  --> {detail}"))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    lint_arg = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "tools" / "citation_lint.py"
    docgen_arg = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "tools" / "docgen.py"
    raise SystemExit(run_probes(lint_arg, docgen_arg))
