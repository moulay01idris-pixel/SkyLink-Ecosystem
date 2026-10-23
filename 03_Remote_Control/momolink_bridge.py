# -*- coding: utf-8 -*-
"""
================================================================================
 MoMoLink Remote Bridge  —  v1.0.0
--------------------------------------------------------------------------------
جسر عربي بين حاسوبك وهاتفك، يعمل داخل شبكة البيت فقط:

  1) الملفات   : تصفّح مجلدات الحاسوب، تنزيل، رفع بالسحب، مجلد جديد، حذف آمن.
  2) الحافظة   : انسخ نصاً على الهاتف (ChatGPT, Facebook...) وألصقه على الحاسوب،
                 والعكس — مع سجلّ لآخر 40 عنصراً.
  3) الاتصال   : QR Code تمسحه بكاميرا الهاتف فيفتح الصفحة فوراً.

المبادئ الهندسية:
   * رمز وصول إجباري (Token) — لا وصول بلا رمز حتى داخل الشبكة.
   * منع الخروج عن المجلدات المسموح بها (Path Traversal) عبر resolve + is_relative_to.
   * الحذف لا يمحو: يُعاد تسمية الملف (اسم.deleted-تاريخ) ⇒ قابل للاسترجاع.
   * حدّ أقصى لحجم الرفع، وقبول الطلب يُرفض فوراً عند تجاوزه.
   * إن تعطّل شيء في الحافظة لا يسقط الخادم (كل عملية محروسة).
   * لا إرسال أي بيانات إلى أي خادم خارجي — كل شيء داخل جهازك.

 التشغيل:
   python momolink_bridge.py
   أو: run_bridge.bat   (يجهّز كل شيء تلقائياً)
================================================================================
"""

from __future__ import annotations

import asyncio
import ctypes
import json
import os
import platform
import secrets
import shutil
import socket
import sys
import threading
import time
import webbrowser
from ctypes import wintypes
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
)

# ==============================================================================
# 0) إعدادات عامة
# ==============================================================================

APP_NAME = "MoMoLink Remote"
APP_VERSION = "1.0.0"
PORT = 8756

IS_WINDOWS = os.name == "nt"
CLIP_HISTORY_LIMIT = 40


def _force_utf8_console() -> None:
    """
    طرفية ويندوز قد تعمل بترميز cp1252/cp437 ⇒ طباعة أي حرف عربي تُسقط البرنامج.
    الحل المزدوج: نضبط ترميز الطرفية نفسها على UTF-8 عبر Win32، ثم نُعيد ضبط
    مجرى الإخراج. وإن فشل كل شيء نستبدل الحروف بدل الانهيار.
    """
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
    """طباعة لا تسقط أبداً — حتى لو كانت الطرفية لا تدعم العربية."""
    try:
        print(text, flush=True)
    except Exception:
        try:
            enc = getattr(sys.stdout, "encoding", None) or "ascii"
            print(text.encode(enc, "replace").decode(enc, "replace"), flush=True)
        except Exception:
            pass


_force_utf8_console()
MAX_UPLOAD_MB = 2048          # 2 غيغابايت للملف الواحد
MAX_CLIP_CHARS = 200_000      # حماية من نص ضخم يُغرق الحافظة

CONFIG_DIR = (
    Path(os.environ.get("APPDATA", Path.home())) / "MoMoLink"
    if IS_WINDOWS
    else Path.home() / ".momolink"
)
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

CONFIG_FILE = CONFIG_DIR / "bridge_config.json"
HISTORY_FILE = CONFIG_DIR / "clipboard_history.json"

#: الألوان (نفس هوية تطبيق الحاسوب)
C_BG = "#070C16"
C_PANEL = "#0E1626"
C_CARD = "#131E33"
C_BORDER = "#22304D"
C_TEXT = "#E9EFFA"
C_MUTED = "#8DA1C1"
C_ACCENT = "#22D3EE"
C_OK = "#22C55E"
C_WARN = "#F59E0B"
C_ERR = "#EF4444"


# ==============================================================================
# 1) الإعدادات والرمز السري
# ==============================================================================

def _default_roots() -> list[str]:
    """المجلدات المسموح بفتحها من الهاتف (يمكن تعديلها في ملف الإعدادات)."""
    home = Path.home()
    candidates = [
        home / "Desktop",
        home / "Documents",
        home / "Downloads",
        home / "Pictures",
        home / "Videos",
        home / "Music",
    ]
    if IS_WINDOWS:
        for letter in "DEFGH":
            drive = Path(f"{letter}:\\")
            try:
                if drive.exists():
                    candidates.append(drive)
            except OSError:
                continue
    found: list[str] = []
    for path in candidates:
        try:
            if path.is_dir():
                found.append(str(path))
        except OSError:
            continue
    return found


def load_config() -> dict:
    """
    يقرأ الإعدادات، ويولّد رمز وصول عشوائياً في أول تشغيل.
    الرمز = 24 حرفاً عشوائياً آمن التشفير (secrets) — لا يمكن تخمينه.
    """
    cfg: dict = {
        "token": "",
        "port": PORT,
        "roots": _default_roots(),
        "max_upload_mb": MAX_UPLOAD_MB,
    }
    try:
        if CONFIG_FILE.is_file():
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8-sig"))
            if isinstance(data, dict):
                for key in cfg:
                    if key in data and data[key] not in (None, "", []):
                        cfg[key] = data[key]
    except Exception:
        pass

    changed = False
    if not cfg.get("token") or len(str(cfg["token"])) < 16:
        cfg["token"] = secrets.token_urlsafe(18)   # ~24 حرفاً
        changed = True
    if not cfg.get("roots"):
        cfg["roots"] = _default_roots()
        changed = True

    if changed:
        try:
            tmp = CONFIG_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, CONFIG_FILE)
        except Exception:
            pass
    return cfg


