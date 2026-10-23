# -*- coding: utf-8 -*-
"""
================================================================================
 MoMoLink Builder — بناء ملف EXE واحد مستقل
--------------------------------------------------------------------------------
يشغّله build_exe.bat. كل الرسائل بالعربية لأن بايثون يتعامل معها بثقة،
بخلاف ملفات .bat التي تتلف نصوصها العربية عند التشغيل في cmd.

ما يفعله:
  1) يتأكد من PyInstaller و Pillow والمتطلبات.
  2) يولّد الأيقونة إن غابت (assets/make_icon.py).
  3) يبحث عن عميل Flet المكتبي ليُدمجه (يعمل بلا إنترنت في أول تشغيل).
  4) يبني ملفاً واحداً: dist\\MoMoLinkDesktopPro.exe بلا نافذة سوداء.
================================================================================
"""

from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP = HERE / "momolink_desktop.py"
EXE_NAME = "MoMoLinkDesktopPro"
TARGET = HERE / "dist" / f"{EXE_NAME}.exe"


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


def line_title(text: str) -> None:
    say("=" * 62)
    say(f"   {text}")
    say("=" * 62)
    say()


def pip(*args: str) -> bool:
    return subprocess.call(
        [sys.executable, "-m", "pip", "install",
         "--disable-pip-version-check", "--quiet", *args]
    ) == 0


def find_flet_client() -> str | None:
    """عميل Flet المكتبي: مجلد يحتوي flet.exe (يُدمج ليَعمل بلا إنترنت)."""
    base = Path(os.environ.get("USERPROFILE", Path.home())) / ".flet" / "client"
    if not base.is_dir():
        return None
    for folder in sorted(base.glob("flet-desktop-*"), reverse=True):
        candidate = folder / "flet"
        if (candidate / "flet.exe").is_file():
            return str(candidate)
    return None


def main() -> int:
    _utf8()
    line_title("MoMoLink Desktop Pro   -   تحويل التطبيق إلى ملف EXE")
    say("هذه العملية تُنشئ ملفاً واحداً مستقلاً يعمل على أي ويندوز")
    say("بدون تثبيت بايثون ولا أي مكتبة. تستغرق 2 - 5 دقائق.")
    say()

    if not APP.is_file():
        say(f"[خطأ] لم أجد ملف التطبيق: {APP}")
        return 1

    # ---------------- 1) المكتبات ----------------
    say("[1/5] تجهيز المكتبات (مرة واحدة فقط)...")
    pip("--upgrade", "pip")
    if not pip("-r", str(HERE / "requirements.txt")):
        say("[خطأ] فشل تثبيت متطلبات المشروع. تحقّق من الإنترنت.")
        return 1
    if not pip("pyinstaller", "pillow"):
        say("[خطأ] فشل تثبيت أدوات البناء. تحقّق من الإنترنت.")
        return 1
    say("      تم.")
    say()

    # ---------------- 2) الأيقونة ----------------
    say("[2/5] تجهيز الأيقونة...")
    icon = HERE / "assets" / "icon.ico"
    if not icon.is_file():
        maker = HERE / "assets" / "make_icon.py"
        if maker.is_file():
            subprocess.call([sys.executable, str(maker)], cwd=str(HERE))
    say("      الأيقونة جاهزة." if icon.is_file()
        else "      تنبيه: لا توجد أيقونة، سيُبنى الملف بدونها.")
    say()

    # ---------------- 3) عميل Flet ----------------
    say("[3/5] البحث عن عميل Flet المكتبي...")
    client = find_flet_client()
    if client:
        say(f"      وُجد: {client}")
        say("      سيُدمج داخل الملف = يعمل بلا إنترنت في أول تشغيل.")
    else:
        say("      غير موجود حالياً.")
        say("      سيُبنى الملف بحجم أصغر، ويُنزّل العميل عند أول تشغيل.")
    say()

    # ---------------- 4) تنظيف ----------------
    say("[4/5] تنظيف مخرجات البناء السابقة...")
    for folder in ("build", "dist"):
        shutil.rmtree(HERE / folder, ignore_errors=True)
    for old in HERE.glob("*.spec"):
        try:
            old.unlink()
        except OSError:
            pass
    say("      تم.")
    say()

    # ---------------- 5) البناء ----------------
    say("[5/5] جاري بناء الملف التنفيذي...")
    say()
    command = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onefile", "--windowed",
        "--name", EXE_NAME,
    ]
    if icon.is_file():
        command += ["--icon", str(icon)]
    command += ["--add-data", f"{HERE / 'scrcpy'};scrcpy"]
    if client:
        command += ["--add-data", f"{client};flet_client"]
    command += [
        "--collect-all", "flet",
        "--collect-all", "flet_desktop",
        str(APP),
    ]
    code = subprocess.call(command, cwd=str(HERE))
    if code != 0:
        say()
        say(f"[خطأ] فشل البناء (رمز {code}). راجع الرسائل أعلاه.")
        return code

    # ---------------- النتيجة ----------------
    say()
    if TARGET.is_file():
        size_mb = TARGET.stat().st_size / (1024 * 1024)
        line_title("تم البناء بنجاح")
        say(f"   الملف : {TARGET}")
        say(f"   الحجم : {size_mb:.1f} م.ب")
        say()
        say("   يمكنك نسخ هذا الملف إلى أي حاسوب ويندوز وتشغيله مباشرة.")
        say("=" * 62)
        try:
            os.startfile(str(TARGET.parent))  # type: ignore[attr-defined]
        except Exception:
            pass
        return 0

    say("[خطأ] لم يكتمل البناء. راجع الرسائل أعلاه.")
    return 1


if __name__ == "__main__":
    result = main()
    if result != 0:
        try:
            input("\nاضغط Enter للإغلاق...")
        except Exception:
            pass
    sys.exit(result)
