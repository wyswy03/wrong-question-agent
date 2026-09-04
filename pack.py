# -*- coding: utf-8 -*-
"""把可分发文件打成 zip，不含个人题库。"""
from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = Path.home() / "Desktop" / "错题本-发给别人.zip"
INCLUDE = [
    "start.bat",
    "server.py",
    "bank.py",
    "README.md",
    "SKILL.md",
    "Dockerfile",
    "Procfile",
    "render.yaml",
    "web/index.html",
    "web/app.js",
    "web/styles.css",
]


def main() -> None:
    if OUT.exists():
        OUT.unlink()
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in INCLUDE:
            src = ROOT / rel
            zf.write(src, arcname="WrongQuestionAgent/" + rel.replace("\\", "/"))
        zf.writestr("WrongQuestionAgent/data/images/.gitkeep", "")
        zf.writestr("WrongQuestionAgent/data/inbox/.gitkeep", "")
    print("已生成：%s" % OUT)


if __name__ == "__main__":
    main()
