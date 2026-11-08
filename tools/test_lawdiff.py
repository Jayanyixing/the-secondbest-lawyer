#!/usr/bin/env python3
"""lawdiff 回归：标题粘连不算正文差异，真差异要报出来。

用法：python3 tools/test_lawdiff.py
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAWDIFF = HERE / "lawdiff.py"

OFFICIAL = """中华人民共和国某某法

第一条 为了规范某某活动，制定本法。
第二条 本法适用于中华人民共和国境内的某某活动。
第三条 某某活动应当遵循合法、诚信原则。
"""

# 库内整理件：条文后粘着 markdown 目录标题，这是 LawRefBook 整理件的常见形态
LOCAL_GLUE = """# 中华人民共和国某某法

## 第一章 总则

第一条 为了规范某某活动，制定本法。###第二节 监督管理

第二条 本法适用于中华人民共和国境内的某某活动。

第三条 某某活动应当遵循合法、诚信原则。####附则
"""

# 官方件那一侧粘着分编标题（flk 官方 Word 的形态）
OFFICIAL_TAIL = OFFICIAL.replace("第三条 某某活动应当遵循合法、诚信原则。",
                                 "第三条 某某活动应当遵循合法、诚信原则。第二分编 监督管理")

# 真差异：第二条少了一个限定语
LOCAL_DIFF = """# 中华人民共和国某某法

第一条 为了规范某某活动，制定本法。
第二条 本法适用于境内的某某活动。
第三条 某某活动应当遵循合法、诚信原则。
"""


def run(official: str, local: str, name: str) -> tuple[int, str]:
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "official.txt").write_text(official, encoding="utf-8")
        (d / "local.md").write_text(local, encoding="utf-8")
        p = subprocess.run(
            [sys.executable, str(LAWDIFF), str(d / "official.txt"), str(d / "local.md")],
            capture_output=True, text=True,
        )
        return p.returncode, p.stdout + p.stderr


def main() -> int:
    fails = []

    # 库内 md 的行内标题在解析阶段就被剥掉，应直接判完全一致
    code, out = run(OFFICIAL, LOCAL_GLUE, "glue-md")
    if code != 0:
        fails.append(f"库内行内标题应判无实质差异，实际退出码 {code}")
    if "完全一致" not in out:
        fails.append(f"库内行内标题未被剥离：\n{out}")

    # 官方件末尾的分编标题算「标题粘连」，不算正文差异
    code, out = run(OFFICIAL_TAIL, LOCAL_GLUE, "glue-official")
    if code != 0:
        fails.append(f"官方件末尾目录标题应判无实质差异，实际退出码 {code}")
    if "标题粘连 1" not in out:
        fails.append(f"未把官方件末尾目录标题识别为标题粘连：\n{out}")

    code, out = run(OFFICIAL, LOCAL_DIFF, "diff")
    if code != 1:
        fails.append(f"真差异应退出码 1，实际 {code}")
    if "内容不一致：1 条" not in out:
        fails.append(f"真差异条数不对：\n{out}")
    if "标题粘连 0" not in out:
        fails.append("真差异被误判为标题粘连")

    for f in fails:
        print(f"[失败] {f}")
    if fails:
        print(f"结果：{len(fails)} 项失败")
        return 1
    print("结果：5/5 通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
