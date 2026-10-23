[app]

# ------------------------------------------------------------------------------
# هوية التطبيق
# ------------------------------------------------------------------------------
title = MoMoLink Connect
package.name = momolinkconnect
package.domain = dz.momolink

# ------------------------------------------------------------------------------
# الملفات المصدرية
# ------------------------------------------------------------------------------
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,ttf,otf,json,txt
source.include_patterns = assets/*,fonts/*
source.exclude_exts = spec,md,zip,apk
source.exclude_dirs = bin,.buildozer,__pycache__,.github

# ------------------------------------------------------------------------------
# الإصدار والمتطلبات
# ------------------------------------------------------------------------------
version = 1.0.0
# ملاحظة مهمة: kivy==2.3.0 مع kivymd==1.2.0 هما التوافق المستقر لبناء أندرويد 5+.
requirements = python3,kivy==2.3.0,kivymd==1.2.0,pyjnius,arabic-reshaper,python-bidi

# ------------------------------------------------------------------------------
# تثبيت python-for-android على إصدار مستقر يستعمل Python 3.11.5.
# السبب (مُثبَت من سجل الفشل الحقيقي، تشغيل #3):
#   الفرع الدوّار master صار يبني بـPython 3.13/3.14، وkivy 2.3.0 يُترجم بـCython 3.0.12
#   الذي لا يعرف توقيع _PyLong_AsByteArray الجديد ⇒ فشل ترجمة kivy/graphics/tesselator.c:
#   error: too few arguments to function '_PyLong_AsByteArray'
#   وسم v2024.01.21 يستعمل Python 3.11.5 (متوافق مع kivy 2.3.0).
# ------------------------------------------------------------------------------
p4a.branch = v2024.01.21

# ------------------------------------------------------------------------------
# الشاشة
# ------------------------------------------------------------------------------
orientation = portrait
fullscreen = 0

# ------------------------------------------------------------------------------
# صلاحيات أندرويد (كلها مطلوبة لعرض IP والاتصال بـ ADB)
# ------------------------------------------------------------------------------
android.permissions = INTERNET,ACCESS_WIFI_STATE,ACCESS_NETWORK_STATE

# ------------------------------------------------------------------------------
# إعدادات أندرويد
# ------------------------------------------------------------------------------
# minapi = 21 يعني التوافق مع أندرويد 5.0 فما فوق (المطلوب في المواصفات).
android.api = 34
android.minapi = 21
android.ndk_api = 21
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True
android.allow_backup = True
android.private_storage = True
android.release_artifact = apk
android.debug_artifact = apk

# أيقونة التطبيق وشاشة البداية (اختيارية — ضع الملفات في مجلد assets إن أردت)
# icon.filename = %(source.dir)s/assets/icon.png
# presplash.filename = %(source.dir)s/assets/splash.png

# لا نحتاج خدمات خلفية ولا إشعارات
services =

# منع تعطيل التطبيق تلقائياً من طرف النظام
android.wakelock = False
android.presplash_color = #0B1220

# ------------------------------------------------------------------------------
# بناء
# ------------------------------------------------------------------------------
[buildozer]
log_level = 2
warn_on_root = 1
