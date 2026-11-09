#!/usr/bin/env python3
"""十个回归探针：build.py / lawdiff.py / test_tender.py 的历史缺陷。

每个探针都在当前 HEAD 上通过；在修复前的基线（9e9e5de^）上应全部失败。
探针只读仓库，临时文件都写进 TemporaryDirectory，跑完不留痕。
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

import build  # noqa: E402
import lawdiff  # noqa: E402

CASES: list[tuple[str, object]] = []


class Skip(Exception):
    """安装布局下不适用（例如 build.py 的仓库相对路径）。"""


def case(name: str):
    def deco(fn):
        CASES.append((name, fn))
        return fn

    return deco


def run(args: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, *args], capture_output=True, text=True,
        encoding="utf-8", cwd=ROOT, **kw,
    )


# ---------------------------------------------------------------- build.py


@case("build：zip 不打包 cards.full.* 与 SQLite 事务文件")
def _() -> None:
    old_root = build.ROOT
    tmp = Path(tempfile.mkdtemp(prefix="probe-build-zip-"))
    build.ROOT = tmp
    try:
        for folder in ("the-secondbest-lawyer", "tools", "eval", "data", "templates"):
            (tmp / folder).mkdir()
        (tmp / "data" / "cards.sqlite").write_text("masked", "utf-8")
        (tmp / "data" / "cards.full.sqlite").write_text("secret", "utf-8")
        (tmp / "data" / "cards.full.json").write_text("{}", "utf-8")
        for suffix in ("-wal", "-shm", "-journal"):
            (tmp / "data" / f"cards.sqlite{suffix}").write_text("txn", "utf-8")
        (tmp / "dist").mkdir()
        target = build.build_zip(tmp / "dist")
        names = zipfile.ZipFile(target).namelist()
        bad = [n for n in names if "cards.full" in n or n.endswith(("-wal", "-shm", "-journal"))]
        assert not bad, f"分发包带了敏感文件：{bad}"
        assert "data/cards.sqlite" in names, "脱敏库应正常入包"
    finally:
        build.ROOT = old_root
        shutil.rmtree(tmp, ignore_errors=True)


@case("build：--lite-extra 参数可用")
def _() -> None:
    if not (build.SKILL_DIR / "references").is_dir():
        raise Skip("安装布局没有 the-secondbest-lawyer/references，本探针只适用仓库")
    old_check, old_zip = build.check_readme_numbers, build.build_zip
    build.check_readme_numbers = lambda: []

    def fake_zip(out: Path) -> Path:
        p = out / "dummy.zip"
        p.write_bytes(b"")
        return p

    build.build_zip = fake_zip
    try:
        with tempfile.TemporaryDirectory(prefix="probe-build-lite-") as td:
            try:
                rc = build.main(["--out", td, "--lite-extra", "09-case-operations.md"])
            except SystemExit as exc:  # 旧版 argparse 直接退出
                rc = exc.code
            assert rc == 0, f"main 返回 {rc}（旧版会把 --lite-extra 当未知参数）"
            assert (Path(td) / "the-secondbest-lawyer-lite.md").is_file()
    finally:
        build.check_readme_numbers, build.build_zip = old_check, old_zip


@case("build：测试部分失败时 check_readme_numbers 必须报错")
def _() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="probe-build-readme-"))
    old_root, old_run = build.ROOT, build.subprocess.run
    build.ROOT = tmp
    (tmp / "tools").mkdir()
    (tmp / "README.md").write_text(
        "# probe\n\n引用校验器（1 条规则）\n\n155/155 条断言\n", "utf-8",
    )
    (tmp / "tools" / "citation_lint.py").write_text('rep.error("R1", "x")\n', "utf-8")
    build.subprocess.run = lambda *a, **k: SimpleNamespace(
        returncode=1, stdout="结果：155/160 条断言通过\n",
    )
    try:
        problems = build.check_readme_numbers()
    finally:
        build.ROOT, build.subprocess.run = old_root, old_run
        shutil.rmtree(tmp, ignore_errors=True)
    assert problems, "测试退出码非 0 且 155/160 时，构建不应放行"
    assert any("未通过" in p for p in problems), problems


@case("build：demote 识别四反引号/缩进围栏，且不再留死变量")
def _() -> None:
    src = (
        "````markdown\n```python\n# 注释\n```\n````\n"
        "## 标题\n"
        "  ```\n# 缩进围栏内\n  ```\n"
    )
    out = build.demote(src)
    assert "## 注释" not in out, "四反引号内的 # 注释被误降级"
    assert "## 缩进围栏内" not in out, "缩进围栏内的 # 被误降级"
    assert "### 标题" in out, "围栏外的 ## 标题应降为 ###"
    assert "title = next((" not in (TOOLS / "build.py").read_text(encoding="utf-8")


# ---------------------------------------------------------------- lawdiff.py


@case("lawdiff：同条号重复时保留正文最长的一条")
def _() -> None:
    long_body = "这是第一条的完整正文，内容足够长，用于验证去重时保留最长的一条。"
    text = f"第一条 {long_body}\n第二条 第二条正文。\n第一条 短。\n"
    with tempfile.TemporaryDirectory(prefix="probe-lawdiff-dup-") as td:
        p = Path(td) / "a.txt"
        p.write_text(text, "utf-8")
        book, _ = lawdiff.load(p)
    assert book.get("第一条") == lawdiff.norm(long_body), f"实际：{book.get('第一条')!r}"


@case("lawdiff：--only 9 能命中 第九条")
def _() -> None:
    body = "第一条 甲。\n第九条 这是第九条正文。\n第一百条 这是第一百条正文。\n"
    with tempfile.TemporaryDirectory(prefix="probe-lawdiff-only-") as td:
        a, b = Path(td) / "a.txt", Path(td) / "b.txt"
        a.write_text(body, "utf-8")
        b.write_text(body, "utf-8")
        r = run([str(TOOLS / "lawdiff.py"), str(a), str(b), "--only", "9"])
    assert "A（官方）：1 条" in r.stdout, r.stdout
    assert r.returncode == 0, r.stdout + r.stderr


@case("lawdiff：抽查后最大条号同步收窄")
def _() -> None:
    body = "第一条 甲。\n第九条 这是第九条正文。\n第一百条 这是第一百条正文。\n"
    with tempfile.TemporaryDirectory(prefix="probe-lawdiff-max-") as td:
        a, b = Path(td) / "a.txt", Path(td) / "b.txt"
        a.write_text(body, "utf-8")
        b.write_text(body, "utf-8")
        r = run([str(TOOLS / "lawdiff.py"), str(a), str(b), "--only", "9"])
    assert "A（官方）：1 条，最大 9" in r.stdout, r.stdout


@case("lawdiff：HEAD_TAIL 识别 零/千/两/数字 与长章名")
def _() -> None:
    assert lawdiff.is_heading_glue(
        "本法自公布之日起施行第一百零一章", "本法自公布之日起施行",
    ), "含「零」的章名未识别"
    assert lawdiff.is_heading_glue(
        "正文第一章一二三四五六七八九十十一十二十三", "正文",
    ), "超过 12 字的章名未识别"


# ---------------------------------------------------------------- test_tender.py


@case("test_tender：C6 用例断言退出码为 1")
def _() -> None:
    src = (TOOLS / "test_tender.py").read_text(encoding="utf-8")
    assert '"C6" in out and code == 1' in src, "C6 只断言输出、没断言退出码"


@case("test_tender：临时目录清理 + 子进程 UTF-8")
def _() -> None:
    src = (TOOLS / "test_tender.py").read_text(encoding="utf-8")
    assert 'encoding="utf-8"' in src, "subprocess.run 未显式指定 UTF-8"
    assert "shutil.rmtree(tmp" in src, "mkdtemp 创建的目录未清理"
    with tempfile.TemporaryDirectory(prefix="probe-tender-tmp-") as td:
        env = os.environ.copy()
        env["TMPDIR"] = td + os.sep
        r = subprocess.run(
            [sys.executable, str(TOOLS / "test_tender.py")],
            capture_output=True, text=True, encoding="utf-8", cwd=ROOT, env=env,
        )
        leftovers = list(Path(td).glob("tender-test-*"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert not leftovers, f"临时目录残留：{leftovers}"


def main() -> int:
    failed = skipped = 0
    for name, fn in CASES:
        try:
            fn()
        except Skip as exc:
            skipped += 1
            print(f"[跳过] {name}\n       {exc}")
        except Exception as exc:  # noqa: BLE001 - 探针要把断言失败都汇总
            failed += 1
            print(f"[失败] {name}\n       {exc}")
        else:
            print(f"[通过] {name}")
    tail = f"，{skipped} 跳过" if skipped else ""
    print(f"结果：{len(CASES) - failed - skipped}/{len(CASES)} 通过{tail}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
