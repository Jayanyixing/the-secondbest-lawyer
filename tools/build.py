#!/usr/bin/env python3
"""把技能打包成「任何宿主都能吃」的分发件。

产物（dist/）：
  the-secondbest-lawyer-lite.md   核心规则版，适合上下文小的宿主 / 直接粘贴
  the-secondbest-lawyer-full.md   全模块合并版，适合知识库、长上下文模型
  the-secondbest-lawyer.zip       技能包，适合 WorkBuddy 上传或任意文件夹式安装

无第三方依赖，Python 3.8+。

用法：
    python3 tools/build.py
    python3 tools/build.py --out dist --lite-extra 09-case-operations.md
"""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = ROOT / "the-secondbest-lawyer"
REFS = SKILL_DIR / "references"

# 合并顺序：先入口，再硬规则，再业务模块，最后附录
FULL_ORDER = [
    "SKILL.md",
    "citation.md",
    "data-supply.md",
    "scope.md",
    "00-chief.md",
    "01-legal-research.md",
    "02-civil-litigation.md",
    "03-criminal-defense.md",
    "04-evidence-trial.md",
    "05-contract-counsel.md",
    "06-corporate-due-diligence.md",
    "07-assets-enforcement.md",
    "08-law-firm-tender.md",
    "08a-legal-service-bid.md",
    "09-case-operations.md",
    "10-legal-quality.md",
    "11-client-practice.md",
    "12-standards.md",
    "13-procedure-actions.md",
    "checklist.md",
    "sources.md",
    "case-access.md",
    "case-mcp-setup.md",
    "handoff.md",
    "eval-protocol.md",
    "acceptance-scenarios.md",
]

# 精简版只保留：入口 + 引用铁律 + 范围 + 总闸 + 期限口径
LITE_ORDER = ["SKILL.md", "citation.md", "scope.md", "checklist.md", "09-case-operations.md"]

HEADER = """<!-- 单文件合并版 · 由 tools/build.py 生成，请勿手工编辑 -->
# the-secondbest-lawyer（{variant}版）

> 版本 {version} ｜ 生成 {today} ｜ 无需安装、无需联网、无需外部文件。
> 直接作为系统提示、项目知识或对话开头使用即可。
> 没有 shell 时跳过 `tools/citation_lint.py`，改用文末「交付前总闸」人工检查。
> 仓库：<https://github.com/Jayanyixing/the-secondbest-lawyer>

---

"""


def version() -> str:
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    m = re.search(r"^version:\s*(\S+)", text, re.M)
    return m.group(1) if m else "0"


def strip_frontmatter(text: str) -> str:
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            return parts[2].lstrip("\n")
    return text


def demote(text: str, by: int = 1) -> str:
    """合并进主文档时整体降一级标题，保持层级。代码块内不动。"""
    out, fenced = [], False
    for line in text.splitlines():
        if line.startswith("```"):
            fenced = not fenced
            out.append(line)
            continue
        if not fenced:
            m = re.match(r"^(#{1,5})(\s)", line)
            if m:
                line = "#" * min(len(m.group(1)) + by, 6) + line[len(m.group(1)):]
        out.append(line)
    return "\n".join(out)


def flatten_links(text: str) -> str:
    """单文件版里不能有指向 references/*.md 的相对链接，改成纯文字标注。"""
    return re.sub(r"\[([^\]]+)\]\((?!https?://)([^)]*?\.md)(?:#[^)]*)?\)", r"「\1」", text)


def read(name: str, demote_by: int) -> str:
    path = SKILL_DIR / name if name == "SKILL.md" else REFS / name
    body = strip_frontmatter(path.read_text(encoding="utf-8")).rstrip() + "\n"
    body = flatten_links(body)
    return demote(body, demote_by) if demote_by else body


def build_flat(order: list[str], variant: str) -> str:
    chunks = [HEADER.format(variant=variant, version=version(), today=date.today().isoformat())]
    for name in order:
        body = read(name, demote_by=1)
        if name == "SKILL.md":
            chunks.append(body)
        else:
            title = next((l.lstrip("# ") for l in body.splitlines() if l.startswith("#")), name)
            chunks.append(f"\n---\n\n<!-- 源文件：references/{name} -->\n\n{body}")
    chunks.append(
        "\n---\n\n## 使用提醒\n\n"
        "- 本文件是规则集合，不是内容模板；输出前先过一遍文末总闸。\n"
        "- 案例与法条只引用实际读到的原文，落不到页／段／小节的，一律进「待取正文」。\n"
        "- 交付物开头三行固定：结论／最紧迫／最大缺口。\n"
    )
    return "\n".join(chunks)


def build_zip(out: Path) -> Path:
    target = out / "the-secondbest-lawyer.zip"
    include_dirs = ["the-secondbest-lawyer", "tools", "eval", "data", "templates"]
    include_files = ["README.md", "CHANGELOG.md", "LICENSE", "MAINTENANCE.md"]
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for folder in include_dirs:
            base = ROOT / folder
            for path in sorted(base.rglob("*")):
                if path.is_dir() or "__pycache__" in path.parts or path.suffix == ".pyc":
                    continue
                zf.write(path, path.relative_to(ROOT).as_posix())
        for name in include_files:
            path = ROOT / name
            if path.exists():
                zf.write(path, name)
        zf.writestr(
            "安装说明.txt",
            "the-secondbest-lawyer\n\n"
            "1) 有技能目录的客户端：把 the-secondbest-lawyer/ 放进技能目录。\n"
            "2) WorkBuddy：技能 → 添加技能 → 上传技能，选择本 zip。\n"
            "3) 只能上传单文件：用 dist/the-secondbest-lawyer-full.md。\n"
            "4) 只能粘贴文本：用 dist/the-secondbest-lawyer-lite.md。\n"
            "详见 the-secondbest-lawyer/INSTALL.md。\n",
        )
    return target


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="生成单文件版与技能包")
    ap.add_argument("--out", default="dist", help="输出目录，默认 dist")
    args = ap.parse_args(argv)

    out = (ROOT / args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)

    targets = [
        (LITE_ORDER, "精简", out / "the-secondbest-lawyer-lite.md"),
        (FULL_ORDER, "完整", out / "the-secondbest-lawyer-full.md"),
    ]
    for order, variant, path in targets:
        text = build_flat(order, variant)
        path.write_text(text, encoding="utf-8")
        print(f"{path.relative_to(ROOT)}  {len(text):,} 字")

    zpath = build_zip(out)
    print(f"{zpath.relative_to(ROOT)}  {zpath.stat().st_size:,} 字节")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
