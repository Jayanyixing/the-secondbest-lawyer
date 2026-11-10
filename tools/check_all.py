#!/usr/bin/env python3
"""一键全量门禁：单测、边界探针、评测集、数据完整性、构建与防泄露。

用法：
    python3 tools/check_all.py          # 全量（含试构建与包扫描）
    python3 tools/check_all.py --fast   # 供 pre-push 用：跳过试构建与数据校验

退出码：0 全部通过；1 有失败。零第三方依赖，Python 3.8+。
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
DIST_ZIP = ROOT / "dist" / "the-secondbest-lawyer.zip"
EXPECTED_EVAL_CASES = 12

SENSITIVE_NAME_RE = re.compile(
    r"cards\.full|-(?:wal|shm|journal)$|(?:^|/)credits\.json$|(?:^|/)sealed/|BULK-GENERATION-PROMPT",
    re.I,
)
# 真实案号：年份 + 法院代字 + 案件类型 + 数字号；数字号里带 X/×/＊/* 就匹配不上，即视为已脱敏。
CASE_NO_RE = re.compile(
    r"[（(〔\[]\s*(?:19|20)\d{2}\s*[）)〕\]]\s*[\u4e00-\u9fa5]{0,8}\d{0,8}\s*"
    r"(?:民初|民终|民申|民再|民特|民辖|民撤|民监|刑初|刑终|刑申|刑更|行初|行终|行申|"
    r"执异|执复|执恢|执保|执监|执|商初|知民初|知民终|知行初|破申|破|劳仲|仲裁|赔)\s*\d+\s*号"
    # 仲裁：京朝劳人仲字［2022］第20XXX号
    r"|[\u4e00-\u9fa5]{0,10}仲[\u4e00-\u9fa5]{0,3}字?\s*[［\[（(〔]\s*(?:19|20)\d{2}\s*[］\]）)〕]\s*第?\s*\d+\s*号"
)
MASK_RE = re.compile(r"[XxＸｘ×＊*]")
# README 约定：指导案例、典型案例、公报案例、入库编号属于「来源编号」，不要求遮罩。
PUBLIC_SOURCE_MARKERS = ("指导案例", "指导性案例", "典型案例", "参考案例", "公报", "入库编号")
SENSITIVE_PARTY_RE = re.compile(
    r"侯树启|张剑伦|崔洪波|高冬生|中人公司|广东中人|煜金桥|金都园林|玉桥街道|中外运"
)


@dataclass
class Result:
    name: str
    ok: bool
    seconds: float
    detail: str = ""
    skipped: bool = False


def tail(text: str, limit: int = 1200) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else "…" + text[-limit:]


def run_script(
    name: str,
    path: Path,
    pattern: str | None = None,
    validator=None,
    timeout: int = 900,
    args: list[str] | None = None,
) -> Result:
    started = time.perf_counter()
    try:
        proc = subprocess.run(
            [sys.executable, str(path), *(args or [])],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return Result(name, False, time.perf_counter() - started, f"超时（>{timeout}s）")
    except OSError as exc:
        return Result(name, False, time.perf_counter() - started, f"无法执行：{exc}")

    elapsed = time.perf_counter() - started
    output = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        return Result(name, False, elapsed, f"退出码 {proc.returncode}\n{tail(output)}")
    if pattern is None:
        return Result(name, True, elapsed, "通过")

    match = re.search(pattern, output)
    if not match:
        return Result(name, False, elapsed, f"输出缺少统计行 /{pattern}/\n{tail(output)}")
    if validator is not None and not validator(match):
        return Result(name, False, elapsed, f"统计不达标：{match.group(0)}\n{tail(output)}")
    return Result(name, True, elapsed, match.group(0))


def counts_equal(match: re.Match) -> bool:
    return int(match.group(1)) == int(match.group(2)) and int(match.group(2)) > 0


def eval_ok(match: re.Match) -> bool:
    return (
        int(match.group(1)) == EXPECTED_EVAL_CASES
        and int(match.group(2)) == EXPECTED_EVAL_CASES
    )


def verify_ok(match: re.Match) -> bool:
    same, missing, changed = (int(match.group(i)) for i in (1, 2, 3))
    return same > 0 and missing == 0 and changed == 0


def bad_name(name: str) -> bool:
    return bool(SENSITIVE_NAME_RE.search(name.replace("\\", "/")))


def scan_zip(path: Path) -> list[str]:
    """扫描分发包：敏感文件名 + 卡片库里的未脱敏案号。返回问题列表。"""
    problems: list[str] = []
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            for name in names:
                if bad_name(name):
                    problems.append(f"包含敏感条目：{name}")

            card_entries = [
                n for n in names
                if n in {"data/cards.sqlite", "data/cards.json"}
            ]
            if not card_entries:
                problems.append("包内找不到 data/cards.sqlite 或 data/cards.json，无法核验卡片脱敏")
            for name in card_entries:
                data = zf.read(name)
                if name.endswith(".sqlite"):
                    problems.extend(_scan_sqlite_bytes(name, data))
                else:
                    problems.extend(_scan_json_bytes(name, data))
    except (OSError, zipfile.BadZipFile) as exc:
        problems.append(f"无法读取 {path.name}：{exc}")
    return problems


def _case_no_problems(label: str, text: str) -> list[str]:
    # 只拦「真实案号」；公报/指导/典型案例的来源编号按 README 约定可保留。
    # 豁免按「每个命中」判断（命中本身或紧邻其前 16 字含来源标记），
    # 不能因为同一字段里提到「典型案例」就把整段的真实案号一起放过。
    text = text or ""
    out: list[str] = []
    for match in CASE_NO_RE.finditer(text):
        raw = match.group(0)
        ctx = text[max(0, match.start() - 16):match.end()]
        if any(marker in ctx for marker in PUBLIC_SOURCE_MARKERS):
            continue
        if not MASK_RE.search(raw):
            out.append(f"{label} 出现未脱敏案号：{raw}")
    for match in SENSITIVE_PARTY_RE.finditer(text):
        out.append(f"{label} 出现未脱敏主体名称：{match.group(0)}")
    return out


def _scan_sqlite_bytes(name: str, data: bytes) -> list[str]:
    problems: list[str] = []
    with tempfile.TemporaryDirectory(prefix="tsl-card-scan-") as tmp:
        db = Path(tmp) / "cards.sqlite"
        db.write_bytes(data)
        try:
            conn = sqlite3.connect(db)
            tables = [
                r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                )
            ]
            for table in tables:
                if table.startswith("sqlite_"):
                    continue
                quoted = '"' + table.replace('"', '""') + '"'
                try:
                    rows = conn.execute(f"SELECT * FROM {quoted}").fetchall()
                except sqlite3.DatabaseError:
                    continue
                for row in rows:
                    for value in row:
                        if isinstance(value, str):
                            problems.extend(_case_no_problems(f"{name}:{table}", value))
            conn.close()
        except sqlite3.DatabaseError as exc:
            problems.append(f"{name} 不是可读的 SQLite：{exc}")
    return problems


def _scan_json_bytes(name: str, data: bytes) -> list[str]:
    problems: list[str] = []
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [f"{name} 无法解析：{exc}"]

    def walk(value, where: str) -> None:
        if isinstance(value, str):
            problems.extend(_case_no_problems(where, value))
        elif isinstance(value, dict):
            for key, child in value.items():
                walk(child, f"{where}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{where}[{index}]")

    walk(payload, name)
    return problems


def check_repo_dist(fast: bool) -> list[Result]:
    started = time.perf_counter()
    if not DIST_ZIP.is_file():
        if fast:
            return [Result("仓库分发包扫描", True, time.perf_counter() - started,
                           "dist/ 不存在，fast 模式跳过", skipped=True)]
        return [Result("仓库分发包扫描", False, time.perf_counter() - started,
                       "dist/the-secondbest-lawyer.zip 不存在；先运行 python3 tools/build.py")]
    problems = scan_zip(DIST_ZIP)
    elapsed = time.perf_counter() - started
    if problems:
        return [Result("仓库分发包扫描", False, elapsed, "\n".join(problems[:8]))]
    return [Result("仓库分发包扫描", True, elapsed, "无 cards.full / WAL / SHM / journal / credits / sealed / 未脱敏案号")]


def check_tracked(fast: bool) -> Result:
    started = time.perf_counter()
    proc = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True
    )
    if proc.returncode != 0:
        if fast:
            return Result("跟踪文件敏感名扫描", True, time.perf_counter() - started,
                          "不在 Git 工作树内，fast 模式跳过", skipped=True)
        return Result("跟踪文件敏感名扫描", False, time.perf_counter() - started,
                      "git ls-files 失败；无法核验受跟踪文件")
    names = [n for n in proc.stdout.decode("utf-8", "replace").split("\0") if n]
    bad = [n for n in names if bad_name(n)]
    content_problems: list[str] = []
    for n in names:
        if n == "tools/check_all.py":
            continue
        p = ROOT / n
        if not p.is_file() or p.suffix in {".sqlite", ".zip", ".pdf", ".docx"}:
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:
            continue
        content_problems.extend(_case_no_problems(n, text))
    elapsed = time.perf_counter() - started
    if bad or content_problems:
        details = []
        if bad:
            details.append("受跟踪的敏感文件：\n" + "\n".join(bad[:8]))
        if content_problems:
            details.append("受跟踪文件存在未脱敏内容：\n" + "\n".join(content_problems[:8]))
        return Result("跟踪文件敏感名与脱敏扫描", False, elapsed, "\n".join(details))
    return Result("跟踪文件敏感名与脱敏扫描", True, elapsed, f"{len(names)} 个受跟踪文件，无敏感名与未脱敏案号")


def check_build() -> Result:
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="tsl-gate-") as tmp:
        out = Path(tmp) / "dist"
        proc = subprocess.run(
            [sys.executable, str(TOOLS / "build.py"), "--out", str(out)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=900,
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0:
            return Result("试构建与临时包扫描", False, time.perf_counter() - started,
                          f"build.py 退出码 {proc.returncode}\n{tail(output)}")
        target = out / "the-secondbest-lawyer.zip"
        if not target.is_file():
            return Result("试构建与临时包扫描", False, time.perf_counter() - started,
                          "build.py 未生成 zip")
        problems = scan_zip(target)
        elapsed = time.perf_counter() - started
        if problems:
            return Result("试构建与临时包扫描", False, elapsed, "\n".join(problems[:8]))
        return Result("试构建与临时包扫描", True, elapsed,
                      f"{target.stat().st_size:,} 字节；敏感条目 0；卡片案号已脱敏")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="一键全量门禁")
    ap.add_argument("--fast", action="store_true", help="跳过试构建与数据校验，供 pre-push 使用")
    args = ap.parse_args(argv)

    results: list[Result] = []
    print("=== the-secondbest-lawyer 门禁 ===")
    if args.fast:
        print("模式：fast（核心测试 / 探针 / 评测 / 敏感扫描）")

    core = [
        ("引用校验自测", "test_citation_lint.py",
         r"结果：(\d+)/(\d+) 条断言通过", counts_equal),
        ("法条库自测", "test_lawdb.py", r"结果：(\d+)/(\d+) 通过", counts_equal),
        ("法条比对自测", "test_lawdiff.py", r"结果：(\d+)/(\d+) 通过", counts_equal),
        ("投标工具自测", "test_tender.py", r"结果：(\d+)/(\d+) 通过", counts_equal),
    ]
    for name, script, pattern, validator in core:
        results.append(run_script(name, TOOLS / script, pattern, validator))

    tests_dir = ROOT / "tests"
    if tests_dir.is_dir():
        probe_files = sorted(tests_dir.glob("test_*.py"))
        if not probe_files:
            results.append(Result("专项边界探针", True, 0.0, "tests/ 下无 test_*.py", skipped=True))
        for script in probe_files:
            results.append(run_script(f"探针 {script.name}", script))
    else:
        results.append(Result("专项边界探针", True, 0.0,
                              "当前分发包不含 tests/，按设计跳过", skipped=True))

    results.append(run_script(
        "评测集 12 案判别力", TOOLS / "eval_cases.py",
        r"判别力：(\d+)/(\d+) 个案例", eval_ok,
    ))

    if not args.fast:
        results.append(run_script(
            "法规库哈希完整性", TOOLS / "lawdb.py",
            r"一致性：一致 (\d+)／文件缺失 (\d+)／内容变更 (\d+)", verify_ok,
            args=["verify"],
        ))
        if (TOOLS / "retrieval_check.py").is_file():
            results.append(run_script(
                "卡片检索回归", TOOLS / "retrieval_check.py",
                r"回归：(\d+)/(\d+) 通过", counts_equal,
            ))
        else:
            results.append(Result("卡片检索回归", True, 0.0,
                                  "retrieval_check.py 不存在，跳过", skipped=True))
        if (TOOLS / "card_health.py").is_file():
            results.append(run_script(
                "卡片库体检", TOOLS / "card_health.py",
                r"规则卡 (\d+) 张：条号与引文一致 (\d+) 张",
            ))
        results.append(check_build())

    results.extend(check_repo_dist(args.fast))
    results.append(check_tracked(args.fast))

    for result in results:
        if result.skipped:
            status = "SKIP"
        else:
            status = "PASS" if result.ok else "FAIL"
        detail = f"  {result.detail.splitlines()[0]}" if result.detail else ""
        print(f"[{status}] {result.name}  {result.seconds:.1f}s{detail}")
        if not result.ok and result.detail:
            for line in result.detail.splitlines()[1:]:
                print(f"       {line}")

    passed = sum(1 for r in results if r.ok and not r.skipped)
    skipped = sum(1 for r in results if r.skipped)
    failed = sum(1 for r in results if not r.ok and not r.skipped)
    total_seconds = sum(r.seconds for r in results)
    print(f"\n结果：通过 {passed}／失败 {failed}／跳过 {skipped}，"
          f"总耗时 {total_seconds:.1f}s")
    if failed:
        print("失败项：" + "、".join(r.name for r in results if not r.ok and not r.skipped))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
