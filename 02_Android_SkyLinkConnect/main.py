# -*- coding: utf-8 -*-
"""
================================================================================
 SkyLink Connect  —  v1.0.0
--------------------------------------------------------------------------------
 تطبيق الهاتف المساعد لمنظومة SkyLink Ecosystem.

 الوظيفة:
   * يعرض عنوان IP المحلي للهاتف بخط ضخم جداً (يسهل قراءته من بعيد).
   * زر واحد يفتح «خيارات المطوّر» مباشرةً عبر Intent رسمي من أندرويد (pyjnius).
   * زر ثانٍ يفتح إعدادات Wi-Fi، وثالث ينسخ العنوان للحافظة.

 التوافق:
   * أندرويد 5.0 (API 21) فما فوق.
   * خفيف: بلا صور، بلا رسوم متحركة ثقيلة، تحديث العنوان كل 5 ثوانٍ فقط.
   * دعم العربية: تشكيل الحروف (arabic_reshaper + python-bidi) + خط النظام
     Noto Naskh Arabic. وإن غابت المكتبات يبقى التطبيق يعمل باللاتينية.

 البناء:
   أنظر ملف buildozer.spec وملف README_BUILD_ANDROID.md
================================================================================
"""

from __future__ import annotations

import os
import socket

from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.metrics import dp
from kivy.utils import platform
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDFlatButton, MDRaisedButton
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDLabel
from kivymd.uix.screen import MDScreen
from kivymd.uix.scrollview import MDScrollView
from kivymd.uix.toolbar import MDTopAppBar


# ==============================================================================
# 1) دعم العربية في Kivy (Kivy لا يشكّل الحروف ولا يرتّبها من اليمين تلقائياً)
# ==============================================================================

def _build_shaper():
    """يُعيد دالة تشكيل عربية إن توفرت المكتبات، وإلا يُعيد الهوية (نص كما هو)."""
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display

        def shape(text: str) -> str:
            try:
                return get_display(arabic_reshaper.reshape(text))
            except Exception:
                return text

        return shape
    except Exception:  # المكتبات غير مثبّتة (بيئة تطوير مثلاً)
        def passthrough(text: str) -> str:
            return text

        return passthrough


ar = _build_shaper()


def _find_arabic_font() -> str | None:
    """
    يبحث عن خط عربي داخل نظام أندرويد. Kivy يحتاج الخط صراحةً لعرض العربية.
    يُعيد None إن لم يوجد ⇒ يبقى الخط الافتراضي (Roboto) والنصوص اللاتينية سليمة.
    """
    candidates = [
        "/system/fonts/NotoNaskhArabic-Regular.ttf",
        "/system/fonts/NotoNaskhArabicUI-Regular.ttf",
        "/system/fonts/NotoSansArabic-Regular.ttf",
        "/system/fonts/DroidNaskh-Regular.ttf",
        "/system/fonts/DroidSansArabic.ttf",
    ]
    # خط مرفق بالمشروع (إن وُضع في مجلد fonts/) له الأولوية
    local = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
    if os.path.isdir(local):
        for name in sorted(os.listdir(local)):
            if name.lower().endswith((".ttf", ".otf")):
                candidates.insert(0, os.path.join(local, name))

    for path in candidates:
        try:
            if os.path.isfile(path):
                return path
        except OSError:
            continue
    return None


ARABIC_FONT = _find_arabic_font()

#: لون الواجهة الأساسي (نفس هوية تطبيق الحاسوب).
ACCENT_HEX = (0.13, 0.83, 0.93, 1)      # #22D3EE
OK_HEX = (0.13, 0.77, 0.37, 1)          # #22C55E
WARN_HEX = (0.96, 0.62, 0.04, 1)        # #F59E0B
MUTED_HEX = (0.56, 0.63, 0.76, 1)       # #8DA1C1


# ==============================================================================
# 2) أدوات أندرويد الأصلية (pyjnius)
# ==============================================================================

def _jnius():
    """استيراد pyjnius عند الحاجة فقط، وبأمان على الحاسوب."""
    if platform != "android":
        return None
    try:
        from jnius import autoclass
        return autoclass
    except Exception:
        return None


