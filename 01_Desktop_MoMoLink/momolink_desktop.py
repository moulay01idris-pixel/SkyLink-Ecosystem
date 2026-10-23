# -*- coding: utf-8 -*-
"""
================================================================================
 MoMoLink Desktop Pro  🚀  —  v1.0.0
--------------------------------------------------------------------------------
 تطبيق سطح المكتب لمنظومة MoMoLink Ecosystem.

 الوظيفة:
   بث شاشة هاتف أندرويد والتحكم بها من الحاسوب عبر scrcpy + ADB،
   بكابل USB أو لاسلكياً عبر Wi-Fi، بضغطة زر واحدة وبدون أي نافذة سوداء.

 المبادئ الهندسية المطبَّقة:
   * لا استخدام إطلاقاً لـ shell=True  ⇒ لا احتمال لحقن أوامر (Command Injection).
   * كل عنوان IP يُتحقَّق منه بـ ipaddress قبل تمريره لأي أمر.
   * المسارات تُحلّ من مواقع معروفة فقط، ولا يُنفَّذ أي ملف من مجلد عشوائي.
   * إخفاء نافذة الكونسول عبر CREATE_NO_WINDOW + STARTF_USESHOWWINDOW.
   * كل عمليات الإدخال/الإخراج الثقيلة في خيوط منفصلة ⇒ الواجهة لا تتجمد.
   * تنظيف العمليات عند الإغلاق (page.on_close) ⇒ لا عمليات معلّقة.
   * لا تُخزَّن أي بيانات حساسة؛ فقط آخر طريقة اتصال وآخر IP في ملف إعدادات محلي.

 التشغيل:
   python momolink_desktop.py
================================================================================
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Optional


# ==============================================================================
# تهيئة مبكرة: ربط عميل Flet المكتبي المدمج داخل ملف .exe
# ------------------------------------------------------------------------------
# عند بناء التطبيق بـ PyInstaller نضع مجلد عميل Flet بجانب الكود داخل الحزمة،
# ونُخبر Flet بمساره عبر FLET_VIEW_PATH حتى لا يحتاج التطبيق إلى إنترنت
# في أول تشغيل، ولا إلى تثبيت أي شيء على حاسوب المستخدم.
# ==============================================================================

def _bootstrap_bundled_client() -> None:
    if not getattr(sys, "frozen", False):
        return
    if os.environ.get("FLET_VIEW_PATH"):
        return

    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "flet_client")
    candidates.append(Path(sys.executable).resolve().parent / "flet_client")

    for folder in candidates:
        try:
            if (folder / "flet.exe").is_file() or (folder / "flet").is_file():
                os.environ["FLET_VIEW_PATH"] = str(folder)
                return
        except OSError:
            continue


_bootstrap_bundled_client()

import flet as ft


# ==============================================================================
# 0) ثوابت عامة وألوان الواجهة (ألوان HEX تعمل مع كل إصدارات Flet)
# ==============================================================================

APP_NAME = "MoMoLink Desktop Pro"
APP_VERSION = "1.0.0"
# عنوان شريط النافذة: بلا رموز تعبيرية لأن ويندوز لا يرسمها في شريط العنوان
# فكانت تظهر «??» — والرمز 🚀 موجود في عنوان الواجهة الداخلية أدناه.
WINDOW_TITLE = "MoMoLink Desktop Pro"

BG_DEEP = "#070C16"
BG_PANEL = "#0C1424"
CARD = "#121D31"
CARD_SOFT = "#182742"
BORDER = "#22304D"
TEXT_MAIN = "#E9EFFA"
TEXT_MUTED = "#8DA1C1"
ACCENT = "#22D3EE"
INDIGO = "#6366F1"
OK = "#22C55E"
WARN = "#F59E0B"
ERR = "#EF4444"
IDLE = "#2C3A55"

IS_WINDOWS = os.name == "nt"

#: يمنع ظهور نافذة الكونسول السوداء لأي أمر فرعي (Windows فقط).
CREATE_NO_WINDOW = 0x08000000 if IS_WINDOWS else 0

#: منفذ ADB اللاسلكي الافتراضي (نفس المنفذ المعروض في تطبيق الهاتف).
DEFAULT_ADB_PORT = 5555

#: مهلة أوامر ADB القصيرة (ثوانٍ).
ADB_TIMEOUT = 25

#: مدة الفحص للتأكد من أن scrcpy فتح نافذته فعلاً (ثوانٍ).
SCRCPY_STARTUP_PROBE = 6.0

#: أقصى عدد أسطر في سجل الأحداث (لتوفير الذاكرة).
MAX_LOG_LINES = 250


# ==============================================================================
# 1) الإعدادات المحلية (تُحفظ في مجلد المستخدم — لا تحتاج صلاحيات مدير)
# ==============================================================================

def _config_dir() -> Path:
    if IS_WINDOWS:
        base = os.environ.get("APPDATA")
        if base:
            return Path(base) / "MoMoLink"
    return Path.home() / ".momolink"


CONFIG_PATH = _config_dir() / "config.json"

#: نسخة الإعدادات — رفعها يفرض قيم جودة جديدة على من جرّب نسخة أقدم.
CONFIG_VERSION = "2"

DEFAULT_CONFIG: dict = {
    "mode": "usb",           # "usb" | "wifi"
    "last_ip": "",
    "quality": "high",       # high | medium | low
    "max_size": "1280",      # أقصى بعد بالبكسل — "": الأبعاد الأصلية
    "bitrate": "16",         # ميغابت/ثانية — أعلى = صورة أوضح
    "max_fps": "60",         # أقصى إطارات/ثانية
    "turn_screen_off": False,
    "stay_awake": True,
    "no_audio": True,        # الصوت يستهلك معالجاً — يُفتح عند الحاجة
    "config_version": CONFIG_VERSION,
}

#: كل مستوى جودة يضبط ثلاثة أرقام معاً (والباقي يبقى كما هو).
QUALITY_PRESETS: dict = {
    "high":   {"max_size": "1280", "bitrate": "16", "max_fps": "60"},
    "medium": {"max_size": "1024", "bitrate": "8",  "max_fps": "30"},
    "low":    {"max_size": "720",  "bitrate": "3",  "max_fps": "30"},
}

#: حقول الجودة التي تُعاد لقيمها الجديدة عند ترقية الإعدادات من نسخة أقدم.
_QUALITY_KEYS = ("quality", "max_size", "bitrate", "max_fps", "no_audio")


def load_config() -> dict:
    """يقرأ الإعدادات مع تجاهل آمن لأي ملف تالف (لا يُسقط التطبيق أبداً)."""
    cfg = dict(DEFAULT_CONFIG)
    try:
        if CONFIG_PATH.is_file():
            # utf-8-sig يتجاهل علامة BOM التي يضيفها Notepad تلقائياً،
            # وإلا فشلت قراءة ملف الإعدادات بصمت وعاد التطبيق للقيم الافتراضية.
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
            if isinstance(data, dict):
                # ملف قديم (قبل v2) كان يحفظ 8 ميغابت ودقة أصلية ⇒ صورة رديئة.
                # عند الترقية نتجاهل قيم الجودة المحفوظة ونأخذ الجديدة.
                same_version = str(data.get("config_version", "1")) == CONFIG_VERSION
                for key, default in DEFAULT_CONFIG.items():
                    if not same_version and key in _QUALITY_KEYS:
                        continue
                    value = data.get(key, default)
                    if isinstance(default, bool):
                        cfg[key] = bool(value)
                    elif isinstance(default, str):
                        cfg[key] = str(value)
                cfg["config_version"] = CONFIG_VERSION
    except Exception:
        pass
    return cfg


def save_config(cfg: dict) -> None:
    """كتابة ذرّية: ملف مؤقت ثم استبدال ⇒ لا يبقى ملف مبتور عند انقطاع مفاجئ."""
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = CONFIG_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, CONFIG_PATH)
    except Exception:
        pass


# ==============================================================================
# 2) اكتشاف أدوات scrcpy و adb (المدمجة بجانب التطبيق أو المثبّتة)
# ==============================================================================

def _tool_dirs() -> list[Path]:
    """
    ترتيب البحث عن مجلد scrcpy:
      1. متغيّر البيئة MOMOLINK_SCRCPY_DIR (لمن يريد مجلداً مخصصاً).
      2. مجلد بجانب الملف التنفيذي .exe  (الحالة الطبيعية بعد البناء).
      3. المجلد المؤقت الذي يفكّه PyInstaller في وضع --onefile.
      4. مجلد السكربت نفسه (وضع التطوير).
      5. أسماء النسخ الشائعة.
    """
    dirs: list[Path] = []

    env_dir = os.environ.get("MOMOLINK_SCRCPY_DIR")
    if env_dir:
        dirs.append(Path(env_dir))

    if getattr(sys, "frozen", False):
        dirs.append(Path(sys.executable).resolve().parent / "scrcpy")
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            dirs.append(Path(meipass) / "scrcpy")

    try:
        here = Path(__file__).resolve().parent
    except Exception:
        here = Path.cwd()

    dirs.extend([
        here / "scrcpy",
        here / "scrcpy-win64-v5.0.1",
        here,
    ])
    return dirs


def _which(name: str) -> Optional[Path]:
    """بديل مبسّط لـ shutil.which (نتجنّب استيراداً إضافياً بلا داعٍ)."""
    exts = [".exe", ".bat", ".cmd", ""] if IS_WINDOWS else [""]
    for folder in os.environ.get("PATH", "").split(os.pathsep):
        if not folder:
            continue
        for ext in exts:
            candidate = Path(folder) / (name + ext)
            try:
                if candidate.is_file():
                    return candidate
            except OSError:
                continue
    return None


class Toolchain:
    """يحلّ مسار scrcpy.exe و adb.exe مرة واحدة، ويوفّر تنفيذاً مخفيَّ النافذة."""

    def __init__(self) -> None:
        self.scrcpy_dir: Optional[Path] = None
        self.scrcpy_exe: Optional[Path] = None
        self.adb_exe: Optional[Path] = None
        self._resolve()

    # ------------------------------------------------------------------ بحث
    def _resolve(self) -> None:
        scrcpy_name = "scrcpy.exe" if IS_WINDOWS else "scrcpy"
        adb_name = "adb.exe" if IS_WINDOWS else "adb"

        for folder in _tool_dirs():
            try:
                if not folder or not folder.is_dir():
                    continue
            except OSError:
                continue
            candidate = folder / scrcpy_name
            if candidate.is_file():
                self.scrcpy_dir = folder
                self.scrcpy_exe = candidate
                adb_candidate = folder / adb_name
                if adb_candidate.is_file():
                    self.adb_exe = adb_candidate
                break

        # احتياط أخير: أدوات مثبّتة في PATH.
        if self.scrcpy_exe is None:
            found = _which("scrcpy")
            if found:
                self.scrcpy_exe = found
                self.scrcpy_dir = found.parent
        if self.adb_exe is None:
            found_adb = _which("adb")
            if found_adb:
                self.adb_exe = found_adb

        # نضع مجلد الأدوات في مقدمة PATH حتى تجد scrcpy ملفات DLL و scrcpy-server.
        if self.scrcpy_dir:
            current = os.environ.get("PATH", "")
            if str(self.scrcpy_dir) not in current.split(os.pathsep):
                os.environ["PATH"] = str(self.scrcpy_dir) + os.pathsep + current

    # ------------------------------------------------------------- خصائص
    @property
    def ready(self) -> bool:
        return self.scrcpy_exe is not None

    @property
    def workdir(self) -> str:
        if self.scrcpy_dir:
            return str(self.scrcpy_dir)
        return str(Path.cwd())

    # ------------------------------------------------------------- تنفيذ
    def _popen_kwargs(self) -> dict:
        kwargs: dict = {
            "cwd": self.workdir,
            "stdin": subprocess.DEVNULL,
            "env": os.environ.copy(),
        }
        if IS_WINDOWS:
            kwargs["creationflags"] = CREATE_NO_WINDOW
            # طبقة احتياطية ثانية: بعض الأوامر لا تحترم creationflags وحدها.
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 0  # SW_HIDE
            kwargs["startupinfo"] = si
        return kwargs

    def run(self, args: list[str], timeout: int = ADB_TIMEOUT) -> tuple[int, str]:
        """تنفيذ أمر قصير الأمد، التقاط المخرجات، وبلا أي نافذة."""
        try:
            proc = subprocess.run(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                **self._popen_kwargs(),
            )
            text = (proc.stdout or b"").decode("utf-8", errors="replace").strip()
            return int(proc.returncode), text
        except FileNotFoundError:
            return 127, f"الأداة غير موجودة: {args[0]}"
        except subprocess.TimeoutExpired:
            return 124, f"انتهت المهلة الزمنية: {' '.join(args)}"
        except Exception as exc:  # noqa: BLE001
            return 1, f"تعذّر تنفيذ الأمر: {exc}"

    def spawn(self, args: list[str]) -> subprocess.Popen:
        """تشغيل scrcpy (له نافذته الرسومية الخاصة). لا نلتقط مخرجاته."""
        return subprocess.Popen(args, **self._popen_kwargs())

    # ------------------------------------------------------------- ADB
    def adb(self, *args: str, timeout: int = ADB_TIMEOUT) -> tuple[int, str]:
        if not self.adb_exe:
            return 127, "adb غير موجود بجانب scrcpy ولا في PATH."
        return self.run([str(self.adb_exe), *args], timeout=timeout)

    def version(self) -> str:
        """إصدار scrcpy كما يعلنه هو نفسه."""
        if not self.scrcpy_exe:
            return "غير متوفر"
        code, out = self.run([str(self.scrcpy_exe), "--version"], timeout=15)
        if code != 0:
            return "غير معروف"
        match = re.search(r"scrcpy\s+([0-9][0-9a-zA-Z.\-+]*)", out)
        if match:
            return match.group(1)
        first = out.splitlines()[0].strip() if out else ""
        return first[:40] or "غير معروف"


# ==============================================================================
# 3) التحقق من المدخلات (خط الدفاع الأول قبل أي أمر)
# ==============================================================================

_IPV4_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")


def parse_target(raw: str) -> Optional[tuple[str, int]]:
    """
    يحلّل ما يكتبه المستخدم إلى (عنوان، منفذ).

    يقبل:
        192.168.1.25            → (192.168.1.25, 5555)
        192.168.1.25:43215      → (192.168.1.25, 43215)   ← أندرويد 11+ "التصحيح اللاسلكي"
        [fe80::1]:5555          → (fe80::1, 5555)

    يرفض كل ما ليس عنواناً صحيحاً ⇒ يستحيل تمرير «; rm -rf» أو أي نص غريب إلى ADB.
    """
    text = (raw or "").strip()
    if not text:
        return None

    host = text
    port = DEFAULT_ADB_PORT

    if text.startswith("["):
        end = text.find("]")
        if end == -1:
            return None
        host = text[1:end]
        rest = text[end + 1:]
        if rest:
            if not rest.startswith(":") or not rest[1:].isdigit():
                return None
            port = int(rest[1:])
    elif text.count(":") == 1:
        host_part, port_part = text.split(":", 1)
        host = host_part
        if port_part:
            if not port_part.isdigit():
                return None
            port = int(port_part)

    if not (1 <= port <= 65535):
        return None

    if _IPV4_RE.match(host):
        try:
            addr = ipaddress.IPv4Address(host)
        except ValueError:
            return None
        if addr.is_unspecified or addr.is_multicast or addr.is_loopback:
            return None
        return str(addr), port

    try:
        return str(ipaddress.IPv6Address(host)), port
    except ValueError:
        return None


def clean_host(raw: str) -> Optional[str]:
    """يُعيد العنوان فقط (بلا منفذ) أو None — تُستعمل للعرض والتحقق السريع."""
    parsed = parse_target(raw)
    return parsed[0] if parsed else None


# ==============================================================================
# 4) محرّك الاتصال (Backend) — يعمل دائماً داخل خيط منفصل
# ==============================================================================

class MoMoLinkEngine:
    """
    كل منطق الاتصال مع الهاتف.
    لا يمسّ عناصر الواجهة مباشرةً، بل يُبلّغ عبر دوال مرجعية (Callbacks).
    """

    def __init__(
        self,
        toolchain: Toolchain,
        on_status: Callable[[str, str, str], None],
        on_log: Callable[[str], None],
        on_devices: Callable[[list[str]], None],
        on_busy: Callable[[bool], None],
    ) -> None:
        self.tools = toolchain
        self._on_status = on_status
        self._on_log = on_log
        self._on_devices = on_devices
        self._on_busy = on_busy

        self._lock = threading.Lock()
        self._scrcpy_proc: Optional[subprocess.Popen] = None
        self._stop_flag = threading.Event()
        self._opts: dict = dict(DEFAULT_CONFIG)

    # ---------------------------------------------------------------- حالة
    def status(self, kind: str, title: str, detail: str = "") -> None:
        """kind ∈ {idle, working, ok, error}"""
        self._on_status(kind, title, detail)

    def log(self, message: str) -> None:
        self._on_log(message)

    def set_options(self, opts: dict) -> None:
        self._opts = dict(opts)

    # ------------------------------------------------------------- الأجهزة
    def list_devices(self) -> list[str]:
        code, out = self.tools.adb("devices")
        if code != 0:
            self.log(f"ADB: {out}")
            return []

        devices: list[str] = []
        for line in out.splitlines()[1:]:
            line = line.strip()
            if not line or "\t" not in line:
                continue
            serial, state = line.split("\t", 1)
            state = state.strip()
            if state == "device":
                devices.append(serial)
            elif state == "unauthorized":
                devices.append(f"{serial}  ← غير مصرّح (اقبل النافذة على الهاتف)")
            elif state == "offline":
                devices.append(f"{serial}  ← غير متصل")
        return devices

    def refresh_devices(self) -> None:
        if not self.tools.adb_exe:
            return
        self.tools.adb("start-server")
        self._on_devices(self.list_devices())

    # ------------------------------------------------------- بناء معاملات scrcpy
    def _scrcpy_options(self) -> list[str]:
        args: list[str] = [f"--window-title={APP_NAME}"]

        max_size = str(self._opts.get("max_size") or "").strip()
        if max_size.isdigit() and int(max_size) >= 240:
            args.append(f"--max-size={int(max_size)}")

        bitrate = str(self._opts.get("bitrate") or "").strip()
        if bitrate.isdigit() and int(bitrate) > 0:
            args.append(f"--video-bit-rate={int(bitrate)}M")

        fps = str(self._opts.get("max_fps") or "").strip()
        if fps.isdigit() and int(fps) > 0:
            args.append(f"--max-fps={int(fps)}")

        if self._opts.get("turn_screen_off"):
            args.append("--turn-screen-off")
        if self._opts.get("stay_awake"):
            args.append("--stay-awake")
        if self._opts.get("no_audio"):
            args.append("--no-audio")   # متاح في scrcpy 2.0+ فقط
        return args

    # ------------------------------------------------------------- إيقاف
    def stop(self) -> None:
        self._stop_flag.set()
        with self._lock:
            proc = self._scrcpy_proc
        if proc and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
            try:
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        self.log("تم إيقاف جلسة البث.")
        self.status("idle", "متوقف", "لا توجد جلسة بث نشطة الآن.")

    # ------------------------------------------------------------- مراقبة
    def _monitor(self, proc: subprocess.Popen, success_detail: str) -> None:
        try:
            code = proc.wait()
        except Exception:
            return
        with self._lock:
            if self._scrcpy_proc is proc:
                self._scrcpy_proc = None
        self._on_busy(False)
        if self._stop_flag.is_set():
            self.status("idle", "متوقف", "أوقفت الجلسة يدوياً.")
        elif code == 0:
            self.status("ok", "انتهت الجلسة", success_detail)
        else:
            self.status("error", "انتهت الجلسة بخطأ", f"رمز الخروج: {code}")

    def _launch_variants(self, variants: list[list[str]], ok_detail: str) -> bool:
        """
        يجرّب صيغ أوامر scrcpy بالترتيب حتى تنجح إحداها.
        النجاح = بقاء العملية حيّة بعد مدة الفحص (أي أن نافذة البث فُتحت).
        """
        assert self.tools.scrcpy_exe is not None
        for index, args in enumerate(variants, start=1):
            self.log("تنفيذ: " + self.tools.scrcpy_exe.name + " " + " ".join(args))
            try:
                proc = self.tools.spawn([str(self.tools.scrcpy_exe), *args])
            except Exception as exc:  # noqa: BLE001
                self.log(f"تعذّر تشغيل scrcpy: {exc}")
                continue

            with self._lock:
                self._scrcpy_proc = proc

            deadline = time.time() + SCRCPY_STARTUP_PROBE
            while time.time() < deadline:
                if proc.poll() is not None:
                    break
                time.sleep(0.2)

            if proc.poll() is None:
                self.status("ok", "متصل ✔ الشاشة تُبثّ الآن", ok_detail)
                self._on_busy(False)
                threading.Thread(
                    target=self._monitor, args=(proc, ok_detail), daemon=True
                ).start()
                return True

            code = proc.returncode
            self.log(f"الصيغة {index} فشلت (رمز الخروج: {code}).")

        with self._lock:
            self._scrcpy_proc = None
        return False

    def _explain_failure(self) -> None:
        """يقرأ حالة ADB ويشرح سبب الفشل بلغة مفهومة لغير المبرمج."""
        code, out = self.tools.adb("devices")
        if code == 0:
            self.log("أجهزة ADB الحالية:\n" + out)
            lowered = out.lower()
            if "unauthorized" in lowered:
                self.status(
                    "error",
                    "الهاتف لم يصرّح للحاسوب",
                    "افتح شاشة الهاتف واقبل نافذة «السماح بتصحيح الأخطاء» ثم أعد المحاولة.",
                )
                return
            rows = [l for l in out.splitlines()[1:] if l.strip()]
            if not rows:
                self.status(
                    "error",
                    "لا يوجد جهاز متصل",
                    "تأكد من الكابل ووضعية نقل الملفات، أو فعّل «التصحيح اللاسلكي» على الهاتف.",
                )
                return
        self.status(
            "error",
            "فشل تشغيل البث",
            "راجع «سجل الأحداث» بالأسفل — غالباً خيار غير مدعوم في نسخة scrcpy الحالية.",
        )

    # ------------------------------------------------------------- USB
    def connect_usb(self) -> None:
        self._stop_flag.clear()
        self._on_busy(True)
        try:
            self.status("working", "جاري الاتصال عبر USB…", "نتحقق من تصحيح الأخطاء")
            self.log("— بدء الاتصال عبر USB —")

            if not self.tools.adb_exe:
                self.status("error", "adb غير موجود",
                            "تأكد من وجود adb.exe داخل مجلد scrcpy.")
                return

            self.tools.adb("start-server")
            devices = self.list_devices()
            self._on_devices(devices)

            real_devices = [d for d in devices if "←" not in d]
            if not real_devices:
                self._explain_failure()
                return

            serial = real_devices[0]
            self.log(f"الجهاز المكتشف: {serial}")

            variants = [
                ["-s", serial, *self._scrcpy_options()],
                ["-s", serial],
            ]
            if self._launch_variants(variants, f"بث عبر USB — الجهاز {serial}"):
                return
            self._explain_failure()
        except Exception as exc:  # noqa: BLE001
            self.status("error", "خطأ غير متوقع", str(exc)[:160])
        finally:
            self._on_busy(False)
            self.refresh_devices()

    # ------------------------------------------------------------- Wi-Fi
    def connect_wifi(self, raw_ip: str) -> None:
        self._stop_flag.clear()

        target = parse_target(raw_ip)
        if not target:
            self.status(
                "error",
                "عنوان غير صالح",
                "اكتب عنواناً مثل 192.168.1.25 أو 192.168.1.25:43215 — أرقام ونقاط فقط.",
            )
            return

        host, port = target

        self._on_busy(True)
        try:
            addr = f"{host}:{port}"
            self.status("working", "جاري الاتصال لاسلكياً…", f"محاولة الوصول إلى {addr}")
            self.log(f"— بدء الاتصال اللاسلكي بالعنوان {addr} —")

            if not self.tools.adb_exe:
                self.status("error", "adb غير موجود",
                            "تأكد من وجود adb.exe داخل مجلد scrcpy.")
                return

            self.tools.adb("start-server")
            code, out = self.tools.adb("connect", addr, timeout=20)
            self.log(f"adb connect ⇒ ({code}) {out}")

            joined = out.lower()
            connected = (
                code == 0
                and ("connected to" in joined or "already connected" in joined)
                and "cannot" not in joined
                and "failed" not in joined
            )
            if not connected:
                self.status(
                    "error",
                    "فشل الاتصال اللاسلكي",
                    "تأكد أن الهاتف والحاسوب على نفس شبكة Wi-Fi، وأن الهاتف يقبل التصحيح.",
                )
                return

            self._on_devices(self.list_devices())

            variants = [
                [f"--tcpip={addr}", *self._scrcpy_options()],
                ["-s", addr, *self._scrcpy_options()],
                ["-s", addr],
            ]
            if self._launch_variants(variants, f"بث لاسلكي — {addr}"):
                return
            self._explain_failure()
        except Exception as exc:  # noqa: BLE001
            self.status("error", "خطأ غير متوقع", str(exc)[:160])
        finally:
            self._on_busy(False)

    # ------------------------------------------------------------- تنظيف
    def shutdown(self) -> None:
        """يُنادى عند إغلاق النافذة: إيقاف scrcpy ثم خادم ADB."""
        self.stop()
        try:
            if self.tools.adb_exe:
                self.tools.adb("kill-server", timeout=8)
        except Exception:
            pass


# ==============================================================================
# 5) الواجهة الرسومية (Flet)
# ==============================================================================

def _input_border(radius: int = 12, width: float = 1.0):
    """
    إطار موحّد لحقول الإدخال يعمل مع Flet 1.x (الطريقة الحديثة غير المهجورة).
    حالات: عادي · تحت المؤشر · مركّز.
    """
    return {
        ft.ControlState.DEFAULT: ft.OutlineInputBorder(
            border_radius=radius, side=ft.BorderSide(width=width, color=BORDER)
        ),
        ft.ControlState.HOVERED: ft.OutlineInputBorder(
            border_radius=radius, side=ft.BorderSide(width=width, color="#2E4470")
        ),
        ft.ControlState.FOCUSED: ft.OutlineInputBorder(
            border_radius=radius, side=ft.BorderSide(width=1.6, color=ACCENT)
        ),
    }


def main(page: ft.Page) -> None:
    page.title = WINDOW_TITLE
    page.bgcolor = BG_DEEP
    page.padding = 0
    page.spacing = 0
    page.theme_mode = ft.ThemeMode.DARK
    # واجهة عربية بالكامل: الاتجاه من اليمين إلى اليسار.
    try:
        page.rtl = True
    except Exception:
        pass
    _setup_window(page)

    cfg = load_config()
    tools = Toolchain()

    state = {
        "mode": cfg.get("mode", "usb"),
        "advanced_open": False,
        "busy": False,
        "quality": cfg.get("quality", "high"),
    }

    # ------------------------------------------------------- تحديث آمن للواجهة
    def safe_update() -> None:
        """تحديث الواجهة من أي خيط دون إسقاط التطبيق عند خطأ عابر."""
        try:
            page.update()
        except Exception:
            pass

    # =========================================================== شريط الحالة
    status_icon = ft.Icon(icon=ft.Icons.BOLT, size=18, color=TEXT_MUTED)
    status_title = ft.Text("جاهز للاتصال", size=14, weight=ft.FontWeight.BOLD, color=TEXT_MAIN)
    status_detail = ft.Text(
        "اختر طريقة الاتصال ثم اضغط الزر الرئيسي.",
        size=11, color=TEXT_MUTED, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS,
    )
    status_spinner = ft.ProgressRing(width=16, height=16, stroke_width=2, visible=False,
                                     color="#1A1206")

    status_bar = ft.Container(
        content=ft.Row(
            controls=[
                ft.Container(
                    content=status_icon, width=34, height=34, border_radius=10,
                    bgcolor="#0A1424", alignment=ft.Alignment.CENTER,
                ),
                ft.Column(
                    controls=[status_title, status_detail],
                    spacing=1, expand=True, alignment=ft.MainAxisAlignment.CENTER,
                ),
                status_spinner,
            ],
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding.symmetric(horizontal=14, vertical=11),
        border_radius=14,
        bgcolor=IDLE,
        animate_opacity=200,
    )

    def set_status(kind: str, title: str, detail: str = "") -> None:
        palette = {
            "idle":    (IDLE, TEXT_MAIN, "#D6E0F0", ft.Icons.BOLT,          False),
            "working": (WARN, "#1A1206", "#5A3E06", ft.Icons.HOURGLASS_TOP, True),
            "ok":      (OK,   "#04120A", "#0B3B22", ft.Icons.CHECK_CIRCLE,  False),
            "error":   (ERR,  "#FFFFFF", "#4A1010", ft.Icons.ERROR,         False),
        }
        bg, title_color, detail_color, icon, spin = palette.get(kind, palette["idle"])
        status_bar.bgcolor = bg
        status_title.value = title
        status_title.color = title_color
        status_detail.value = detail or " "
        status_detail.color = detail_color
        status_icon.icon = icon
        status_icon.color = title_color
        status_spinner.visible = spin
        safe_update()

    # ------------------------------------------------------ سجل الأحداث
    log_column = ft.Column(spacing=2, scroll=ft.ScrollMode.AUTO, height=130)

    def add_log(message: str) -> None:
        log_column.controls.append(
            ft.Text(
                f"[{time.strftime('%H:%M:%S')}] {message}",
                size=10, color=TEXT_MUTED, font_family="Consolas",
                selectable=True,
            )
        )
        while len(log_column.controls) > MAX_LOG_LINES:
            log_column.controls.pop(0)
        safe_update()

    log_panel = ft.Container(
        content=log_column,
        padding=10, border_radius=12, bgcolor="#060B14",
        border=ft.Border.all(1, BORDER),
        visible=False,
        height=152,
    )

    # ------------------------------------------------------ بطاقات طريقة الاتصال
    def make_mode_card(mode: str, title: str, subtitle: str, icon_value) -> ft.Container:
        active = state["mode"] == mode
        card = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Container(
                        content=ft.Icon(icon=icon_value, size=22,
                                        color=ACCENT if active else TEXT_MUTED),
                        width=40, height=40, border_radius=11,
                        bgcolor="#0A1424", alignment=ft.Alignment.CENTER,
                    ),
                    ft.Column(
                        controls=[
                            ft.Text(title, size=13, weight=ft.FontWeight.BOLD,
                                    color=TEXT_MAIN if active else TEXT_MUTED),
                            ft.Text(subtitle, size=10, color=TEXT_MUTED),
                        ],
                        spacing=1, expand=True,
                    ),
                    ft.Icon(
                        icon=ft.Icons.RADIO_BUTTON_CHECKED if active else ft.Icons.RADIO_BUTTON_OFF,
                        size=18, color=ACCENT if active else "#3B4A66",
                    ),
                ],
                spacing=10,
            ),
            padding=12,
            border_radius=14,
            bgcolor=CARD_SOFT if active else "#0E1828",
            border=ft.Border.all(1, ACCENT if active else BORDER),
            ink=True,
            on_click=lambda e, m=mode: select_mode(m),
        )
        return card

    mode_cards = {
        "usb": make_mode_card("usb", "كابل USB فائق السرعة", "أداء عالٍ — بدون أي تأخير",
                              ft.Icons.USB),
        "wifi": make_mode_card("wifi", "اتصال لاسلكي Wi-Fi", "حرية الحركة — تأخير طفيف",
                               ft.Icons.WIFI),
    }

    # ------------------------------------------------------ حقل عنوان IP
    ip_field = ft.TextField(
        label="عنوان الهاتف (IP أو IP:PORT)",
        hint_text="مثال: 192.168.1.25 أو 192.168.1.25:43215",
        value=cfg.get("last_ip", ""),
        prefix_icon=ft.Icons.WIFI,
        bgcolor="#0B1424",
        border=_input_border(12),
        color=TEXT_MAIN,
        label_style=ft.TextStyle(color=TEXT_MUTED, size=12),
        text_style=ft.TextStyle(color=TEXT_MAIN, size=15, weight=ft.FontWeight.BOLD),
        keyboard_type=ft.KeyboardType.NUMBER,
        visible=(state["mode"] == "wifi"),
        opacity=1.0 if state["mode"] == "wifi" else 0.0,
        animate_opacity=220,
        on_change=lambda e: persist(),
    )

    hint_wifi = ft.Container(
        content=ft.Row([
            ft.Icon(icon=ft.Icons.INFO_OUTLINE, size=14, color=ACCENT),
            ft.Text(
                "افتح تطبيق MoMoLink Connect على الهاتف ليظهر لك عنوان IP بخط كبير.",
                size=10, color=TEXT_MUTED, expand=True,
            ),
        ], spacing=8),
        visible=(state["mode"] == "wifi"),
        padding=ft.Padding.only(left=4, right=4),
    )

    # ------------------------------------------------------ الخيارات المتقدمة
    adv_max = ft.TextField(
        label="أقصى دقة (فارغ = الأصلية)", value=str(cfg.get("max_size", "")),
        dense=True, bgcolor="#0B1424", border=_input_border(10),
        text_style=ft.TextStyle(color=TEXT_MAIN, size=12),
        label_style=ft.TextStyle(color=TEXT_MUTED, size=10),
        on_change=lambda e: persist(),
    )
    adv_bitrate = ft.TextField(
        label="الجودة (ميغابت/ث)", value=str(cfg.get("bitrate", "16")),
        dense=True, bgcolor="#0B1424", border=_input_border(10),
        text_style=ft.TextStyle(color=TEXT_MAIN, size=12),
        label_style=ft.TextStyle(color=TEXT_MUTED, size=10),
        on_change=lambda e: persist(),
    )
    adv_fps = ft.TextField(
        label="إطارات/ثانية", value=str(cfg.get("max_fps", "60")),
        dense=True, bgcolor="#0B1424", border=_input_border(10),
        text_style=ft.TextStyle(color=TEXT_MAIN, size=12),
        label_style=ft.TextStyle(color=TEXT_MUTED, size=10),
        on_change=lambda e: persist(),
    )

    quality_hint = ft.Text("", size=10, color=TEXT_MUTED)

    def _quality_click(level: str):
        """يضبط الأرقام الثلاثة دفعة واحدة (لا يترك المستخدم يخمّن)."""
        def handler(e=None) -> None:
            preset = QUALITY_PRESETS.get(level, QUALITY_PRESETS["high"])
            state["quality"] = level
            adv_max.value = preset["max_size"]
            adv_bitrate.value = preset["bitrate"]
            adv_fps.value = preset["max_fps"]
            quality_hint.value = (
                f"{preset['max_size']} بكسل · "
                f"{preset['bitrate']} م.ب/ث · {preset['max_fps']} إطار/ث"
            )
            persist()
            safe_update()
        return handler

    def _quality_button(text: str, level: str, primary: bool) -> ft.Button:
        return ft.Button(
            content=ft.Text(
                text, size=11,
                color="#04121B" if primary else TEXT_MAIN,
                weight=ft.FontWeight.BOLD if primary else None,
            ),
            bgcolor=ACCENT if primary else "#16233A",
            height=32,
            expand=True,
            on_click=_quality_click(level),
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
        )

    quality_row = ft.Row([
        _quality_button("⭐ عالية", "high", True),
        _quality_button("متوسطة", "medium", False),
        _quality_button("اقتصادية", "low", False),
    ], spacing=6)
    quality_hint.value = (
        f"{adv_max.value or 'الأبعاد الأصلية'} بكسل · "
        f"{adv_bitrate.value} م.ب/ث · {adv_fps.value} إطار/ث"
    )
    sw_screen_off = ft.Switch(
        label="إبقاء شاشة الهاتف مطفأة أثناء البث",
        label_text_style=ft.TextStyle(color=TEXT_MAIN, size=11),
        value=bool(cfg.get("turn_screen_off", False)),
        active_color=ACCENT, on_change=lambda e: persist(),
    )
    sw_awake = ft.Switch(
        label="إبقاء الهاتف مستيقظاً",
        label_text_style=ft.TextStyle(color=TEXT_MAIN, size=11),
        value=bool(cfg.get("stay_awake", True)),
        active_color=ACCENT, on_change=lambda e: persist(),
    )
    sw_noaudio = ft.Switch(
        label="تعطيل الصوت (أخف على الأجهزة القديمة)",
        label_text_style=ft.TextStyle(color=TEXT_MAIN, size=11),
        value=bool(cfg.get("no_audio", False)),
        active_color=ACCENT, on_change=lambda e: persist(),
    )

    advanced_panel = ft.Container(
        content=ft.Column([
            ft.Row([adv_max, adv_bitrate, adv_fps], spacing=8),
            sw_awake, sw_screen_off, sw_noaudio,
        ], spacing=6),
        visible=False,
        padding=ft.Padding.only(top=8),
    )

    adv_text = ft.Text("خيارات متقدمة", size=11, color=TEXT_MUTED)

    def toggle_advanced(e=None) -> None:
        state["advanced_open"] = not state["advanced_open"]
        advanced_panel.visible = state["advanced_open"]
        adv_text.value = "إخفاء الخيارات المتقدمة" if state["advanced_open"] else "خيارات متقدمة"
        safe_update()

    # ============================================================ المحرّك
    def collect_options() -> dict:
        return {
            "quality": state.get("quality", "high"),
            "max_size": adv_max.value or "",
            "bitrate": adv_bitrate.value or "",
            "max_fps": adv_fps.value or "",
            "turn_screen_off": bool(sw_screen_off.value),
            "stay_awake": bool(sw_awake.value),
            "no_audio": bool(sw_noaudio.value),
        }

    def persist() -> None:
        save_config({
            "mode": state["mode"],
            "last_ip": ip_field.value or "",
            "config_version": CONFIG_VERSION,
            **collect_options(),
        })

    def set_busy(busy: bool) -> None:
        state["busy"] = busy
        connect_btn.disabled = busy
        stop_btn.disabled = not busy
        safe_update()

    def update_devices(devices: list[str]) -> None:
        devices_column.controls.clear()
        if not devices:
            devices_column.controls.append(
                ft.Text("لا يوجد جهاز متصل حالياً.", size=10, color=TEXT_MUTED)
            )
        else:
            for dev in devices:
                warning = "←" in dev
                devices_column.controls.append(
                    ft.Row([
                        ft.Icon(icon=ft.Icons.SMARTPHONE, size=13,
                                color=WARN if warning else OK),
                        ft.Text(dev, size=10, color=WARN if warning else TEXT_MAIN),
                    ], spacing=6)
                )
        safe_update()

    engine = MoMoLinkEngine(tools, set_status, add_log, update_devices, set_busy)

    # ============================================================ الأزرار
    def select_mode(mode: str) -> None:
        if state["busy"]:
            return
        state["mode"] = mode
        is_wifi = mode == "wifi"

        ip_field.visible = is_wifi
        ip_field.opacity = 1.0 if is_wifi else 0.0
        hint_wifi.visible = is_wifi

        for key, card in mode_cards.items():
            active = key == mode
            card.bgcolor = CARD_SOFT if active else "#0E1828"
            card.border = ft.Border.all(1, ACCENT if active else BORDER)
            row = card.content
            icon_box = row.controls[0]
            texts = row.controls[1]
            radio = row.controls[2]
            icon_box.content.color = ACCENT if active else TEXT_MUTED
            texts.controls[0].color = TEXT_MAIN if active else TEXT_MUTED
            radio.icon = ft.Icons.RADIO_BUTTON_CHECKED if active else ft.Icons.RADIO_BUTTON_OFF
            radio.color = ACCENT if active else "#3B4A66"

        persist()
        safe_update()

    def on_connect(e=None) -> None:
        if state["busy"]:
            return
        engine.set_options(collect_options())
        persist()

        if state["mode"] == "usb":
            threading.Thread(target=engine.connect_usb, daemon=True).start()
            return

        ip_value = (ip_field.value or "").strip()
        if not parse_target(ip_value):
            set_status("error", "عنوان غير صالح",
                       "اكتب عنواناً مثل 192.168.1.25 أو 192.168.1.25:43215.")
            try:
                ip_field.focus()
            except Exception:
                pass
            return
        threading.Thread(target=engine.connect_wifi, args=(ip_value,), daemon=True).start()

    def on_stop(e=None) -> None:
        threading.Thread(target=engine.stop, daemon=True).start()

    def on_refresh(e=None) -> None:
        threading.Thread(target=engine.refresh_devices, daemon=True).start()

    def on_toggle_log(e=None) -> None:
        log_panel.visible = not log_panel.visible
        safe_update()

    connect_btn = ft.Button(
        content=ft.Row([
            ft.Icon(icon=ft.Icons.PLAY_ARROW_ROUNDED, size=22, color="#04121B"),
            ft.Text("بث ومشاركة الشاشة الآن | Connect", size=14,
                    weight=ft.FontWeight.BOLD, color="#04121B"),
        ], alignment=ft.MainAxisAlignment.CENTER, spacing=8),
        bgcolor=ACCENT,
        height=54,
        on_click=on_connect,
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=14),
            elevation={ft.ControlState.HOVERED: 8, ft.ControlState.DEFAULT: 2},
        ),
    )

    stop_btn = ft.OutlinedButton(
        content=ft.Row([
            ft.Icon(icon=ft.Icons.STOP_CIRCLE, size=17, color=ERR),
            ft.Text("إيقاف البث", size=12, color=ERR),
        ], alignment=ft.MainAxisAlignment.CENTER, spacing=6),
        disabled=True,
        height=44,
        on_click=on_stop,
        style=ft.ButtonStyle(
            side=ft.BorderSide(width=1, color="#3B1B1B"),
            shape=ft.RoundedRectangleBorder(radius=12),
        ),
    )

    refresh_btn = ft.TextButton(
        content=ft.Row([
            ft.Icon(icon=ft.Icons.REFRESH, size=15, color=TEXT_MUTED),
            ft.Text("كشف الأجهزة", size=11, color=TEXT_MUTED),
        ], spacing=5),
        on_click=on_refresh,
    )

    log_btn = ft.TextButton(
        content=ft.Row([
            ft.Icon(icon=ft.Icons.TERMINAL, size=15, color=TEXT_MUTED),
            ft.Text("سجل الأحداث", size=11, color=TEXT_MUTED),
        ], spacing=5),
        on_click=on_toggle_log,
    )

    devices_column = ft.Column(spacing=3)

    # ============================================================ الترويسة
    tool_state_text = ft.Text(
        f"scrcpy {tools.version()}" if tools.ready else "scrcpy غير موجود",
        size=9, color=OK if tools.ready else ERR,
    )

    header = ft.Container(
        content=ft.Row([
            ft.Container(
                content=ft.Icon(icon=ft.Icons.ROCKET_LAUNCH, size=24, color="#04121B"),
                width=46, height=46, border_radius=14,
                gradient=ft.LinearGradient(
                    begin=ft.Alignment.TOP_LEFT, end=ft.Alignment.BOTTOM_RIGHT,
                    colors=[ACCENT, INDIGO],
                ),
                alignment=ft.Alignment.CENTER,
            ),
            ft.Column([
                ft.Text("MoMoLink Desktop Pro 🚀", size=19,
                        weight=ft.FontWeight.BOLD, color=TEXT_MAIN),
                ft.Text("بث شاشة الأندرويد والتحكم بها من حاسوبك", size=11, color=TEXT_MUTED),
            ], spacing=2, expand=True),
            ft.Container(
                content=ft.Column([
                    ft.Text(f"v{APP_VERSION}", size=9, color=ACCENT),
                    tool_state_text,
                ], spacing=0, alignment=ft.MainAxisAlignment.CENTER),
                padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                border_radius=10, bgcolor="#0A1424",
                border=ft.Border.all(1, BORDER),
            ),
        ], spacing=14, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        padding=ft.Padding.only(left=18, right=18, top=16, bottom=14),
    )

    # ============================================================ الجسم
    body = ft.Column(
        controls=[
            ft.Text("١ · اختر طريقة الاتصال", size=12,
                    weight=ft.FontWeight.BOLD, color=TEXT_MAIN),
            mode_cards["usb"],
            mode_cards["wifi"],
            ip_field,
            hint_wifi,

            ft.Row([
                ft.Text("٢ · جودة الصورة", size=12,
                        weight=ft.FontWeight.BOLD, color=TEXT_MAIN),
                ft.Container(content=quality_hint, expand=True,
                             alignment=ft.Alignment.CENTER_RIGHT),
            ], spacing=8),
            quality_row,

            ft.Row([
                ft.Icon(icon=ft.Icons.TUNE, size=14, color=TEXT_MUTED),
                ft.Container(content=adv_text, ink=True, on_click=toggle_advanced,
                             padding=ft.Padding.symmetric(horizontal=4, vertical=2)),
            ], spacing=4),
            advanced_panel,

            connect_btn,
            ft.Row([refresh_btn, log_btn], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            devices_column,
            log_panel,
            ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Icon(icon=ft.Icons.INFO_OUTLINE, size=14, color=ACCENT),
                        ft.Text("دليل سريع · ٤ خطوات", size=11,
                                weight=ft.FontWeight.BOLD, color=TEXT_MAIN),
                    ], spacing=6),
                    ft.Text("١ · على الهاتف: الإعدادات ← حول الهاتف ← اضغط «رقم البنية» ٧ مرات "
                            "لتفعيل خيارات المطوّر.", size=10, color=TEXT_MUTED),
                    ft.Text("٢ · فعّل «تصحيح أخطاء USB»، وصّل الكابل، ثم اقبل النافذة على الهاتف.",
                            size=10, color=TEXT_MUTED),
                    ft.Text("٣ · للاسلكي: فعّل «التصحيح اللاسلكي» واكتب عنوان IP الظاهر في "
                            "تطبيق MoMoLink Connect.", size=10, color=TEXT_MUTED),
                    ft.Text("٤ · لنقل الملفات وتبادل الحافظة: شغّل 03_Remote_Control\\run_bridge.bat "
                            "ثم امسح رمز QR بكاميرا الهاتف.", size=10, color=TEXT_MUTED),
                ], spacing=5),
                padding=12, border_radius=12, bgcolor="#0A1322",
                border=ft.Border.all(1, BORDER),
            ),
        ],
        spacing=11,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )

    bottom = ft.Container(
        content=ft.Column([
            ft.Container(content=status_bar),
            ft.Container(content=stop_btn, alignment=ft.Alignment.CENTER),
        ], spacing=8),
        padding=ft.Padding.only(left=18, right=18, top=10, bottom=14),
        bgcolor=BG_PANEL,
        border=ft.Border.only(top=ft.BorderSide(width=1, color=BORDER)),
    )

    page.add(
        ft.Container(
            content=ft.Column([
                header,
                ft.Divider(height=1, color=BORDER),
                ft.Container(content=body, expand=True,
                             padding=ft.Padding.only(left=18, right=18, top=14, bottom=14)),
                bottom,
            ], spacing=0, expand=True),
            expand=True,
            bgcolor=BG_DEEP,
        )
    )

    # ============================================================ الإقلاع
    if not tools.ready:
        set_status(
            "error", "لم يتم العثور على scrcpy",
            "تأكد أن مجلد scrcpy موجود بجانب التطبيق: 01_Desktop_MoMoLink\\scrcpy",
        )
        add_log("مسارات البحث عن scrcpy:")
        for path in _tool_dirs():
            add_log(f"   • {path}")
    else:
        add_log(f"scrcpy: {tools.scrcpy_exe}")
        add_log(f"adb: {tools.adb_exe or 'غير موجود'}")
        add_log(f"مجلد العمل: {tools.workdir}")
        add_log("جاهز — اختر USB أو Wi-Fi ثم اضغط زر الاتصال.")
        threading.Thread(target=engine.refresh_devices, daemon=True).start()

    def on_close(e=None) -> None:
        try:
            engine.shutdown()
        except Exception:
            pass

    page.on_close = on_close

    # نضمن ظهور النافذة في نسخة .exe (عطل PyInstaller المعروف — موثَّق أعلى الدالة).
    if getattr(sys, "frozen", False):
        _force_show_window("MoMoLink Desktop Pro")


def _force_show_window(window_title_prefix: str) -> None:
    """
    إصلاح عطل حقيقي خاص بـ PyInstaller + Flet على ويندوز:
    عند بناء التطبيق بصيغة --onefile --windowed فإن مُحمّل PyInstaller يمرّر
    حالة نافذة "مخفية" (SW_HIDE) إلى العمليات الابنة، فيُنشئ عميل Flet نافذته
    لكنها تبقى غير مرئية (IsWindowVisible = False) رغم أن التطبيق يعمل.

    الحل: نبحث عن نافذة التطبيق بأسمائها ونُظهرها نحن عبر Win32.
    يعمل في خيط منفصل وبصمت، ولا يفعل شيئاً إن كانت النافذة ظاهرة أصلاً.
    """
    if not IS_WINDOWS:
        return

    def worker() -> None:
        try:
            import ctypes
            from ctypes import wintypes
        except Exception:
            return

        user32 = ctypes.windll.user32
        SW_SHOW = 5
        SW_RESTORE = 9
        found = {"done": False}

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

        def _callback(hwnd, _lparam):
            try:
                if not user32.IsWindowVisible(hwnd):
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length:
                        buffer = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buffer, length + 1)
                        if buffer.value.startswith(window_title_prefix):
                            user32.ShowWindow(hwnd, SW_RESTORE)
                            user32.ShowWindow(hwnd, SW_SHOW)
                            user32.SetForegroundWindow(hwnd)
                            found["done"] = True
            except Exception:
                pass
            return True

        callback = WNDENUMPROC(_callback)
        # نُكرّر المحاولة ~20 ثانية كحد أقصى: النافذة قد تتأخر في الإنشاء.
        for _ in range(80):
            if found["done"]:
                return
            try:
                user32.EnumWindows(callback, 0)
            except Exception:
                return
            time.sleep(0.25)

    threading.Thread(target=worker, daemon=True).start()


def _setup_window(page: ft.Page) -> None:
    try:
        page.window.width = 560
        page.window.height = 700
        page.window.min_width = 460
        page.window.min_height = 560
        page.window.resizable = True
    except Exception:
        pass


# ==============================================================================
# 6) نقطة الدخول
# ==============================================================================

if __name__ == "__main__":
    # Flet 1.x يستخدم ft.run ، والإصدارات الأقدم ft.app — ندعم الاثنين.
    if hasattr(ft, "run"):
        ft.run(main)
    else:  # pragma: no cover
        ft.app(target=main)
