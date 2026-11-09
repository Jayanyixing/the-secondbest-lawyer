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


def run_ledger_strict(body: str, ledger: dict) -> tuple[int, str]:
    import json

    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d) / "doc.md"
        l = pathlib.Path(d) / "ledger.json"
        p.write_text(body, encoding="utf-8")
        l.write_text(json.dumps(ledger, ensure_ascii=False), encoding="utf-8")
        r = subprocess.run(
            [sys.executable, str(LINT), str(p), "--ledger", str(l), "--strict"],
            capture_output=True, text=True,
        )
        return r.returncode, r.stdout + r.stderr


def run_file(path, *extra: str) -> tuple[int, str]:
    r = subprocess.run(
        [sys.executable, str(LINT), str(path), *extra], capture_output=True, text=True
    )
    return r.returncode, r.stdout + r.stderr


FIXTURES = HERE.parent / "tests" / "fixtures"


def run_fixture(name: str, ledger: str | None = None, *extra: str) -> tuple[int, str]:
    doc = FIXTURES / name
    args = [sys.executable, str(LINT), str(doc)]
    if ledger:
        args += ["--ledger", str(FIXTURES / ledger)]
    args += list(extra)
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

    # R16 fixture：未确认 + 缺适用时点 + 已用于结论 → 错误与警告同时出现；已废止只警告
    code, out = run_fixture("norm-status-conflict.md", "norm-status-conflict.json")
    _chk(code == 1, f"效力未确认却用于结论应退出 1，实际 {code}", fails)
    _chk("N-01 的规范效力为「未确认」" in out, "R16 未报「未确认却用于结论」错误", fails)
    _chk("N-01 缺字段：适用时点" in out, "R16 缺字段警告被错误分支屏蔽", fails)
    _chk("N-02 的规范效力为「未确认」" not in out, "已废止被误判为未确认", fails)
    _chk("N-02 缺字段：适用时点" in out, "已废止但缺适用时点应给警告", fails)

    # 严格模式：用于结论但缺「规范效力」→ 错误；普通模式只警告
    code, out = run_ledger(body, old)
    _chk(code == 0, f"普通模式下旧底稿缺效力应只警告，实际退出码 {code}", fails)
    code, out = run_ledger_strict(body, old)
    _chk(code == 1 and "严格模式" in out, f"严格模式缺效力却用于结论应报错，实际 {code}", fails)

    # R17 否定只在同一分句内生效
    code, out = run_file(d / "offline-draft-negative.md", "--mode", "offline")
    _chk(code == 0, f"「不是可交付稿」「无一条已核实」应通过，实际 {code}", fails)
    code, out = run_file(d / "offline-draft-contrast.md", "--mode", "offline")
    _chk(code == 1 and "[R17]" in out, f"「未经联网回读，但引用均已核实」应报 R17，实际 {code}", fails)
    _chk("已核实" in out, "R17 未指出被肯定的「已核实」", fails)

    # normalize_norm_status 单元（对应 78bb91a 引入的归一逻辑）
    import citation_lint as cl2

    _chk(cl2.normalize_norm_status(None) == "unknown", "空值应为 unknown", fails)
    _chk(cl2.normalize_norm_status("") == "unknown", "空串应为 unknown", fails)
    for zh, en in [("现行有效", "current"), ("已修改", "amended"), ("已废止", "repealed"),
                   ("未施行", "not_effective"), ("未确认", "unconfirmed")]:
        _chk(cl2.normalize_norm_status(zh) == en, f"词表内「{zh}」应归为 {en}", fails)
    _chk(cl2.normalize_norm_status("有效") == "unconfirmed", "词表外「有效」应按未确认", fails)
    for en in ("current", "amended", "repealed", "not_effective", "unconfirmed", "unknown"):
        _chk(cl2.normalize_norm_status(en) == en, f"英文值 {en} 应原样保留", fails)

    # 官方复核的否定写法：一律按未核，不得报 R18
    for raw in ("未核（仅商业库或转载）", "未经核实", "未能核实", "尚未核"):
        _chk(cl2.normalize_check(raw) == "unverified", f"「{raw}」应归一为 unverified", fails)
    _chk(cl2.normalize_check("已核（与官方原文一致）") == "verified", "正写「已核」仍应 verified", fails)
    code, out = run_fixture("commercial-unverified-variants.md", "commercial-unverified-variants.json")
    _chk(code == 0, f"否定写法不应阻断交付，实际 {code}", fails)
    _chk("[R18]" not in out, "否定写法不得触发 R18", fails)
    _chk("官方复核未核 4 条" in out, "否定写法应汇总为「官方复核未核 4 条」", fails)

    # 官方复核默认拒绝：词表外带「核」一律按未核，不得报 R18
    six = ["未经官方核实", "尚未经官方核对", "未能与官方原文核对", "未完成核对", "核对中", "待核"]
    for v in six:
        _chk(cl2.normalize_check(v) == "unverified", f"「{v}」应归一为 unverified", fails)
        _chk(not cl2.claims_official_verified(v), f"「{v}」不得被当作已核声称", fails)
    _chk(cl2.normalize_check("基本核实") == "unverified", "词表外「基本核实」按未核处理", fails)
    _chk(cl2.claims_official_verified("基本核实"), "「基本核实」仍算已核声称，商业库应报 R18", fails)
    code, out = run_fixture("check-vocab-outliers.md", "check-vocab-outliers.json")
    _chk(code == 0, f"词表外写法不应阻断，实际 {code}", fails)
    _chk("[R18]" not in out, "词表外写法不得触发 R18", fails)
    _chk("不在词表内，已按未核处理" in out, "缺「按未核处理」提示", fails)
    code, out = run_fixture("commercial-verified-outofvocab.md", "commercial-verified-outofvocab.json")
    _chk(code == 1 and "[R18]" in out, f"商业库+「基本核实」应报 R18，实际 {code}", fails)

    # 商业库 + 不含「核」字的肯定写法：R18 必须触发，并进未核汇总
    nonnuclear = ["已比对一致", "与官方原文一致", "已验证", "已确认", "已查证", "一致"]
    for v in nonnuclear:
        _chk(cl2.normalize_check(v) == "unverified", f"「{v}」应归一为 unverified", fails)
        _chk(not cl2.check_allowed_for_channel(v), f"「{v}」不应被非官方渠道接受", fails)
    _chk(cl2.check_allowed_for_channel("未核（仅商业库或转载）"), "未核词表应被非官方渠道接受", fails)
    _chk(cl2.check_allowed_for_channel(""), "留空应被接受", fails)
    code, out = run_fixture("commercial-affirmative-nonuclear.md", "commercial-affirmative-nonuclear.json")
    _chk(code == 1, f"商业库 + 肯定写法应阻断，实际 {code}", fails)
    _chk(out.count("[R18]") == 6, f"六种写法应各报 R18，实际 {out.count('[R18]')}", fails)
    _chk("官方复核未核 6 条" in out, "六种写法应进「未核 6 条」汇总", fails)
    _chk("不在词表内" in out, "缺词表外提示", fails)

    # 对抗样例：每种写法都要被拦住（详见 tests/fixtures/EXPECTATIONS.md）
    code, out = run_fixture("commercial-verified-variants.md", "commercial-verified-variants.json")
    _chk(code == 1 and out.count("[R18]") == 3, f"三种「已核」变体应各报 R18，实际 {out.count('[R18]')}", fails)
    code, out = run_fixture("boilerplate-quote.md", "boilerplate-quote.json")
    _chk(code == 1 and "[R13]" in out, f"套话摘录应报 R13，实际 {code}", fails)
    code, out = run_fixture("reused-quote.md", "reused-quote.json")
    _chk(code == 0 and "[R14]" in out, f"摘录复用应警告 R14 且不阻断，实际 {code}", fails)
    code, out = run_fixture("future-reread.md", "future-reread.json")
    _chk(code == 1 and "[R15]" in out, f"未来回读日期应报 R15，实际 {code}", fails)
    code, out = run_fixture("norm-status-out-of-vocab.md", "norm-status-out-of-vocab.json")
    _chk(code == 1 and "未确认" in out, f"词表外效力应按未确认报错，实际 {code}", fails)

    # R14 严格模式升级为错误，普通模式仍为警告
    code, out = run_fixture("reused-quote.md", "reused-quote.json")
    _chk(code == 0 and "[R14]" in out, f"普通模式摘录复用应仅警告，实际 {code}", fails)
    code, out = run_fixture("reused-quote.md", "reused-quote.json", "--strict")
    _chk(code == 1 and "严格模式" in out, f"严格模式摘录复用应报错，实际 {code}", fails)

    # 严格模式 fixture：普通模式通过（仅警告），--strict 报 R16 错误
    code, out = run_fixture("strict-missing-effect.md", "strict-missing-effect.json")
    _chk(code == 0, f"普通模式缺规范效力应通过，实际 {code}", fails)
    _chk("[R16]" in out and "未登记「规范效力」" not in out, "普通模式不应出现严格模式错误", fails)
    code, out = run_fixture("strict-missing-effect.md", "strict-missing-effect.json", "--strict")
    _chk(code == 1, f"严格模式缺规范效力应退出 1，实际 {code}", fails)
    _chk("严格模式" in out, "严格模式未给出 R16 错误文案", fails)

    # R16 内联底稿：只出一条汇总提示，不逐条刷屏
    code, out = run(BODY_TMPL.format(tag="〔N-01〕", id_cell="N-01《劳动合同法》第三十八条"))
    _chk("未登记「规范效力」" in out, "内联底稿缺规范效力未给汇总提示", fails)
    _chk(out.count("未登记「规范效力」") == 1, "内联底稿缺规范效力逐条刷屏", fails)
    _chk(code == 0, f"内联缺规范效力应只提示不阻断，实际退出码 {code}", fails)

    # R18 商业库不得记官方已核
    code, out = run_fixture("commercial-verified.md", "commercial-verified.json")
    _chk(code == 1 and "[R18]" in out, f"商业库写已核应报 R18 且退出 1，实际 {code}", fails)

    if fails:
        for f in fails:
            print("失败：" + f)
        print(f"结果：{len(fails)} 项不通过")
        return 1
    print(f"结果：{_extra[1]}/{_extra[0]} 条断言通过")
    print("口径：每调用一次 _chk() 计一条断言；同一断言换 fixture 再跑算另一条。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