def get_local_ip() -> tuple[str | None, str]:
    """
    يُعيد (العنوان، مصدره). يحاول أولاً WifiManager (أدق على أندرويد)،
    ثم يعود لمقبس UDP (لا يرسل أي بيانات فعلياً).
    """
    autoclass = _jnius()
    if autoclass is not None:
        try:
            Context = autoclass("android.content.Context")
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            activity = PythonActivity.mActivity
            wifi = activity.getSystemService(Context.WIFI_SERVICE)
            info = wifi.getConnectionInfo()
            ip_int = int(info.getIpAddress() or 0)
            if ip_int != 0:
                # getIpAddress يعيد العدد بترتيب بايتات صغيري (little-endian)
                host = "%d.%d.%d.%d" % (
                    ip_int & 0xFF,
                    (ip_int >> 8) & 0xFF,
                    (ip_int >> 16) & 0xFF,
                    (ip_int >> 24) & 0xFF,
                )
                return host, "wifi"
        except Exception:
            pass

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # لا تُرسل أي حزمة: فقط لاختيار واجهة الشبكة النشطة.
            sock.connect(("8.8.8.8", 53))
            host = sock.getsockname()[0]
        finally:
            sock.close()
        if host and not host.startswith("127."):
            return host, "socket"
    except Exception:
        pass
    return None, "none"


def open_android_settings(action_name: str = "ACTION_APPLICATION_DEVELOPMENT_SETTINGS") -> bool:
    """
    يفتح صفحة إعدادات أندرويد عبر Intent رسمي.
    يجرّب الإجراء المطلوب، وإن لم يوجد يتراجع إلى إعدادات التطبيق نفسه.
    يُعيد True عند النجاح.
    """
    autoclass = _jnius()
    if autoclass is None:
        return False

    try:
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        Intent = autoclass("android.content.Intent")
        Settings = autoclass("android.provider.Settings")
        activity = PythonActivity.mActivity

        # المحاولة 1: الإجراء المطلوب
        try:
            action = getattr(Settings, action_name)
            intent = Intent(action)
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            activity.startActivity(intent)
            return True
        except Exception:
            pass

        # المحاولة 2: إعدادات النظام العامة
        try:
            intent = Intent(Settings.ACTION_SETTINGS)
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            activity.startActivity(intent)
            return True
        except Exception:
            pass

        # المحاولة 3: صفحة تفاصيل هذا التطبيق (متاحة دائماً)
        try:
            Uri = autoclass("android.net.Uri")
            intent = Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS)
            intent.setData(Uri.parse("package:" + activity.getPackageName()))
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            activity.startActivity(intent)
            return True
        except Exception:
            return False
    except Exception:
        return False


# ==============================================================================
# 3) عناصر واجهة صغيرة قابلة لإعادة الاستخدام
# ==============================================================================

class AutoLabel(MDLabel):
    """
    MDLabel يتكيّف تلقائياً:
      * يلفّ النص حسب عرضه (text_size).
      * يضبط ارتفاعه حسب النص الفعلي ⇒ لا فراغات ولا تراكب.
    """

    def __init__(self, **kwargs):
        kwargs.setdefault("halign", "center")
        kwargs.setdefault("size_hint_y", None)
        if ARABIC_FONT and not kwargs.get("font_name"):
            kwargs["font_name"] = ARABIC_FONT
        super().__init__(**kwargs)
        self.bind(width=self._sync_text_size)
        self.bind(texture_size=self._sync_height)

    def _sync_text_size(self, *_):
        self.text_size = (max(self.width - dp(6), dp(40)), None)

    def _sync_height(self, *_):
        self.height = self.texture_size[1] + dp(6)


def hint(text: str, size: str = "13sp", color=MUTED_HEX) -> AutoLabel:
    """سطر شرح صغير."""
    return AutoLabel(text=ar(text), font_style="Caption", theme_text_color="Custom",
                     text_color=color, font_size=size)


# ==============================================================================
# 4) التطبيق
# ==============================================================================

