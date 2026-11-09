#!/usr/bin/env python3
"""投标工具的回归测试：用合成文件跑一遍，确认四类检查都还在工作。

这个测试集不评判标书质量，只保证工具没被改坏：跨文件金额冲突、表格合计不符、
暗标文档属性、实质性条款漏项、业绩缺口、超限价。

用法：
    python3 tools/test_tender.py

退出码：0 全过；1 有失败。无第三方依赖。
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"

TENDER = """# 磋商文件（项目编号：TEST-001）
1. 供应商应当具有律师事务所执业许可证，且设立满三年以上。
2. 供应商须提供近三年同类项目业绩不少于三项。
★3. 供应商应提供团队成员近三个月社会保险缴纳证明，否则按无效响应处理。
"""

BID = """# 响应文件
1. 本所持有律师事务所执业许可证，设立于 2011 年。
2. 近三年同类业绩：某局顾问（2023）。
投标总价：人民币 1200000.00 元（大写：壹佰贰拾万元整）
"""

QUOTE_OK = """# 开标一览表
| 项目 | 金额（元） |
|---|---|
| 顾问费 | 600000.00 |
| 代理费 | 600000.00 |
| 合计 | 1200000.00 |
"""

# 与响应文件总价不同、但表内自洽 → 只该触发 C5
QUOTE_CONFLICT = """# 开标一览表
| 项目 | 金额（元） |
|---|---|
| 顾问费 | 590000.00 |
| 代理费 | 590000.00 |
| 合计 | 1180000.00 |

投标总价：人民币 1180000.00 元（大写：壹佰壹拾捌万元整）
"""
# 表内合计与分项不符 → 只该触发 C6
QUOTE_BAD = QUOTE_OK.replace("| 合计 | 1200000.00 |", "| 合计 | 1210000.00 |")

SCORE = {
    "项目": "测试项目", "预算": 1500000, "最高限价": 1500000, "投标价": 1600000,
    "价格分": {"分值": 20, "方法": "最低价"}, "对手价": [1100000],
    "评分项": [{"名称": "服务方案", "分值": 40, "自评": 30}], "对手非价格分": 55,
}

CREDITS = {"credits": [
    {"id": "C-1", "project": "某局法律顾问", "year": 2023, "amount": 300000,
     "scope": ["顾问"], "credits_use": "yes"},
    {"id": "C-2", "project": "某公司合同审查", "year": 2024, "amount": 200000,
     "scope": ["合同"], "credits_use": "need_auth"},
]}


def make_docx(path: Path, body: str, creator: str = "王某某") -> None:
    doc = ('<?xml version="1.0" encoding="UTF-8"?><w:document '
           'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
           f'<w:p><w:r><w:t>{body}</w:t></w:r></w:p></w:body></w:document>')
    core = ('<?xml version="1.0" encoding="UTF-8"?><cp:coreProperties xmlns:cp="x" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/">'
            f'<dc:creator>{creator}</dc:creator></cp:coreProperties>')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", doc)
        z.writestr("docProps/core.xml", core)


def run(args: list[str]) -> tuple[int, str]:
    p = subprocess.run([sys.executable, *args], capture_output=True, text=True, encoding="utf-8")
    return p.returncode, p.stdout + p.stderr


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="tender-test-"))
    (tmp / "采购文件").mkdir()
    (tmp / "标书").mkdir()
    (tmp / "采购文件" / "磋商文件.md").write_text(TENDER, "utf-8")
    (tmp / "标书" / "响应文件.md").write_text(BID, "utf-8")
    (tmp / "标书" / "报价表.md").write_text(QUOTE_OK, "utf-8")
    (tmp / "采购文件" / "x").mkdir(exist_ok=True)
    (tmp / "score.json").write_text(json.dumps(SCORE, ensure_ascii=False), "utf-8")
    (tmp / "credits.json").write_text(json.dumps(CREDITS, ensure_ascii=False), "utf-8")

    cases: list[tuple[str, bool, str]] = []

    code, out = run([str(TOOLS / "tender_matrix.py"), str(tmp / "采购文件"),
                     "--body", str(tmp / "标书")])
    cases.append(("矩阵抽到实质性条款", "实质性" in out and "★" in out, out))
    cases.append(("矩阵报未覆盖且返回 1", code == 1 and "未在正文找到" in out, out))

    (tmp / "标书" / "报价表.md").write_text(QUOTE_CONFLICT, "utf-8")
    code, out = run([str(TOOLS / "tender_consistency.py"), str(tmp / "标书")])
    cases.append(("跨文件总价冲突被捕获", "C5" in out and code == 1, out))

    (tmp / "标书" / "报价表.md").write_text(QUOTE_BAD, "utf-8")
    code, out = run([str(TOOLS / "tender_consistency.py"), str(tmp / "标书")])
    cases.append(("表格合计与分项不符被捕获", "C6" in out and code == 1, out))

    docx = tmp / "标书" / "暗标.docx"
    make_docx(docx, "投标总价：人民币 1200000.00 元")
    code, out = run([str(TOOLS / "tender_consistency.py"), str(docx), "--anonymous"])
    cases.append(("docx 属性泄露被捕获", "C4" in out and code == 1, out))

    code, out = run([str(TOOLS / "tender_score.py"), str(tmp / "score.json")])
    cases.append(("超限价判无效", "超最高限价" in out and code == 1, out))

    code, out = run([str(TOOLS / "tender_credits.py"), "--credits", str(tmp / "credits.json"),
                     "--need", "3", "--years", "2023-2025"])
    cases.append(("业绩缺口被算出", "缺 1 项" in out and code == 1, out))

    failed = [name for name, ok, _ in cases if not ok]
    for name, ok, out in cases:
        print(f"[{'通过' if ok else '失败'}] {name}")
        if not ok:
            print("  输出：", out.strip()[:400].replace("\n", " | "))
    print(f"结果：{len(cases) - len(failed)}/{len(cases)} 通过")
    shutil.rmtree(tmp, ignore_errors=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
