#!/usr/bin/env python3
"""citation_lint 的内联底稿回归：底稿直接附在文书末尾时，八条编号检查仍要生效。"""
from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
LINT = HERE / "citation_lint.py"

BODY_TMPL = """# 意见书

结论：用人单位未缴社保，劳动者可据第三十八条第三项解除并主张补偿〔{tag}〕。

| 依据 | 摘录 | 回读状态 |
|---|---|---|
| {id_cell} | 未依法为劳动者缴纳社会保险费的 | 摘录来自本地库 |
"""


_extra = [0, 0]  # [断言总数, 通过]


def _chk(cond: bool, msg: str, fails: list[str]) -> None:
    _extra[0] += 1
    if cond:
        _extra[1] += 1
    else:
        fails.append(msg)


def run(text: str) -> tuple[int, str]:
    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d) / "doc.md"
        p.write_text(text, encoding="utf-8")
        r = subprocess.run([sys.executable, str(LINT), str(p)], capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr


def run_ledger(body: str, ledger: dict) -> tuple[int, str]:
    import json

    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d) / "doc.md"
        l = pathlib.Path(d) / "ledger.json"
        p.write_text(body, encoding="utf-8")
        l.write_text(json.dumps(ledger, ensure_ascii=False), encoding="utf-8")
        r = subprocess.run(
            [sys.executable, str(LINT), str(p), "--ledger", str(l)], capture_output=True, text=True
        )
        return r.returncode, r.stdout + r.stderr


def run_file(path, *extra: str) -> tuple[int, str]:
    r = subprocess.run(
        [sys.executable, str(LINT), str(path), *extra], capture_output=True, text=True
    )
    return r.returncode, r.stdout + r.stderr


FIXTURES = HERE.parent / "tests" / "fixtures"


def run_fixture(name: str, ledger: str | None = None) -> tuple[int, str]:
    doc = FIXTURES / name
    args = [sys.executable, str(LINT), str(doc)]
    if ledger:
        args += ["--ledger", str(FIXTURES / ledger)]
    r = subprocess.run(args, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def main() -> int:
    fails = []

    code, out = run(BODY_TMPL.format(tag="〔N-01〕", id_cell="N-01《劳动合同法》第三十八条"))
    _chk(not ("[R8]" in out), "括号编号被误判为不存在", fails)
    _chk(not (code != 0), f"内联底稿应通过，实际退出码 {code}", fails)

    code, out = run(BODY_TMPL.format(tag="N-01", id_cell="N-01《劳动合同法》第三十八条"))
    _chk(not ("[R8]" in out or "[R10]" in out), "裸写编号 N-01 未被识别", fails)

    code, out = run(
        "# 意见\n\n见指导案例190号〔C-01〕。\n\n| 编号 | 摘录 |\n|---|---|\n"
        "| C-01 指导案例190号 | 审查劳动者自营或者新入职单位与原用人单位是否形成竞争关系 |\n"
    )
    _chk(not ("[R1]" in out), "指导案例编号未登记进底稿", fails)

    code, out = run(BODY_TMPL.format(tag="〔N-09〕", id_cell="N-01《劳动合同法》第三十八条"))
    _chk(not ("[R8]" not in out or code == 0), "引用不存在的编号应报 R8 且退出 1", fails)

    # 商业库来源：已回读 + 官方复核未核，必须通过（回读与官方复核分离）
    body = "# 意见〔自查〕\n\n合同自通知到达对方时解除〔N-01〕。\n"
    led = {
        "citations": [
            {
                "id": "N-01",
                "type": "法律",
                "number": "第五百六十五条",
                "channel": "commercial",
                "location": "第 1 页",
                "read_scope": "excerpt",
                "quote": "合同自通知到达对方时解除",
                "reread": "已回读（2026-11-09）",
                "official_check": "unverified",
                "effectiveness": "effective",
                "norm_status": "current",
                "apply_time": "行为时点 2024-03-01；适用版本 民法典",
            }
        ]
    }
    code, out = run_ledger(body, led)
    _chk(not (code != 0 or "[R0] 官方复核未核" not in out), f"商业库已回读应通过并提示官方未核，实际退出码 {code}：{out[-200:]}", fails)

    # 回读日期：只到日，缺日期要提示；「日期待补」算合法写法
    led2 = {"citations": [dict(led["citations"][0])]}
    led2["citations"][0]["reread"] = "已回读"
    code, out = run_ledger(body, led2)
    _chk(not ("缺日期" not in out), "回读缺日期未提示", fails)
    led2["citations"][0]["reread"] = "已回读（日期待补）"
    code, out = run_ledger(body, led2)
    _chk(not ("缺日期" in out), "「日期待补」应被接受", fails)

    # R16：效力未确认却用于结论 → 错误；补齐两字段 → 不再提示
    led3 = {"citations": [dict(led["citations"][0])]}
    code, out = run_ledger(body, led3)
    _chk(not ("R16" in out), "补了效力与时点仍报 R16", fails)
    old = {"citations": [{k: v for k, v in led["citations"][0].items()
                          if k not in ("norm_status", "apply_time")}]}
    code, out = run_ledger(body, old)
    _chk(not ("R16" not in out or code != 0), "旧底稿缺两字段应只警告、不阻断", fails)
    led3["citations"][0]["norm_status"] = "unconfirmed"
    code, out = run_ledger(body, led3)
    _chk(not (code == 0 or "规范效力为「未确认」" not in out), "规范效力未确认用于结论应报错并退出 1", fails)

    # 离线模式：草稿合规，缺〔草稿〕即不合规
    d = HERE.parent / "tests" / "fixtures"
    code, out = run_file(d / "offline-draft.md", "--mode", "offline")
    _chk(not (code != 0 or "离线草稿" not in out or "可交付" in out.replace("不得标「可交付」", "")), f"离线草稿应通过且不提可交付，实际 {code}：{out[-160:]}", fails)
    code, out = run_file(d / "offline-draft-negative.md", "--mode", "offline")
    _chk(not (code != 0), f"否定句（不是可交付／无一条已核实）应通过，实际 {code}：{out[-200:]}", fails)
    code, out = run_file(d / "offline-draft-nomark.md", "--mode", "offline")
    _chk(not (code == 0 or "〔草稿〕" not in out), "离线稿缺〔草稿〕应报错", fails)

    if fails:
        for f in fails:
            print("失败：" + f)
        print(f"结果：{len(fails)} 项不通过")
        return 1
    print(f"结果：{_extra[1]}/{_extra[0]} 通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
