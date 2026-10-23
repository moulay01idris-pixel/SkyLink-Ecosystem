# -*- coding: utf-8 -*-
"""
================================================================================
 MoMoLink Admin — v1.0.0
--------------------------------------------------------------------------------
أدوات صيانة جسر MoMoLink Remote، مع رسائل عربية سليمة (بعيداً عن مشاكل ترميز cmd):

    status       عرض حالة كل شيء (IP · الجسر · RDP · جدار الحماية)
    firewall     التأكد من فتح المنفذ 8756 لشبكة البيت فقط
    enable-rdp   تفعيل سطح المكتب البعيد + فتح 3389 لشبكة البيت فقط
    disable-rdp  إغلاق سطح المكتب البعيد نهائياً

لماذا بايثون لا ملف دفعي؟ لأن ملفات .bat العربية تتلف عند تشغيلها في cmd
(تعارض UTF-8 مع chcp يقتطع الحروف ويكسر تحليل الأوامر). بايثون يتعامل مع
العربية بشكل موثوق 100%.

الصلاحيات: enable-rdp و disable-rdp يحتاجان مديراً — يطلبانها تلقائياً.
================================================================================
"""

from __future__ import annotations

import ctypes
import os
import socket
import subprocess
import sys

IS_WINDOWS = os.name == "nt"
TS_KEY = r"SYSTEM\CurrentControlSet\Control\Terminal Server"
BRIDGE_RULE = "MoMoLink Bridge 8756"
RDP_RULE = "MoMoLink RDP (LAN only)"
BRIDGE_PORT = 8756
RDP_PORT = 3389


# ------------------------------------------------------------------ أدوات مساعدة
def _utf8() -> None:
    if IS_WINDOWS:
        try:
            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            ctypes.windll.kernel32.SetConsoleCP(65001)
        except Exception:
            pass
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass


def say(text: str = "") -> None:
    try:
        print(text, flush=True)
    except Exception:
        try:
            enc = getattr(sys.stdout, "encoding", None) or "ascii"
            print(text.encode(enc, "replace").decode(enc, "replace"), flush=True)
        except Exception:
            pass


def rule(text: str = "") -> None:
    say("  " + "─" * 62)
    if text:
        say("  " + text)


def run(cmd: list[str], timeout: int = 25) -> tuple[int, str]:
    """ينفّذ أمراً ويعيد (رمز الخروج، المخرجات) — بلا نوافذ سوداء."""
    try:
        creation = subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
            creationflags=creation,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except Exception as exc:
        return 1, str(exc)


def is_admin() -> bool:
    if not IS_WINDOWS:
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def elevate() -> bool:
    """يعيد تشغيل نفس الأمر بصلاحيات مدير، بنافذة مخفية."""
    try:
        params = " ".join([f'"{a}"' for a in sys.argv])
        result = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, params, None, 0
        )
        return int(result) > 32
    except Exception:
        return False


def lan_ips() -> list[str]:
    """عناوين الحاسوب في الشبكة المحلية (بلا إرسال أي بيانات)."""
    found: list[str] = []
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("8.8.8.8", 53))
            found.append(sock.getsockname()[0])
        finally:
            sock.close()
    except Exception:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip not in found and not ip.startswith("127."):
                found.append(ip)
    except Exception:
        pass
    return found or ["127.0.0.1"]


def firewall_rule_exists(name: str) -> bool:
    code, _ = run(["netsh", "advfirewall", "firewall", "show", "rule", f"name={name}"])
    return code == 0


def add_firewall_rule(name: str, port: int) -> tuple[bool, str]:
    run(["netsh", "advfirewall", "firewall", "delete", "rule", f"name={name}"])
    code, out = run([
        "netsh", "advfirewall", "firewall", "add", "rule",
        f"name={name}", "dir=in", "action=allow", "protocol=TCP",
        f"localport={port}", "profile=private", "remoteip=localsubnet",
    ])
    return code == 0, out.strip()


def port_listening(port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1.2)
            return sock.connect_ex(("127.0.0.1", port)) == 0
    except Exception:
        return False


def rdp_enabled() -> bool:
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, TS_KEY) as key:
            value, _ = winreg.QueryValueEx(key, "fDenyTSConnections")
            return int(value) == 0
    except Exception:
        return False


