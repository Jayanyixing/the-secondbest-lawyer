#!/usr/bin/env python3
"""生成可直接交付的 Word 文书（零依赖，不需要 python-docx）。

律师要交的是 .docx，不是 Markdown。这个脚本把 JSON 输入直接排版成 docx：
起诉状／答辩状、证据目录、风险告知书。

用法：
    python3 tools/docgen.py complaint --input templates/complaint.sample.json --out 起诉状.docx
    python3 tools/docgen.py evidence  --input templates/evidence.sample.json  --out 证据目录.docx
    python3 tools/docgen.py risk      --input templates/risk.sample.json      --out 风险告知书.docx

输入结构与示例见 templates/*.sample.json。生成后请打开检查排版与占位符
（【待补：…】），不要把未替换的占位符交出去。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent

FONT_TITLE = "方正小标宋简体"
FONT_BODY = "仿宋"
FONT_HEAD = "黑体"


# XML 1.0 不允许的控制字符（\x09 \x0a \x0d 保留）。PDF／OCR 提取的文本常带 \x0c 换页符，
# 直接写进 word/document.xml 会让 Word 报「内容有问题，无法打开文件」。
CTRL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def esc(text: str) -> str:
    return escape(CTRL_CHARS_RE.sub("", str(text or "")))


def run(text: str, font: str = FONT_BODY, size: int = 28, bold: bool = False) -> str:
    b = "<w:b/>" if bold else ""
    # <w:t> 里的裸 \n 在 Word 里只会显示成空格；真正的换行要用 <w:br/>
    raw = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    parts = [f'<w:t xml:space="preserve">{esc(seg)}</w:t>' for seg in raw.split("\n")]
    body = "<w:br/>".join(parts)
    return (
        f'<w:r><w:rPr><w:rFonts w:ascii="Times New Roman" w:eastAsia="{font}" w:hAnsi="Times New Roman"/>'
        f'{b}<w:sz w:val="{size}"/></w:rPr>{body}</w:r>'
    )


def para(text: str = "", align: str = "both", font: str = FONT_BODY, size: int = 28,
         bold: bool = False, indent: bool = True, space_after: int = 120) -> str:
    ind = '<w:ind w:firstLineChars="200" w:firstLine="560"/>' if indent and align == "both" else ""
    jc = f'<w:jc w:val="{align}"/>' if align else ""
    # ECMA-376 的 CT_PPrBase 是严格 sequence：spacing → ind → jc。顺序反了，
    # Word／LibreOffice／OpenXML SDK 会静默丢掉排在 jc 之后的 ind 与 spacing
    return (
        f"<w:p><w:pPr><w:spacing w:after=\"{space_after}\" w:line=\"560\" w:lineRule=\"exact\"/>"
        f"{ind}{jc}</w:pPr>{run(text, font, size, bold)}</w:p>"
    )


def title(text: str) -> str:
    return para(text, align="center", font=FONT_TITLE, size=44, bold=True, indent=False, space_after=240)


def heading(text: str) -> str:
    return para(text, font=FONT_HEAD, size=28, bold=True, indent=False, space_after=120)


def blank() -> str:
    return '<w:p><w:pPr><w:spacing w:line="560" w:lineRule="exact"/></w:pPr></w:p>'


def table(rows: list[list[str]], widths: list[int] | None = None) -> str:
    if not rows:
        return ""
    cols = len(rows[0])
    widths = widths or [int(9000 / cols)] * cols
    grid = "".join(f'<w:gridCol w:w="{w}"/>' for w in widths)
    border = "".join(
        f'<w:{side} w:val="single" w:sz="6" w:space="0" w:color="000000"/>'
        for side in ("top", "left", "bottom", "right", "insideH", "insideV")
    )
    out = [
        '<w:tbl><w:tblPr><w:tblW w:w="5000" w:type="pct"/>'
        f"<w:tblBorders>{border}</w:tblBorders>"
        f'<w:tblLayout w:type="fixed"/></w:tblPr><w:tblGrid>{grid}</w:tblGrid>'
    ]
    for r_index, row in enumerate(rows):
        cells = []
        for c_index, cell in enumerate(row):
            w = widths[c_index] if c_index < len(widths) else widths[-1]
            head = r_index == 0
            cells.append(
                f'<w:tc><w:tcPr><w:tcW w:w="{w}" w:type="dxa"/>'
                f'<w:vAlign w:val="center"/></w:tcPr>'
                + para(str(cell), align="center" if head else "both",
                       font=FONT_HEAD if head else FONT_BODY, size=24,
                       bold=head, indent=False, space_after=40)
                + "</w:tc>"
            )
        out.append("<w:tr>" + "".join(cells) + "</w:tr>")
    out.append("</w:tbl>" + blank())
    return "".join(out)


SECT = (
    '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
    '<w:pgMar w:top="1440" w:right="1474" w:bottom="1440" w:left="1587" '
    'w:header="851" w:footer="992" w:gutter="0"/></w:sectPr>'
)

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>"""

RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

DOC_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""

STYLES = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:docDefaults><w:rPrDefault><w:rPr>
<w:rFonts w:ascii="Times New Roman" w:eastAsia="{FONT_BODY}" w:hAnsi="Times New Roman"/>
<w:sz w:val="28"/></w:rPr></w:rPrDefault>
<w:pPrDefault><w:pPr><w:spacing w:line="560" w:lineRule="exact"/></w:pPr></w:pPrDefault>
</w:docDefaults></w:styles>"""


def build_docx(blocks: list[str], out: Path) -> None:
    body = "".join(blocks) + SECT
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", CONTENT_TYPES)
        zf.writestr("_rels/.rels", RELS)
        zf.writestr("word/document.xml", document)
        zf.writestr("word/_rels/document.xml.rels", DOC_RELS)
        zf.writestr("word/styles.xml", STYLES)


# ---------------------------------------------------------------- 模板


def _as_list(val) -> list:
    if val is None:
        return []
    if isinstance(val, str):
        return [val] if val else []
    return list(val)


def tpl_complaint(d: dict) -> list[str]:
    b = [title(d.get("title", "民事起诉状")), blank()]
    for label, key in (("原告", "plaintiff"), ("被告", "defendant")):
        for item in _as_list(d.get(key)):
            b.append(para(f"{label}：{item}", indent=False))
    b.append(para(f"案由：{d.get('cause', '【待补：案由】')}", indent=False))
    b.append(blank())
    b.append(heading("诉讼请求"))
    for i, claim in enumerate(_as_list(d.get("claims")), start=1):
        b.append(para(f"{i}. {claim}"))
    b.append(blank())
    b.append(heading("事实与理由"))
    for p in _as_list(d.get("facts")):
        b.append(para(p))
    b.append(blank())
    b.append(para(f"此致", indent=False))
    b.append(para(d.get("court", "【待补：受理法院】"), indent=False))
    b.append(blank())
    b.append(para(f"具状人：{d.get('signer', '【待补：签名】')}", align="right", indent=False))
    b.append(para(d.get("date", "【待补：日期】"), align="right", indent=False))
    if d.get("attachments"):
        b.append(blank())
        b.append(heading("附件"))
        for a in _as_list(d["attachments"]):
            b.append(para(a, indent=False))
    if d.get("note"):
        b.append(blank())
        b.append(para(d["note"], font=FONT_BODY, size=24, indent=False))
    return b


def tpl_evidence(d: dict) -> list[str]:
    b = [title(d.get("title", "证据目录")), blank()]
    b.append(para(f"案号：{d.get('case_no', '【待补：案号】')}", indent=False))
    b.append(para(f"提交方：{d.get('party', '【待补：原告／被告】')}", indent=False))
    b.append(blank())
    rows = [["序号", "证据名称", "证明内容", "页数", "原件／复印件", "备注"]]
    for i, e in enumerate(d.get("items", []), start=1):
        rows.append([
            str(e.get("no", i)), e.get("name", ""), e.get("purpose", ""),
            str(e.get("pages", "")), e.get("form", ""), e.get("note", ""),
        ])
    b.append(table(rows, widths=[800, 2100, 3200, 800, 1300, 1300]))
    b.append(para(f"提交人：{d.get('signer', '【待补：签名】')}　　日期：{d.get('date', '【待补：日期】')}",
                  align="right", indent=False))
    if d.get("note"):
        b.append(para(d["note"], size=24, indent=False))
    return b


def tpl_risk(d: dict) -> list[str]:
    b = [title(d.get("title", "风险告知书")), blank()]
    b.append(para(f"致：{d.get('client', '【待补：委托人】')}", indent=False))
    b.append(para(f"事项：{d.get('matter', '【待补：委托事项】')}", indent=False))
    b.append(para(f"日期：{d.get('date', '【待补：日期】')}", indent=False))
    b.append(blank())
    b.append(heading("一、我们已了解的情况"))
    for p in _as_list(d.get("known")):
        b.append(para(p))
    b.append(heading("二、主要风险"))
    for item in _as_list(d.get("risks")):
        if isinstance(item, dict):
            b.append(para(f"{item.get('title', '')}　{item.get('body', '')}"))
        else:
            b.append(para(str(item)))
    b.append(heading("三、我们的建议"))
    for p in _as_list(d.get("advice")):
        b.append(para(p))
    b.append(heading("四、需要您确认"))
    b.append(para(d.get("confirm", "上述风险与建议已阅读并理解，是否继续委托由委托人决定。")))
    b.append(blank())
    b.append(para("承办律师：______________　　　　委托人：______________",
                  indent=False))
    b.append(para(d.get("disclaimer",
                        "本告知书基于现有材料作出，不构成对结果的承诺；材料变化时结论可能调整。"),
                  size=24, indent=False))
    return b


def tpl_preservation(d: dict) -> list[str]:
    b = [title(d.get("title", "财产保全申请书")), blank()]
    for label, key in (("申请人", "applicant"), ("被申请人", "respondent")):
        items = _as_list(d.get(key)) or [f"【待补：{label}主体信息】"]
        for item in items:
            b.append(para(f"{label}：{item}", indent=False))
    b.append(blank())
    b.append(heading("申请事项"))
    claims = _as_list(d.get("claims")) or [
        f"请求依法查封、扣押、冻结被申请人名下价值人民币 {d.get('amount', '【待补：保全金额】')} 元的银行存款或相应价值的其他财产。"
    ]
    for i, claim in enumerate(claims, start=1):
        b.append(para(f"{i}. {claim}"))
    b.append(blank())
    b.append(heading("事实与理由"))
    for p in _as_list(d.get("facts")) or ["【待补：基础法律关系与紧迫性事实】"]:
        b.append(para(p))
    b.append(blank())
    b.append(heading("担保与财产线索"))
    b.append(para(f"担保方式：{d.get('security', '【待补：诉责险保函／银行保函／现金担保】')}"))
    clues = _as_list(d.get("clues")) or ["【待补：被申请人银行账户、不动产、股权或车辆线索】"]
    for i, clue in enumerate(clues, start=1):
        b.append(para(f"线索 {i}：{clue}"))
    b.append(blank())
    b.append(para("此致", indent=False))
    b.append(para(d.get("court", "【待补：受理法院】"), indent=False))
    b.append(blank())
    b.append(para(f"申请人：{d.get('signer', '【待补：签名或盖章】')}", align="right", indent=False))
    b.append(para(d.get("date", "【待补：日期】"), align="right", indent=False))
    return b


def tpl_defense(d: dict) -> list[str]:
    b = [title(d.get("title", "民事答辩状")), blank()]
    b.append(para(f"案号：{d.get('case_no', '【待补：案号】')}", indent=False))
    b.append(para(f"案由：{d.get('cause', '【待补：案由】')}", indent=False))
    for item in _as_list(d.get("defendant")) or ["【待补：答辩人主体信息】"]:
        b.append(para(f"答辩人：{item}", indent=False))
    for item in _as_list(d.get("plaintiff")) or ["【待补：被答辩人／原告名称】"]:
        b.append(para(f"被答辩人：{item}", indent=False))
    b.append(blank())
    b.append(heading("答辩请求"))
    for i, req in enumerate(_as_list(d.get("requests")) or ["请求依法驳回原告的全部诉讼请求。"], start=1):
        b.append(para(f"{i}. {req}"))
    b.append(blank())
    b.append(heading("事实与理由"))
    for p in _as_list(d.get("arguments")) or ["【待补：答辩事实与法律依据】"]:
        b.append(para(p))
    b.append(blank())
    b.append(para("此致", indent=False))
    b.append(para(d.get("court", "【待补：受理法院】"), indent=False))
    b.append(blank())
    b.append(para(f"答辩人：{d.get('signer', '【待补：签名或盖章】')}", align="right", indent=False))
    b.append(para(d.get("date", "【待补：日期】"), align="right", indent=False))
    return b


TEMPLATES = {
    "complaint": tpl_complaint,
    "evidence": tpl_evidence,
    "risk": tpl_risk,
    "preservation": tpl_preservation,
    "defense": tpl_defense,
}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="生成 Word 文书")
    ap.add_argument("template", choices=list(TEMPLATES))
    ap.add_argument("--input", required=True, help="JSON 输入")
    ap.add_argument("--out", required=True, help="输出 .docx")
    args = ap.parse_args(argv)

    src = Path(args.input)
    if not src.exists():
        print(f"找不到输入：{src}", file=sys.stderr)
        return 2
    data = json.loads(src.read_text(encoding="utf-8"))
    blocks = TEMPLATES[args.template](data)
    out = Path(args.out)
    build_docx(blocks, out)
    leftovers = sum(blk.count("【待补") for blk in blocks)
    print(f"已生成 {out}（{out.stat().st_size:,} 字节）")
    if leftovers:
        print(f"提示：仍有 {leftovers} 处【待补】占位符，交付前必须替换")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
