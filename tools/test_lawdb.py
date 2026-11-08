#!/usr/bin/env python3
"""lawdb 条号归一化回归：阿拉伯数字、带「条」、带「之一」都要能查。"""
from __future__ import annotations

import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lawdb import normalize_article_no  # noqa: E402

CASES = {
    "38": "第三十八条",
    "38条": "第三十八条",
    "第38条": "第三十八条",
    "第三十八条": "第三十八条",
    "105": "第一百零五条",
    "1260": "第一千二百六十条",
    "133之一": "第一百三十三条之一",
    "第133条之一": "第一百三十三条之一",
}


def main() -> int:
    fails = [f"{k} → {normalize_article_no(k)}（应 {v}）" for k, v in CASES.items() if normalize_article_no(k) != v]

    r = subprocess.run(
        [sys.executable, str(HERE / "lawdb.py"), "article", "中华人民共和国民法典", "585"],
        capture_output=True, text=True,
    )
    if "第五百八十五条" not in r.stdout or r.returncode != 0:
        fails.append("CLI 用阿拉伯数字 585 查不到民法典违约金条")

    if fails:
        for f in fails:
            print("失败：" + f)
        print(f"结果：{len(fails)} 项不通过")
        return 1
    print("结果：9/9 通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
