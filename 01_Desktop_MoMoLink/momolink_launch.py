# -*- coding: utf-8 -*-
"""
================================================================================
 MoMoLink Launcher — تشغيل تطبيق الحاسوب
--------------------------------------------------------------------------------
يضمن وجود مكتبة الواجهة (flet) ثم يشغّل التطبيق.
مكتوب ببايثون لا بملف دفعي، لأن النصوص العربية داخل .bat تتلف عند تشغيلها في cmd.
================================================================================
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP = HERE / "momolink_desktop.py"
REQUIREMENTS = HERE / "requirements.txt"


def _utf8() -> None:
    if os.name == "nt":
        try:
            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            ctypes.windll.kernel32.SetConsoleCP(65001)
        except Exception:
            pass
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def say(text: str = "") -> None:
    try:
        print(text, flush=True)
    except Exception:
        pass


def main() -> int:
    _utf8()
    say("=" * 62)
    say("   MoMoLink Desktop Pro  —  تشغيل التطبيق")
    say("=" * 62)

    if not APP.is_file():
        say(f"[خطأ] لم أجد ملف التطبيق: {APP}")
        return 1

    # هل مكتبة الواجهة موجودة؟
    try:
        import flet  # noqa: F401
    except Exception:
        say("[1/1] تثبيت المكتبات لأول مرة... قد تستغرق دقيقة.")
        code = subprocess.call(
            [sys.executable, "-m", "pip", "install",
             "--disable-pip-version-check", "--quiet", "-r", str(REQUIREMENTS)]
        )
        if code != 0:
            say("[خطأ] فشل تثبيت المكتبات. تحقّق من الإنترنت ثم أعد المحاولة.")
            return code

    say("تشغيل التطبيق... (أغلق نافذة التطبيق لإيقافه)")
    say()
    return subprocess.call([sys.executable, str(APP)], cwd=str(HERE))


if __name__ == "__main__":
    code = main()
    if code != 0:
        try:
            input("\nاضغط Enter للإغلاق...")
        except Exception:
            pass
    sys.exit(code)
