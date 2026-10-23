# MoMoLink Connect — تطبيق الهاتف

تطبيق أندرويد خفيف يعرض عنوان IP المحلي للهاتف بخط كبير جداً، ويفتح «خيارات المطوّر» مباشرةً.

---

## المحتويات

| الملف | الوظيفة |
|---|---|
| `main.py` | كود التطبيق الكامل (KivyMD + pyjnius) |
| `buildozer.spec` | إعدادات البناء: الصلاحيات، minapi، المعماريات |
| `requirements.txt` | مكتبات المعاينة على الحاسوب (Buildozer لا يستعملها) |

---

## البناء عبر GitHub (لا يحتاج أدوات على ويندوز)

1. ارفع المشروع إلى GitHub
2. Actions ← **Build MoMoLink** ← **Run workflow**
3. انتظر انتهاء المهمة `Android APK (Buildozer)`
4. حمّل `MoMoLinkConnect-APK` من Artifacts

الملف الناتج: `bin/momolinkconnect-1.0.0-arm64-v8a_armeabi-v7a-debug.apk`

---

## البناء محلياً (اختياري — لينكس أو WSL فقط)

```bash
sudo apt-get install -y git zip unzip openjdk-17-jdk autoconf libtool pkg-config \
    zlib1g-dev libncurses-dev libncursesw5-dev cmake libffi-dev libssl-dev
python -m pip install "cython==0.29.36" buildozer
cd 02_Android_MoMoLinkConnect
buildozer -v android debug
```

الناتج في مجلد `bin/`.

### نسخة موقّعة للنشر على Google Play (release)

```bash
keytool -genkey -v -keystore momolink.keystore -alias momolink -keyalg RSA -keysize 2048 -validity 10000
buildozer -v android release
apksigner sign --ks momolink.keystore --out momolinkconnect-release.apk bin/momolinkconnect-1.0.0-*-release-unsigned.apk
```

ثم ارفع مفتاح `momolink.keystore` كـ Secret في GitHub باسم `ANDROID_KEYSTORE_BASE64`
إن أردت بناء release تلقائياً (غير مضاف حالياً في `build.yml` عن قصد — أضفه عند الحاجة).

---

## الصلاحيات

| الصلاحية | لماذا |
|---|---|
| `INTERNET` | للتحقق من الشبكة وللاتصال لاحقاً بـ ADB |
| `ACCESS_WIFI_STATE` | قراءة عنوان IP من `WifiManager` |
| `ACCESS_NETWORK_STATE` | معرفة نوع الشبكة (Wi-Fi / بيانات) |

كلها **صلاحيات عادية** تُمنح عند التثبيت، ولا تُطلب نافذة موافقة إضافية.

---

## كيف يفتح زر «خيارات المطوّر» الصفحة الرسمية؟

```python
Intent = autoclass("android.content.Intent")
Settings = autoclass("android.provider.Settings")
intent = Intent(Settings.ACTION_APPLICATION_DEVELOPMENT_SETTINGS)
intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
activity.startActivity(intent)
```

وإن لم تكن الصفحة متاحة (خيارات المطوّر غير مفعّلة)، يتراجع تلقائياً إلى
`ACTION_SETTINGS` ثم إلى صفحة تفاصيل التطبيق — فلا يحدث انهيار أبداً.

---

## العربية داخل Kivy

Kivy **لا** يشكّل الحروف العربية تلقائياً، لذلك التطبيق:

1. يشكّل النص عبر `arabic_reshaper` + `python-bidi`
2. يستعمل خط نظام أندرويد: `NotoNaskhArabic-Regular.ttf` (أو DroidNaskh كبديل)
3. إن غابت المكتبات: يعمل التطبيق بلا انهيار (نصوص لاتينية + أرقام سليمة)

يمكنك وضع خط عربي خاص بك في مجلد `fonts/` داخل هذا المجلد — سيُستعمل تلقائياً وله الأولوية.

---

## ما لم يُختبر

- لم يُبنَ APK فعلياً بعد (يحتاج GitHub Actions أو لينكس).
- لم يُجرَّب على هاتف حقيقي — التحقق الحالي: `py_compile` + مراجعة منطق pyjnius.
- قراءة IP على أندرويد 13+ قد تعطي تحذير إهمال (`getConnectionInfo` deprecated) لكنها تعمل.