CONFIG = load_config()
TOKEN: str = str(CONFIG["token"])
PORT = int(CONFIG.get("port", PORT))
MAX_UPLOAD_BYTES = int(CONFIG.get("max_upload_mb", MAX_UPLOAD_MB)) * 1024 * 1024

#: جذور مسموحة (محلولة مسبقاً للمقارنة الآمنة)
ROOTS: list[Path] = []
for raw in CONFIG.get("roots", []):
    try:
        resolved = Path(raw).expanduser().resolve()
        if resolved.is_dir():
            ROOTS.append(resolved)
    except Exception:
        continue


# ==============================================================================
# 2) الحافظة عبر Win32 (بلا أي مكتبة خارجية)
# ==============================================================================

class WindowsClipboard:
    """
    قراءة/كتابة حافظة ويندوز مباشرة عبر user32/kernel32.
    تعمل مع العربية والإيموجي لأنها تستعمل CF_UNICODETEXT.
    """

    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002
    GMEM_ZEROINIT = 0x0040

    def __init__(self) -> None:
        self.available = False
        if not IS_WINDOWS:
            return
        try:
            self.user32 = ctypes.windll.user32
            self.kernel32 = ctypes.windll.kernel32

            # ضبط الأنواع ضروري على 64-بت وإلا قُصّت المؤشرات إلى 32 بت.
            self.user32.GetClipboardData.restype = wintypes.HANDLE
            self.user32.GetClipboardData.argtypes = [wintypes.UINT]
            self.user32.SetClipboardData.restype = wintypes.HANDLE
            self.user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
            self.user32.OpenClipboard.argtypes = [wintypes.HWND]
            self.user32.EmptyClipboard.restype = wintypes.BOOL
            self.kernel32.GlobalLock.restype = ctypes.c_void_p
            self.kernel32.GlobalLock.argtypes = [wintypes.HANDLE]
            self.kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
            self.kernel32.GlobalAlloc.restype = wintypes.HANDLE
            self.kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
            self.kernel32.GlobalFree.argtypes = [wintypes.HANDLE]
            self.available = True
        except Exception:
            self.available = False

    def get(self) -> str:
        if not self.available:
            return ""
        # الحافظة قد تكون مشغولة بلحظة من برنامج آخر ⇒ نعيد المحاولة بسرعة.
        for _ in range(5):
            try:
                if not self.user32.OpenClipboard(None):
                    time.sleep(0.03)
                    continue
                try:
                    handle = self.user32.GetClipboardData(self.CF_UNICODETEXT)
                    if not handle:
                        return ""
                    pointer = self.kernel32.GlobalLock(handle)
                    if not pointer:
                        return ""
                    try:
                        return ctypes.wstring_at(pointer)
                    finally:
                        self.kernel32.GlobalUnlock(handle)
                finally:
                    self.user32.CloseClipboard()
            except Exception:
                time.sleep(0.03)
        return ""

    def set(self, text: str) -> bool:
        if not self.available:
            return False
        buffer = ctypes.create_unicode_buffer(text)
        size = ctypes.sizeof(buffer)
        for _ in range(5):
            try:
                if not self.user32.OpenClipboard(None):
                    time.sleep(0.03)
                    continue
                try:
                    self.user32.EmptyClipboard()
                    handle = self.kernel32.GlobalAlloc(
                        self.GMEM_MOVEABLE | self.GMEM_ZEROINIT, size
                    )
                    if not handle:
                        return False
                    pointer = self.kernel32.GlobalLock(handle)
                    if not pointer:
                        self.kernel32.GlobalFree(handle)
                        return False
                    ctypes.memmove(pointer, buffer, size)
                    self.kernel32.GlobalUnlock(handle)
                    if not self.user32.SetClipboardData(self.CF_UNICODETEXT, handle):
                        self.kernel32.GlobalFree(handle)
                        return False
                    return True
                finally:
                    self.user32.CloseClipboard()
            except Exception:
                time.sleep(0.03)
        return False


CLIP = WindowsClipboard()


# ==============================================================================
# 3) سجلّ الحافظة (في الذاكرة + ملف للاستمرارية)
# ==============================================================================

def _load_history() -> list[dict]:
    try:
        if HISTORY_FILE.is_file():
            data = json.loads(HISTORY_FILE.read_text(encoding="utf-8-sig"))
            if isinstance(data, list):
                return [x for x in data if isinstance(x, dict)][:CLIP_HISTORY_LIMIT]
    except Exception:
        pass
    return []


