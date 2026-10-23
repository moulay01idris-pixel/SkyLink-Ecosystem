# -*- coding: utf-8 -*-
"""
اختبارات منطق النواة في SkyLink Desktop (بدون فتح الواجهة).

يشغّل هذا الملف الدوال النقية فقط:
  * parse_target / clean_host  ← التحقق من العنوان (خط الدفاع ضد حقن الأوامر)
  * Toolchain                  ← اكتشاف scrcpy و adb

التشغيل:
    python _test_core.py
"""

from __future__ import annotations

import sys

import skylink_desktop as core


passed = 0
failed = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}  {detail}")


def test_valid_targets() -> None:
    print("\n[1] عناوين صحيحة")
    cases = {
        "192.168.1.25": ("192.168.1.25", 5555),
        " 192.168.1.25 ": ("192.168.1.25", 5555),
        "192.168.1.25:43215": ("192.168.1.25", 43215),
        "192.168.1.25:1": ("192.168.1.25", 1),
        "192.168.1.25:65535": ("192.168.1.25", 65535),
        "10.0.0.7:5555": ("10.0.0.7", 5555),
        "[fe80::1]:5555": ("fe80::1", 5555),
    }
    for raw, expected in cases.items():
        got = core.parse_target(raw)
        check(f"parse_target({raw!r}) == {expected}", got == expected, f"got={got}")


def test_injection_rejected() -> None:
    print("\n[2] محاولات حقن / مدخلات خطرة (يجب أن تُرفض كلها)")
    attacks = [
        "192.168.1.1; rm -rf /",
        "192.168.1.1 && calc",
        "192.168.1.1 | powershell",
        "192.168.1.1 & shutdown /s",
        "$(whoami)",
        "`whoami`",
        "192.168.1.1\n rm -rf",
        "192.168.1.1 ; scrcpy",
        "--serial=evil",
        "192.168.1.1:5555; rm -rf /",
    ]
    for raw in attacks:
        got = core.parse_target(raw)
        check(f"رفض {raw!r}", got is None, f"got={got}")


def test_invalid_targets() -> None:
    print("\n[3] مدخلات غير صالحة")
    invalids = [
        "", "   ", "abc", "192.168.1", "192.168.1.256", "999.1.1.1",
        "127.0.0.1", "0.0.0.0", "224.0.0.1",
        "192.168.1.1:0", "192.168.1.1:65536", "192.168.1.1:99999",
        "192.168.1.1:abc", "192.168.1.1:22:33", "[fe80::1", "192..1.1",
    ]
    for raw in invalids:
        got = core.parse_target(raw)
        check(f"رفض {raw!r}", got is None, f"got={got}")


def test_clean_host() -> None:
    print("\n[4] clean_host")
    check("clean_host مع منفذ", core.clean_host("192.168.1.5:4444") == "192.168.1.5")
    check("clean_host بلا منفذ", core.clean_host("192.168.1.5") == "192.168.1.5")
    check("clean_host لمدخل خاطئ", core.clean_host("evil; rm") is None)


def test_toolchain() -> None:
    print("\n[5] اكتشاف الأدوات المدمجة")
    tools = core.Toolchain()
    check("scrcpy موجود", tools.ready, f"scrcpy_exe={tools.scrcpy_exe}")
    check("adb موجود", tools.adb_exe is not None, f"adb_exe={tools.adb_exe}")
    check("مجلد العمل = مجلد scrcpy", "scrcpy" in tools.workdir.lower(), tools.workdir)
    if tools.ready:
        version = tools.version()
        check("إصدار scrcpy مقروء", bool(version) and version != "غير معروف", version)
        print(f"        الإصدار المكتشف: {version}")


def test_adb_smoke() -> None:
    print("\n[6] تشغيل adb فعلياً (بدون نافذة)")
    tools = core.Toolchain()
    if not tools.adb_exe:
        check("adb غير متاح — تُخطّى", True)
        return
    code, out = tools.adb("version", timeout=20)
    check("adb version يعمل", code == 0 and "Android Debug Bridge" in out, out[:80])
    code2, out2 = tools.adb("devices")
    check("adb devices يعمل", code2 == 0 and "List of devices" in out2, out2[:80])


def main() -> int:
    print("=" * 62)
    print(" اختبارات نواة SkyLink Desktop")
    print("=" * 62)
    test_valid_targets()
    test_injection_rejected()
    test_invalid_targets()
    test_clean_host()
    test_toolchain()
    test_adb_smoke()
    print("\n" + "=" * 62)
    print(f" النتيجة: {passed} نجح · {failed} فشل")
    print("=" * 62)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