# ------------------------------------------------------------------ الأوامر
def cmd_status() -> int:
    say()
    say("=" * 68)
    say("   MoMoLink Remote — حالة الاتصال")
    say("=" * 68)
    say()
    say(f"  اسم الحاسوب : {socket.gethostname()}")
    say(f"  المستخدم    : {os.environ.get('USERNAME', '?')}")
    for ip in lan_ips():
        say(f"  عنوان IP    : {ip}")
    say(f"  صلاحية مدير : {'نعم' if is_admin() else 'لا (بعض الأوامر ستطلبها)'}")

    rule("جسر الملفات والحافظة")
    if port_listening(BRIDGE_PORT):
        say(f"  [يعمل]  الخادم يستمع على المنفذ {BRIDGE_PORT}")
        for ip in lan_ips():
            say(f"          من الهاتف: http://{ip}:{BRIDGE_PORT}/")
        say("          (الرابط الكامل مع رمز الدخول في نافذة الجسر)")
    else:
        say(f"  [متوقف] شغّل run_bridge.bat")
    say(f"  جدار الحماية: {'مفتوح لشبكة البيت' if firewall_rule_exists(BRIDGE_RULE) else 'غير مفتوح — الهاتف لن يتصل'}")

    rule("سطح المكتب البعيد (RDP)")
    if rdp_enabled():
        code, _ = run(["sc", "query", "TermService"])
        running = "RUNNING" in _.upper()
        say(f"  [مُفعَّل] الخدمة {'تعمل' if running else 'متوقفة (أعد تشغيل الحاسوب)'}")
        say("          تطبيق Microsoft Remote Desktop على الهاتف:")
        for ip in lan_ips():
            say(f"          PC name: {ip}   User: {os.environ.get('USERNAME', '?')}")
    else:
        say("  [مُعطَّل] شغّل enable_rdp.bat إن أردت التحكم بالحاسوب من الهاتف")
    say(f"  جدار الحماية: {'مفتوح لشبكة البيت' if firewall_rule_exists(RDP_RULE) else 'غير مفتوح'}")

    rule("العنوان الذي تكتبه في الهاتف")
    say(f"  http://{lan_ips()[0]}:{BRIDGE_PORT}/")
    say()
    say("=" * 68)
    return 0


def cmd_firewall() -> int:
    if firewall_rule_exists(BRIDGE_RULE):
        say(f"  [ok] المنفذ {BRIDGE_PORT} مفتوح مسبقاً لشبكة البيت.")
        return 0

    ok, out = add_firewall_rule(BRIDGE_RULE, BRIDGE_PORT)
    if ok:
        say(f"  [ok] فُتح المنفذ {BRIDGE_PORT} لشبكة البيت فقط.")
        return 0

    if not is_admin():
        say("  طلب صلاحية المدير لفتح المنفذ (نافذة موافقة واحدة)...")
        if elevate():
            import time

            for _ in range(10):
                time.sleep(1)
                if firewall_rule_exists(BRIDGE_RULE):
                    say(f"  [ok] فُتح المنفذ {BRIDGE_PORT} لشبكة البيت فقط.")
                    return 0
        say("  [!] لم تُمنح الصلاحية — الهاتف لن يستطيع الاتصال.")
        say("      الحل: انقر بالزر الأيمن على run_bridge.bat ثم «تشغيل كمسؤول».")
        return 1

    say(f"  [X] فشل فتح المنفذ: {out[:200]}")
    return 1