def _save_history() -> None:
    try:
        tmp = HISTORY_FILE.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(HISTORY, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        os.replace(tmp, HISTORY_FILE)
    except Exception:
        pass


HISTORY: list[dict] = _load_history()


def history_add(text: str, source: str) -> None:
    """يضيف نصاً للسجل مع منع التكرار المتتالي."""
    text = (text or "")[:MAX_CLIP_CHARS]
    if not text.strip():
        return
    if HISTORY and HISTORY[0].get("text") == text:
        return
    HISTORY.insert(
        0,
        {
            "text": text,
            "source": source,
            "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
    )
    del HISTORY[CLIP_HISTORY_LIMIT:]
    _save_history()


# ==============================================================================
# 4) أمان المسارات
# ==============================================================================

def safe_path(raw: str) -> Optional[Path]:
    """
    يُرجع مساراً محلولاً داخل المجلدات المسموحة، أو None.
    هذا هو الحاجز ضد ../../ والإشارات الرمزية الخبيثة.
    """
    if not raw:
        return None
    try:
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            return None
        resolved = candidate.resolve()
    except Exception:
        return None

    for root in ROOTS:
        try:
            if resolved == root or root in resolved.parents:
                return resolved
        except Exception:
            continue
    return None


def human_size(num: int) -> str:
    value = float(num)
    for unit in ("بايت", "ك.ب", "م.ب", "غ.ب", "ت.ب"):
        if value < 1024 or unit == "ت.ب":
            if unit == "بايت":
                return f"{int(value)} بايت"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} ت.ب"


def lan_ip() -> str:
    """عنوان الحاسوب داخل شبكة البيت (بلا إرسال أي بيانات)."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("8.8.8.8", 53))
            return sock.getsockname()[0]
        finally:
            sock.close()
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"


# ==============================================================================
# 5) التطبيق (FastAPI)
# ==============================================================================

app = FastAPI(title=f"{APP_NAME} {APP_VERSION}", docs_url=None, redoc_url=None)


def _authorized(request: Request) -> bool:
    cookie = request.cookies.get("momolink_token", "")
    query = request.query_params.get("t", "")
    return secrets.compare_digest(cookie, TOKEN) or secrets.compare_digest(query, TOKEN)


@app.middleware("http")
async def guard(request: Request, call_next):
    """حاجز واحد لكل المسارات: بلا رمز صحيح = لا شيء."""
    path = request.url.path
    if path in ("/health",):
        return await call_next(request)

    if path == "/" and request.query_params.get("t"):
        # دخول أول عبر QR أو رابط فيه رمز ⇒ نحفظه في كوكي وننظّف الرابط.
        if secrets.compare_digest(request.query_params["t"], TOKEN):
            response = RedirectResponse(url="/", status_code=303)
            response.set_cookie(
                "momolink_token", TOKEN, max_age=60 * 60 * 24 * 30,
                httponly=True, samesite="lax",
            )
            return response

    if _authorized(request):
        return await call_next(request)

    return HTMLResponse(_locked_page(), status_code=401)


def _locked_page() -> str:
    return _page(
        """
        <div class="card center">
          <div class="big">🔒</div>
          <h2>الرمز غير صحيح</h2>
          <p class="muted">افتح الرابط الكامل مع رمز الوصول، أو امسح رمز QR من شاشة الحاسوب.</p>
          <p class="muted small">الرابط موجود في نافذة التشغيل على الحاسوب.</p>
        </div>
        """,
        title="مقفول",
    )


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"ok": True, "app": APP_NAME, "version": APP_VERSION})


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return HTMLResponse(_page(_main_html(), title=APP_NAME))


@app.get("/qr.png")
async def qr_png(request: Request) -> Response:
    """QR Code لرابط الدخول — نمسحه بكاميرا الهاتف فيفتح مباشرة."""
    url = f"http://{lan_ip()}:{PORT}/?t={TOKEN}"
    try:
        import io

        import qrcode

        img = qrcode.make(url)
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return Response(content=buffer.getvalue(), media_type="image/png")
    except Exception:
        return Response(status_code=503, content=b"QR unavailable")


@app.get("/api/info")
async def api_info() -> JSONResponse:
    return JSONResponse(
        {
            "app": APP_NAME,
            "version": APP_VERSION,
            "pc": platform.node(),
            "ip": lan_ip(),
            "port": PORT,
            "roots": [str(r) for r in ROOTS],
            "clipboard": CLIP.available,
            "history_count": len(HISTORY),
            "max_upload_mb": MAX_UPLOAD_BYTES // (1024 * 1024),
        }
    )


# ------------------------------------------------------------------ الملفات

@app.get("/api/ls")
async def api_ls(path: str = "") -> JSONResponse:
    # بلا مسار ⇒ نبدأ من أول مجلد متاح (بدل رفض الطلب)
    if not path and ROOTS:
        path = str(ROOTS[0])
    target = safe_path(path)
    if target is None:
        return JSONResponse({"ok": False, "error": "مسار غير مسموح"}, status_code=403)
    if not target.exists():
        return JSONResponse({"ok": False, "error": "المسار غير موجود"}, status_code=404)

    if target.is_file():
        return JSONResponse(
            {
                "ok": True,
                "kind": "file",
                "path": str(target),
                "name": target.name,
                "size": human_size(target.stat().st_size),
            }
        )

    try:
        entries = []
        for child in target.iterdir():
            try:
                stat = child.stat()
                is_dir = child.is_dir()
                entries.append(
                    {
                        "name": child.name,
                        "path": str(child),
                        "dir": is_dir,
                        "size": "" if is_dir else human_size(stat.st_size),
                        "mtime": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                    }
                )
            except (OSError, PermissionError):
                continue
        # المجلدات أولاً ثم الملفات، كل منها أبجدياً
        entries.sort(key=lambda e: (not e["dir"], e["name"].lower()))
    except PermissionError:
        return JSONResponse({"ok": False, "error": "لا توجد صلاحية لقراءة هذا المجلد"}, status_code=403)

    parent = ""
    for root in ROOTS:
        if target != root and root in target.parents:
            parent = str(target.parent)
            break

    return JSONResponse(
        {
            "ok": True,
            "kind": "dir",
            "path": str(target),
            "parent": parent,
            "count": len(entries),
            "entries": entries,
            "roots": [{"name": p.name or str(p), "path": str(p)} for p in ROOTS],
        }
    )


@app.get("/api/download")
async def api_download(path: str = "") -> Response:
    target = safe_path(path)
    if target is None or not target.is_file():
        return JSONResponse({"ok": False, "error": "ملف غير موجود"}, status_code=404)
    return FileResponse(str(target), filename=target.name)


@app.put("/api/upload")
async def api_upload(request: Request, dir: str = "", name: str = "") -> JSONResponse:
    folder = safe_path(dir)
    if folder is None or not folder.is_dir():
        return JSONResponse({"ok": False, "error": "مجلد غير صالح"}, status_code=403)

    clean_name = Path(name or "").name      # يقتل أي ../../ في اسم الملف
    if not clean_name or clean_name in (".", ".."):
        return JSONResponse({"ok": False, "error": "اسم ملف غير صالح"}, status_code=400)

    destination = safe_path(str(folder / clean_name))
    if destination is None:
        return JSONResponse({"ok": False, "error": "مسار غير مسموح"}, status_code=403)

    # في حال وجود ملف بنفس الاسم: نضيف رقماً بدل الكتابة فوقه
    if destination.exists():
        stem, suffix = destination.stem, destination.suffix
        for index in range(1, 1000):
            candidate = destination.with_name(f"{stem} ({index}){suffix}")
            if not candidate.exists():
                destination = candidate
                break

    written = 0
    try:
        with open(destination, "wb") as handle:
            async for chunk in request.stream():
                written += len(chunk)
                if written > MAX_UPLOAD_BYTES:
                    handle.close()
                    try:
                        destination.unlink()
                    except Exception:
                        pass
                    return JSONResponse(
                        {"ok": False, "error": f"الملف أكبر من {MAX_UPLOAD_BYTES // (1024*1024)} م.ب"},
                        status_code=413,
                    )
                handle.write(chunk)
    except Exception as exc:
        return JSONResponse({"ok": False, "error": f"فشل الرفع: {exc}"}, status_code=500)

    return JSONResponse(
        {
            "ok": True,
            "path": str(destination),
            "name": destination.name,
            "size": human_size(written),
        }
    )


@app.post("/api/mkdir")
async def api_mkdir(payload: dict[str, Any]) -> JSONResponse:
    parent = safe_path(str(payload.get("dir", "")))
    name = Path(str(payload.get("name", ""))).name
    if parent is None or not parent.is_dir() or not name:
        return JSONResponse({"ok": False, "error": "طلب غير صالح"}, status_code=400)
    target = parent / name
    try:
        target.mkdir(parents=False, exist_ok=False)
        return JSONResponse({"ok": True, "path": str(target)})
    except FileExistsError:
        return JSONResponse({"ok": False, "error": "المجلد موجود مسبقاً"}, status_code=409)
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


@app.post("/api/delete")
async def api_delete(payload: dict[str, Any]) -> JSONResponse:
    """
    حذف آمن: لا يُمحى الملف — يُعاد تسميته إلى <الاسم>.deleted-YYYYmmdd-HHMMSS
    فيبقى قابلاً للاسترجاع إن حذفته بالخطأ.
    """
    target = safe_path(str(payload.get("path", "")))
    if target is None or not target.exists():
        return JSONResponse({"ok": False, "error": "العنصر غير موجود"}, status_code=404)
    if target in ROOTS:
        return JSONResponse({"ok": False, "error": "لا يمكن حذف مجلد جذر"}, status_code=400)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    new_name = target.with_name(f"{target.name}.deleted-{stamp}")
    try:
        target.rename(new_name)
        return JSONResponse({"ok": True, "renamed_to": str(new_name)})
    except Exception as exc:
        return JSONResponse({"ok": False, "error": f"تعذّر الحذف: {exc}"}, status_code=500)


# ------------------------------------------------------------------ الحافظة

@app.get("/api/clip")
async def api_clip_get() -> JSONResponse:
    current = CLIP.get()
    return JSONResponse(
        {
            "ok": True,
            "available": CLIP.available,
            "text": current,
            "length": len(current),
            "history": HISTORY[:20],
        }
    )


@app.post("/api/clip")
async def api_clip_set(payload: dict[str, Any]) -> JSONResponse:
    text = str(payload.get("text", ""))[:MAX_CLIP_CHARS]
    if not text:
        return JSONResponse({"ok": False, "error": "النص فارغ"}, status_code=400)
    if not CLIP.available:
        return JSONResponse({"ok": False, "error": "الحافظة غير متاحة"}, status_code=503)
    if not CLIP.set(text):
        return JSONResponse({"ok": False, "error": "تعذّر الكتابة في الحافظة"}, status_code=500)
    history_add(text, source="الهاتف")
    return JSONResponse({"ok": True, "length": len(text)})


@app.post("/api/clip-capture")
async def api_clip_capture() -> JSONResponse:
    """يجلب ما هو موجود الآن في حافظة الحاسوب ويضيفه للسجل."""
    text = CLIP.get()
    if text:
        history_add(text, source="الحاسوب")
    return JSONResponse({"ok": True, "text": text, "length": len(text)})


# ==============================================================================
# 6) الواجهة (HTML + CSS + JS بلا أي مكتبة خارجية)
# ==============================================================================

def _page(body: str, title: str = APP_NAME) -> str:
    return (
        """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#070C16">
<title>__TITLE__</title>
<style>
:root{
  --bg:#070C16; --panel:#0E1626; --card:#131E33; --border:#22304D;
  --text:#E9EFFA; --muted:#8DA1C1; --accent:#22D3EE; --ok:#22C55E;
  --warn:#F59E0B; --err:#EF4444;
}
*{box-sizing:border-box; -webkit-tap-highlight-color:transparent}
html,body{margin:0;padding:0;background:var(--bg);color:var(--text);
  font-family:"Segoe UI",Tahoma,Arial,sans-serif;font-size:15px}
body{padding-bottom:env(safe-area-inset-bottom)}
header{position:sticky;top:0;z-index:20;background:rgba(7,12,22,.93);
  backdrop-filter:blur(10px);border-bottom:1px solid var(--border);padding:12px 14px}
.brand{display:flex;align-items:center;gap:10px}
.logo{width:38px;height:38px;border-radius:11px;display:grid;place-items:center;
  background:linear-gradient(135deg,#22D3EE,#6366F1);font-size:19px}
h1{font-size:17px;margin:0;font-weight:700}
.sub{font-size:11px;color:var(--muted);margin-top:2px}
.tabs{display:flex;gap:8px;padding:12px 14px 0}
.tab{flex:1;text-align:center;padding:11px 8px;border-radius:12px;border:1px solid var(--border);
  background:var(--card);color:var(--muted);font-size:13px;font-weight:600;cursor:pointer}
.tab.on{background:#182742;color:var(--text);border-color:var(--accent)}
main{padding:14px}
.card{background:var(--card);border:1px solid var(--border);border-radius:16px;
  padding:14px;margin-bottom:12px}
.card.center{text-align:center}
.big{font-size:46px;line-height:1.1;margin:8px 0}
.muted{color:var(--muted);font-size:13px;line-height:1.7}
.small{font-size:11px}
h2{font-size:16px;margin:6px 0}
.crumb{display:flex;gap:6px;align-items:center;background:#0B1424;border:1px solid var(--border);
  border-radius:11px;padding:9px 11px;font-size:11px;color:var(--muted);overflow:auto;
  white-space:nowrap;direction:ltr;text-align:left}
.row{display:flex;align-items:center;gap:10px;padding:11px 10px;border-radius:12px;
  border:1px solid transparent}
.row:active{background:#182742}
.row+.row{border-top:1px solid #1A2740}
.ico{width:34px;height:34px;border-radius:9px;display:grid;place-items:center;
  background:#0B1424;font-size:16px;flex:0 0 auto}
.name{flex:1;min-width:0}
.name b{display:block;font-weight:600;font-size:13px;white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis}
.name span{font-size:10px;color:var(--muted)}
.btn{border:0;border-radius:12px;padding:12px 14px;font-size:14px;font-weight:700;
  font-family:inherit;cursor:pointer;display:inline-flex;align-items:center;
  justify-content:center;gap:7px;width:100%}
.btn.primary{background:var(--accent);color:#04121B}
.btn.ghost{background:#0B1424;color:var(--text);border:1px solid var(--border)}
.btn.ok{background:var(--ok);color:#04120A}
.btn.danger{background:#2A1116;color:#FF8A8A;border:1px solid #4A1B22}
.btn:disabled{opacity:.5}
.sm{padding:8px 10px;font-size:12px;width:auto;border-radius:10px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:9px}
textarea{width:100%;min-height:130px;background:#0B1424;border:1px solid var(--border);
  border-radius:12px;color:var(--text);padding:12px;font-family:inherit;font-size:14px;
  resize:vertical;line-height:1.7}
textarea:focus{outline:0;border-color:var(--accent)}
input[type=text]{width:100%;background:#0B1424;border:1px solid var(--border);border-radius:11px;
  color:var(--text);padding:11px 12px;font-family:inherit;font-size:14px}
input[type=text]:focus{outline:0;border-color:var(--accent)}
.hist{background:#0B1424;border:1px solid var(--border);border-radius:11px;padding:10px;
  margin-top:8px;font-size:12px;color:var(--muted);max-height:96px;overflow:hidden;
  display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;line-height:1.6}
.hrow{display:flex;gap:6px;align-items:flex-start}
.hrow .hist{flex:1}
.progress{height:7px;background:#0B1424;border-radius:99px;overflow:hidden;margin-top:8px}
.progress>div{height:100%;width:0;background:linear-gradient(90deg,#22D3EE,#6366F1);
  transition:width .18s}
.pill{display:inline-block;padding:4px 9px;border-radius:99px;font-size:10px;
  background:#0B1424;border:1px solid var(--border);color:var(--muted)}
.toast{position:fixed;left:14px;right:14px;bottom:calc(18px + env(safe-area-inset-bottom));
  background:#111E33;border:1px solid var(--accent);color:var(--text);padding:13px 15px;
  border-radius:13px;font-size:13px;text-align:center;z-index:99;opacity:0;
  transform:translateY(16px);transition:.22s;pointer-events:none}
.toast.show{opacity:1;transform:translateY(0)}
.empty{text-align:center;padding:26px 10px;color:var(--muted);font-size:13px}
.qr{width:190px;height:190px;border-radius:14px;background:#fff;padding:8px;
  display:block;margin:12px auto}
a{color:var(--accent);text-decoration:none}
footer{text-align:center;padding:18px 14px 26px;color:#5B6B88;font-size:10px}
</style>
</head>
<body>
__BODY__
<div class="toast" id="toast"></div>
<footer>MoMoLink Remote __VERSION__ · كل شيء داخل شبكتك المحلية · لا يخرج أي بيانات</footer>
<script>
__SCRIPT__
</script>
</body>
</html>"""
        .replace("__TITLE__", title)
        .replace("__BODY__", body)
        .replace("__VERSION__", APP_VERSION)
        .replace("__SCRIPT__", SCRIPT)
    )


def _main_html() -> str:
    return f"""
<header>
  <div class="brand">
    <div class="logo">🚀</div>
    <div style="flex:1">
      <h1>{APP_NAME}</h1>
      <div class="sub">حاسوبك في جيبك · <span id="pcname">…</span></div>
    </div>
  </div>
</header>

<div class="tabs">
  <div class="tab on" id="tab-files" onclick="switchTab('files')">📁 الملفات</div>
  <div class="tab" id="tab-clip" onclick="switchTab('clip')">📋 الحافظة</div>
  <div class="tab" id="tab-info" onclick="switchTab('info')">📶 الاتصال</div>
</div>

<main>
  <!-- ================= الملفات ================= -->
  <section id="pane-files">
    <div class="card">
      <div class="crumb" id="crumb">…</div>
      <div class="grid2" style="margin-top:10px">
        <button class="btn primary" onclick="pickFiles()">⬆️ رفع ملفات</button>
        <button class="btn ghost" onclick="newFolder()">📁 مجلد جديد</button>
      </div>
      <input type="file" id="fileinput" multiple style="display:none"
             onchange="uploadFiles(this.files); this.value=''">
      <div class="progress" id="prog" style="display:none"><div id="progbar"></div></div>
      <div class="muted small" id="upstatus" style="margin-top:7px"></div>
    </div>
    <div class="card" id="listcard">
      <div class="empty">جارٍ التحميل…</div>
    </div>
    <div class="card">
      <div class="muted small" style="margin-bottom:8px">المجلدات المتاحة على الحاسوب</div>
      <div id="roots"></div>
    </div>
  </section>

  <!-- ================= الحافظة ================= -->
  <section id="pane-clip" style="display:none">
    <div class="card">
      <h2>📤 من الهاتف ← إلى الحاسوب</h2>
      <p class="muted small">انسخ النص من ChatGPT أو فيسبوك، الصقه هنا، ثم اضغط الزر.
      سيصبح جاهزاً للصق على الحاسوب مباشرة.</p>
      <textarea id="cliptext" placeholder="الصق النص هنا…"></textarea>
      <button class="btn ok" style="margin-top:10px" onclick="sendClip()">
        ⬅️ أرسل إلى حافظة الحاسوب
      </button>
    </div>

    <div class="card">
      <h2>📥 من الحاسوب ← إلى الهاتف</h2>
      <p class="muted small">ما نسخته على الحاسوب يظهر هنا تلقائياً كل 3 ثوانٍ.</p>
      <textarea id="pcclip" readonly placeholder="(الحافظة فارغة)"></textarea>
      <div class="grid2" style="margin-top:10px">
        <button class="btn primary" onclick="copyPcClip()">📋 انسخ</button>
        <button class="btn ghost" onclick="refreshPcClip()">🔄 تحديث</button>
      </div>
    </div>

    <div class="card">
      <h2>🕘 السجل</h2>
      <div class="muted small">آخر 20 عنصراً — اضغط «لصق» لإعادة أي واحد إلى الحاسوب.</div>
      <div id="history" style="margin-top:10px"></div>
    </div>
  </section>

  <!-- ================= الاتصال ================= -->
  <section id="pane-info" style="display:none">
    <div class="card center">
      <h2>امسح الرمز بكاميرا الهاتف</h2>
      <p class="muted small">يفتح نفس الصفحة على هاتف آخر بدون كتابة أي شيء.</p>
      <img class="qr" src="/qr.png" alt="QR">
      <div id="infoline" class="muted small"></div>
    </div>
    <div class="card">
      <h2>🔐 الأمان</h2>
      <p class="muted small">هذه الصفحة لا تعمل إلا برمز الوصول المحفوظ في حاسوبك،
      ولا تُفتح من خارج شبكة البيت. الحذف لا يمحو الملفات — يُعيد تسميتها
      بـ<span class="pill">.deleted-التاريخ</span> فتُسترجع بسهولة.</p>
    </div>
  </section>
</main>
"""


SCRIPT = r"""
let ROOTS = [];
let CURRENT = "";

function toast(msg, ms) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.classList.add('show');
  clearTimeout(window.__t);
  window.__t = setTimeout(() => el.classList.remove('show'), ms || 2400);
}

function switchTab(name) {
  for (const t of ['files', 'clip', 'info']) {
    document.getElementById('pane-' + t).style.display = (t === name) ? '' : 'none';
    document.getElementById('tab-' + t).classList.toggle('on', t === name);
  }
  if (name === 'clip') refreshPcClip();
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

/* ---------------------------- الملفات ---------------------------- */

async function loadInfo() {
  try {
    const r = await fetch('/api/info'); const d = await r.json();
    document.getElementById('pcname').textContent = d.pc + ' · ' + d.ip + ':' + d.port;
    document.getElementById('infoline').textContent =
      d.pc + ' — ' + d.ip + ':' + d.port + ' · حد الرفع ' + d.max_upload_mb + ' م.ب';
  } catch (e) {}
}

async function loadDir(path) {
  const card = document.getElementById('listcard');
  card.innerHTML = '<div class="empty">جارٍ التحميل…</div>';
  try {
    const r = await fetch('/api/ls?path=' + encodeURIComponent(path || ''));
    const d = await r.json();
    if (!d.ok) { card.innerHTML = '<div class="empty">' + esc(d.error || 'خطأ') + '</div>'; return; }

    if (d.kind === 'file') { downloadFile(d.path); loadDir(CURRENT); return; }

    CURRENT = d.path;
    ROOTS = d.roots || ROOTS;
    document.getElementById('crumb').textContent = d.path;

    let html = '';
    if (d.parent) {
      html += '<div class="row" onclick="loadDir(' + JSON.stringify(d.parent).replace(/"/g,'&quot;') + ')">' +
              '<div class="ico">↩️</div><div class="name"><b>رجوع</b><span>مجلد أعلى</span></div></div>';
    }
    if (!d.entries.length) {
      html += '<div class="empty">هذا المجلد فارغ</div>';
    }
    for (const e of d.entries) {
      const p = JSON.stringify(e.path).replace(/"/g, '&quot;');
      if (e.dir) {
        html += '<div class="row" onclick="loadDir(' + p + ')">' +
          '<div class="ico">📁</div><div class="name"><b>' + esc(e.name) + '</b>' +
          '<span dir="ltr" style="unicode-bidi:isolate">' + esc(e.mtime) + '</span></div>' +
          '<div style="color:#4C5F80">›</div></div>';
      } else {
        html += '<div class="row">' +
          '<div class="ico">📄</div>' +
          '<div class="name"><b>' + esc(e.name) + '</b><span>' + esc(e.size) +
          ' · <span dir="ltr" style="unicode-bidi:isolate">' + esc(e.mtime) + '</span></span></div>' +
          '<button class="btn ghost sm" onclick="downloadFile(' + p + ')">⬇️</button>' +
          '<button class="btn danger sm" onclick="delItem(' + p + ', ' + JSON.stringify(e.name).replace(/"/g,'&quot;') + ')">🗑️</button>' +
          '</div>';
      }
    }
    card.innerHTML = html;
    renderRoots();
  } catch (e) {
    card.innerHTML = '<div class="empty">تعذّر الاتصال بالحاسوب</div>';
  }
}

function renderRoots() {
  const box = document.getElementById('roots');
  box.innerHTML = ROOTS.map(r =>
    '<div class="row" onclick="loadDir(' + JSON.stringify(r.path).replace(/"/g,'&quot;') + ')">' +
    '<div class="ico">🗂️</div><div class="name"><b>' + esc(r.name) + '</b>' +
    '<span dir="ltr">' + esc(r.path) + '</span></div></div>'
  ).join('');
}

function pickFiles() { document.getElementById('fileinput').click(); }

async function uploadFiles(files) {
  if (!files || !files.length) return;
  const bar = document.getElementById('progbar');
  const wrap = document.getElementById('prog');
  const status = document.getElementById('upstatus');
  wrap.style.display = '';

  for (let i = 0; i < files.length; i++) {
    const f = files[i];
    status.textContent = 'رفع ' + (i + 1) + ' من ' + files.length + ' — ' + f.name;
    await new Promise((resolve) => {
      const xhr = new XMLHttpRequest();
      xhr.open('PUT', '/api/upload?dir=' + encodeURIComponent(CURRENT) +
                       '&name=' + encodeURIComponent(f.name));
      xhr.upload.onprogress = (ev) => {
        if (ev.lengthComputable) bar.style.width = (ev.loaded / ev.total * 100) + '%';
      };
      xhr.onload = () => {
        try {
          const d = JSON.parse(xhr.responseText);
          if (!d.ok) toast('فشل: ' + (d.error || ''));
        } catch (e) { toast('فشل الرفع'); }
        resolve();
      };
      xhr.onerror = () => { toast('انقطع الاتصال أثناء الرفع'); resolve(); };
      xhr.send(f);
    });
  }
  bar.style.width = '100%';
  status.textContent = 'تم رفع ' + files.length + ' ملف ✅';
  toast('اكتمل الرفع إلى: ' + CURRENT);
  setTimeout(() => { wrap.style.display = 'none'; bar.style.width = '0'; status.textContent = ''; }, 1600);
  loadDir(CURRENT);
}

function downloadFile(path) {
  window.location.href = '/api/download?path=' + encodeURIComponent(path);
}

async function delItem(path, name) {
  if (!confirm('حذف «' + name + '»؟\nلن يُمحى نهائياً — سيُعاد تسميته ويمكن استرجاعه.')) return;
  const r = await fetch('/api/delete', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({path: path})
  });
  const d = await r.json();
  if (d.ok) { toast('تم الحذف (قابل للاسترجاع)'); loadDir(CURRENT); }
  else toast(d.error || 'فشل الحذف');
}

async function newFolder() {
  const name = prompt('اسم المجلد الجديد:');
  if (!name) return;
  const r = await fetch('/api/mkdir', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({dir: CURRENT, name: name})
  });
  const d = await r.json();
  if (d.ok) { toast('أُنشئ المجلد'); loadDir(CURRENT); }
  else toast(d.error || 'فشل الإنشاء');
}

/* ---------------------------- الحافظة ---------------------------- */

async function sendClip() {
  const box = document.getElementById('cliptext');
  const text = box.value.trim();
  if (!text) { toast('اكتب أو الصق نصاً أولاً'); return; }
  const r = await fetch('/api/clip', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({text: text})
  });
  const d = await r.json();
  if (d.ok) { toast('✅ أصبح النص جاهزاً للصق على الحاسوب (Ctrl+V)'); box.value = ''; loadHistory(); }
  else toast(d.error || 'فشل');
}

async function refreshPcClip() {
  try {
    const r = await fetch('/api/clip-capture', {method: 'POST'});
    const d = await r.json();
    const box = document.getElementById('pcclip');
    box.value = d.text || '';
  } catch (e) {}
  loadHistory();
}

function copyPcClip() {
  const box = document.getElementById('pcclip');
  if (!box.value) { toast('الحافظة فارغة'); return; }
  box.removeAttribute('readonly');
  box.select();
  box.setSelectionRange(0, box.value.length);
  let ok = false;
  try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
  box.setAttribute('readonly', 'readonly');
  if (ok) toast('📋 تم النسخ — الصقه في أي تطبيق');
  else toast('اضغط مطوّلاً على النص ثم اختر «نسخ»');
}

async function loadHistory() {
  try {
    const r = await fetch('/api/clip');
    const d = await r.json();
    const box = document.getElementById('pcclip');
    if (document.activeElement !== box) box.value = d.text || '';
    const h = document.getElementById('history');
    if (!d.history || !d.history.length) {
      h.innerHTML = '<div class="empty">لا يوجد سجل بعد</div>';
      return;
    }
    h.innerHTML = d.history.map((item, i) => {
      const txt = esc(item.text.slice(0, 220));
      const src = item.source === 'الهاتف' ? '📱 من الهاتف' : '💻 من الحاسوب';
      return '<div class="hrow" style="margin-bottom:8px">' +
        '<div class="hist" style="margin-top:0">' + txt + '<br><span class="pill">' +
        src + ' · ' + esc(item.at) + '</span></div>' +
        '<button class="btn ghost sm" onclick="reuse(' + i + ')">📌 لصق</button></div>';
    }).join('');
  } catch (e) {}
}

async function reuse(index) {
  const r = await fetch('/api/clip');
  const d = await r.json();
  const item = (d.history || [])[index];
  if (!item) return;
  const r2 = await fetch('/api/clip', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({text: item.text})
  });
  const d2 = await r2.json();
  if (d2.ok) toast('✅ عاد النص إلى حافظة الحاسوب');
  else toast(d2.error || 'فشل');
}

/* ---------------------------- الإقلاع ---------------------------- */

loadInfo();
loadDir('');
loadHistory();
setInterval(() => { if (document.getElementById('pane-clip').style.display !== 'none') refreshPcClip(); }, 3000);
"""


# ==============================================================================
# 7) التشغيل
# ==============================================================================

def _banner() -> None:
    url = f"http://{lan_ip()}:{PORT}/?t={TOKEN}"
    line = "=" * 68
    say()
    say(line)
    say(f"  {APP_NAME} v{APP_VERSION}  —  يعمل الآن")
    say(line)
    say(f"  الرابط على الحاسوب : http://127.0.0.1:{PORT}/?t={TOKEN}")
    say(f"  الرابط من الهاتف  : {url}")
    say()
    say(f"  المجلدات المتاحة  : {len(ROOTS)}")
    for root in ROOTS:
        say(f"      • {root}")
    say()
    say("  للإيقاف: أغلق هذه النافذة أو اضغط Ctrl+C")
    say(line)
    say()


def main() -> None:
    _banner()
    if "--no-browser" not in sys.argv:
        # نفتح الصفحة على الحاسوب بالرمز جاهزاً — لا يكتب المستخدم شيئاً.
        threading.Timer(
            1.5, lambda: webbrowser.open(f"http://127.0.0.1:{PORT}/?t={TOKEN}")
        ).start()

    # تشغيل الخادم يدوياً حتى نُسكِت ضجيج asyncio عند إغلاق المتصفح للتبويب.
    config = uvicorn.Config(app, host="0.0.0.0", port=PORT, log_level="warning", access_log=False)
    server = uvicorn.Server(config)

    async def serve() -> None:
        loop = asyncio.get_running_loop()

        def handler(loop: Any, context: dict[str, Any]) -> None:
            exc = context.get("exception")
            # قطع الاتصال العادي (إغلاق تبويب/تحديث صفحة) ليس خطأ — لا نُخيف المستخدم.
            if isinstance(exc, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)):
                return
            loop.default_exception_handler(context)

        loop.set_exception_handler(handler)
        await server.serve()

    asyncio.run(serve())


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        say("\nتم الإيقاف.")
        sys.exit(0)