class SkyLinkConnect(MDApp):
    title = "SkyLink Connect"
    ip_text = "—"

    # ------------------------------------------------------------------ البناء
    def build(self):
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "Cyan"
        self.theme_cls.accent_palette = "Indigo"
        self.theme_cls.material_style = "M3"

        screen = MDScreen()

        root = MDBoxLayout(orientation="vertical")

        # ------------------------------------------------------ الشريط العلوي
        root.add_widget(
            MDTopAppBar(
                title="SkyLink Connect",
                elevation=2,
                left_action_items=[["cellphone-link", lambda *_: None]],
            )
        )

        # ------------------------------------------------------ المحتوى القابل للتمرير
        scroll = MDScrollView()
        content = MDBoxLayout(
            orientation="vertical",
            padding=(dp(16), dp(16), dp(16), dp(16)),
            spacing=dp(14),
            size_hint_y=None,
        )
        content.bind(minimum_height=content.setter("height"))

        # ------------------------------ البطاقة الرئيسية: العنوان الكبير
        main_card = MDCard(
            orientation="vertical",
            padding=(dp(18), dp(20), dp(18), dp(20)),
            spacing=dp(6),
            radius=[dp(18)],
            elevation=3,
            size_hint_y=None,
        )
        main_card.bind(minimum_height=main_card.setter("height"))

        main_card.add_widget(
            AutoLabel(text="SkyLink Connect", font_style="H5", bold=True,
                      theme_text_color="Custom", text_color=ACCENT_HEX,
                      font_size="24sp")
        )
        main_card.add_widget(
            hint("عنوان هاتفك على الشبكة  ·  Your phone IP", size="12sp")
        )

        self.ip_label = AutoLabel(
            text="…", font_style="H2", bold=True,
            theme_text_color="Custom", text_color=OK_HEX, font_size="46sp",
        )
        main_card.add_widget(self.ip_label)

        self.state_label = hint("جارٍ قراءة الشبكة…", size="12sp")
        main_card.add_widget(self.state_label)

        # زر النسخ
        copy_row = MDBoxLayout(orientation="horizontal", size_hint_y=None,
                               height=dp(40), spacing=dp(8))
        copy_row.add_widget(MDFlatButton(
            text=ar("نسخ العنوان"), theme_text_color="Custom", text_color=ACCENT_HEX,
            on_release=self.copy_ip,
        ))
        copy_row.add_widget(MDFlatButton(
            text=ar("تحديث"), theme_text_color="Custom", text_color=MUTED_HEX,
            on_release=lambda *_: self.refresh_ip(),
        ))
        main_card.add_widget(copy_row)
        content.add_widget(main_card)

        # ------------------------------ زر الإعدادات الكبير
        self.dev_button = MDRaisedButton(
            text=ar("⚙️ تفعيل خيارات المطوّر والاتصال اللاسلكي"),
            font_name=ARABIC_FONT if ARABIC_FONT else None,
            font_size="15sp",
            size_hint=(1, None),
            height=dp(58),
            md_bg_color=ACCENT_HEX,
            text_color=(0.02, 0.07, 0.10, 1),
            elevation=4,
            on_release=self.open_developer_options,
        )
        content.add_widget(self.dev_button)

        # ------------------------------ أزرار ثانوية
        secondary = MDBoxLayout(orientation="horizontal", size_hint_y=None,
                                height=dp(46), spacing=dp(8))
        secondary.add_widget(MDFlatButton(
            text=ar("🌐 إعدادات Wi-Fi"),
            theme_text_color="Custom", text_color=MUTED_HEX,
            on_release=lambda *_: self._open("ACTION_WIFI_SETTINGS"),
        ))
        secondary.add_widget(MDFlatButton(
            text=ar("📱 إعدادات النظام"),
            theme_text_color="Custom", text_color=MUTED_HEX,
            on_release=lambda *_: self._open("ACTION_SETTINGS"),
        ))
        content.add_widget(secondary)

        # ------------------------------ بطاقة الشرح
        steps_card = MDCard(
            orientation="vertical",
            padding=(dp(18), dp(16), dp(18), dp(16)),
            spacing=dp(8),
            radius=[dp(16)],
            elevation=1,
            size_hint_y=None,
        )
        steps_card.bind(minimum_height=steps_card.setter("height"))

        steps_card.add_widget(AutoLabel(
            text=ar("خطوات التشغيل"),
            bold=True, font_size="15sp", theme_text_color="Custom",
            text_color=ACCENT_HEX,
        ))

        steps = [
            "١ · اضغط الزر الكبير وافتح «خيارات المطوّر».",
            "٢ · فعّل «تصحيح أخطاء USB» (Debugging).",
            "٣ · للأجهزة الحديثة: فعّل «التصحيح اللاسلكي» واكتب رقم المنفذ مع عنوان IP.",
            "٤ · على الحاسوب: افتح SkyLink Desktop، اختر Wi-Fi، واكتب هذا العنوان.",
            "٥ · اضغط «بث ومشاركة الشاشة الآن» وستظهر شاشة الهاتف على الحاسوب.",
        ]
        for line in steps:
            steps_card.add_widget(hint(line, size="12sp", color=(0.85, 0.89, 0.96, 1)))

        steps_card.add_widget(hint(
            "المنفذ الافتراضي لـ ADB هو 5555 — بعض الأجهزة الحديثة تستخدم منفذاً عشوائياً.",
            size="11sp",
        ))
        content.add_widget(steps_card)

        scroll.add_widget(content)
        root.add_widget(scroll)
        screen.add_widget(root)

        # ------------------------------------------------------ أول قراءة + تحديث دوري
        Clock.schedule_once(lambda *_: self.refresh_ip(), 0.6)
        self._tick = Clock.schedule_interval(lambda *_: self.refresh_ip(), 5.0)
        return screen

    # ------------------------------------------------------------------ الوظائف
    def refresh_ip(self) -> None:
        """يقرأ العنوان الحالي ويحدّث الواجهة (بلا أي طلب شبكي)."""
        host, source = get_local_ip()
        if host:
            self.ip_text = host
            self.ip_label.text = host
            self.ip_label.text_color = OK_HEX
            if source == "wifi":
                self.state_label.text = ar("متصل بشبكة Wi-Fi — العنوان جاهز للاستخدام")
                self.state_label.text_color = (0.13, 0.77, 0.37, 1)
            else:
                self.state_label.text = ar("العنوان مقروء — تأكد أن الهاتف على نفس شبكة الحاسوب")
                self.state_label.text_color = WARN_HEX
        else:
            self.ip_text = "—"
            self.ip_label.text = "—"
            self.ip_label.text_color = WARN_HEX
            self.state_label.text = ar("لا يوجد اتصال شبكة — فعّل Wi-Fi ثم اضغط تحديث")
            self.state_label.text_color = WARN_HEX

    def copy_ip(self, *_args) -> None:
        try:
            Clipboard.copy(self.ip_text)
            self.state_label.text = ar("تم نسخ العنوان إلى الحافظة ✔")
            self.state_label.text_color = OK_HEX
        except Exception:
            self.state_label.text = ar("تعذّر النسخ على هذا الجهاز")

    def open_developer_options(self, *_args) -> None:
        ok = open_android_settings("ACTION_APPLICATION_DEVELOPMENT_SETTINGS")
        if ok:
            self.state_label.text = ar("فُتحت خيارات المطوّر — فعّل «تصحيح أخطاء USB»")
            self.state_label.text_color = ACCENT_HEX
        else:
            self.state_label.text = ar(
                "لا يمكن فتح الإعدادات تلقائياً — افتحها يدوياً: الإعدادات ← حول الهاتف"
            )
            self.state_label.text_color = WARN_HEX

    def _open(self, action_name: str) -> None:
        open_android_settings(action_name)

    def on_pause(self):
        # نوقف المؤقّت أثناء خروج التطبيق للخلفية لتوفير البطارية.
        try:
            self._tick.cancel()
        except Exception:
            pass
        return True

    def on_resume(self):
        self.refresh_ip()
        try:
            self._tick = Clock.schedule_interval(lambda *_: self.refresh_ip(), 5.0)
        except Exception:
            pass


if __name__ == "__main__":
    SkyLinkConnect().run()