def cmd_enable_rdp() -> int:
    say()
    say("=" * 68)
    say("   تفعيل سطح المكتب البعيد (RDP) — للتحكم بحاسوبك من الهاتف")
    say("=" * 68)
    say()

    if not is_admin():
        say("  هذا الأمر يحتاج صلاحية مدير. أطلبها الآن (وافق على النافذة)...")
        if elevate():
            say("  تم إرسال الطلب في نافذة منفصلة.")
        else:
            say("  [X] لم تُمنح الصلاحية.")
        return 1

    say("  [1/4] السماح بالاتصالات في النظام...")
    code, out = run([
        "reg", "add", f"HKLM\\{TS_KEY}", "/v", "fDenyTSConnections",
        "/t", "REG_DWORD", "/d", "0", "/f",
    ])
    if code != 0:
        say(f"  [X] فشل التعديل: {out[:200]}")
        return 1
    say("        [ok]")

    say("  [2/4] تشغيل خدمة سطح المكتب البعيد...")
    run(["sc", "config", "TermService", "start=", "auto"])
    run(["net", "start", "TermService"])
    code, out = run(["sc", "query", "TermService"])
    if "RUNNING" in out.upper():
        say("        [ok] الخدمة تعمل")
    else:
        say("        [!] الخدمة لم تبدأ — أعد تشغيل الحاسوب ثم كرّر")

    say("  [3/4] فتح المنفذ 3389 لشبكة البيت فقط...")
    ok, out = add_firewall_rule(RDP_RULE, RDP_PORT)
    say("        [ok] لا يمكن الوصول إليه من الإنترنت" if ok else f"        [!] {out[:150]}")

    say("  [4/4] معلومات الاتصال")
    say()
    say(f"        اسم الحاسوب : {socket.gethostname()}")
    say(f"        المستخدم    : {os.environ.get('USERNAME', '?')}")
    for ip in lan_ips():
        say(f"        عنوان IP    : {ip}")
    say()
    say("  في تطبيق Microsoft Remote Desktop على الهاتف:")
    say("        PC name  =  عنوان IP أعلاه")
    say(f"        User     =  {os.environ.get('USERNAME', '?')}")
    say("        Password =  كلمة مرور ويندوز الخاصة بك")
    say()
    say("  تنبيهات:")
    say("   • يجب أن يكون لحسابك كلمة مرور. الحساب بلا كلمة مرور يرفض RDP")
    say("     (قيد في ويندوز نفسه وليس من عندنا).")
    say("   • أثناء اتصال الهاتف تُقفل شاشة الحاسوب محلياً (جلسة واحدة).")
    say("   • بعد الانتهاء شغّل disable_rdp.bat لإغلاق الباب.")
    say()
    say("=" * 68)
    return 0


def cmd_disable_rdp() -> int:
    say()
    say("=" * 68)
    say("   إيقاف سطح المكتب البعيد")
    say("=" * 68)
    say()

    if not is_admin():
        say("  يحتاج صلاحية مدير. أطلبها الآن (وافق على النافذة)...")
        if elevate():
            say("  تم إرسال الطلب في نافذة منفصلة.")
        else:
            say("  [X] لم تُمنح الصلاحية.")
        return 1

    say("  [1/3] منع اتصالات RDP الجديدة...")
    run([
        "reg", "add", f"HKLM\\{TS_KEY}", "/v", "fDenyTSConnections",
        "/t", "REG_DWORD", "/d", "1", "/f",
    ])
    say("        [ok]")

    say("  [2/3] إيقاف الخدمة...")
    run(["net", "stop", "TermService", "/y"])
    run(["sc", "config", "TermService", "start=", "demand"])
    say("        [ok]")

    say("  [3/3] حذف قاعدة جدار الحماية...")
    run(["netsh", "advfirewall", "firewall", "delete", "rule", f"name={RDP_RULE}"])
    say("        [ok]")

    say()
    say("  تم الإغلاق. جسر الملفات والحافظة يعمل باستقلال عنه.")
    say("=" * 68)
    return 0


COMMANDS = {
    "status": cmd_status,
    "firewall": cmd_firewall,
    "enable-rdp": cmd_enable_rdp,
    "disable-rdp": cmd_disable_rdp,
}


def main() -> int:
    _utf8()
    action = (sys.argv[1] if len(sys.argv) > 1 else "status").strip().lower()
    handler = COMMANDS.get(action)
    if handler is None:
        say(f"أمر غير معروف: {action}")
        say("المتاح: " + " · ".join(COMMANDS))
        return 2
    return handler()


if __name__ == "__main__":
    code = main()
    # نُبقي النافذة مفتوحة أمام المستخدم ليقرأ النتيجة
    if "--no-wait" not in sys.argv:
        try:
            input("\nاضغط Enter للإغلاق...")
        except Exception:
            pass
    sys.exit(code)
