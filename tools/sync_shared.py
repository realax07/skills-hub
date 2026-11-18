#!/usr/bin/env python3
"""Синхронизация общего кода скиллов по tools/shared.conf (копия <- источник).

  python3 tools/sync_shared.py          скопировать источники в копии
  python3 tools/sync_shared.py --check  только проверить; код 1, если копия отличается или нет файла
"""
import argparse
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CONF = REPO / "tools" / "shared.conf"


def pairs():
    out = []
    for ln in CONF.read_text(encoding="utf-8").splitlines():
        ln = ln.split("#", 1)[0].strip()
        if not ln:
            continue
        dst, src = [x.strip() for x in ln.split("<-")]
        out.append((REPO / dst, REPO / src))
    return out


def check():
    bad = []
    for dst, src in pairs():
        if not src.exists():
            bad.append(f"нет источника {src.relative_to(REPO)}")
        elif not dst.exists() or dst.read_bytes() != src.read_bytes():
            bad.append(f"{dst.relative_to(REPO)} отличается от {src.relative_to(REPO)}")
    return bad


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if a.check:
        bad = check()
        for b in bad:
            print(f"✗ {b} — запусти python3 tools/sync_shared.py")
        return 1 if bad else 0
    for dst, src in pairs():
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists() or dst.read_bytes() != src.read_bytes():
            shutil.copyfile(src, dst)
            print(f"+ {dst.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
