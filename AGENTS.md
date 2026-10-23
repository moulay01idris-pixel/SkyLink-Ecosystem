# MoMoLink Ecosystem — قواعد دائمة لهذا المشروع

> يُقرأ تلقائياً في كل جلسة داخل هذا المجلد. اللغة: العربية، والردود مختصرة.
> المستخدم: كريم — مهندس مدني غير مبرمج: نفّذ أنت كل شيء، وسلّم ملفات كاملة جاهزة.

## 1) قراءة سجلات GitHub Actions — إلزامية بعد كل Push

**الأداة:** `~/.config/opencode/skills/gh-logs/gh_logs.py` (مهارة `gh-logs` + أمر `/ghlogs`).

```powershell
$py = "C:\Users\idris\AppData\Local\Programs\Thonny\python.exe"
$s  = "C:\Users\idris\.config\opencode\skills\gh-logs\gh_logs.py"
& $py $s whoami                                              # التوكن صالح؟
& $py $s runs --repo moulay01idris-pixel/SkyLink-Ecosystem   # آخر التشغيلات
& $py $s log  --repo moulay01idris-pixel/SkyLink-Ecosystem --job Android --lines 40
```

- **القاعدة:** بعد أي Push لا تقل «نجح» أو «فشل» بالتخمين — **اقرأ السجل** وأعطِ السبب بنصّه.
- التوكن يُقرأ من **مدير بيانات الاعتماد في ويندوز** (توكن GitHub Desktop لحساب
  `moulay01idris-pixel`) — **لا يُطبع ولا يُنسخ ولا يُحفظ في المستودع**.
- الدفع (Push) لا يعمل من سطر الأوامر (بيانات اعتماد قديمة بلا صلاحية) ⇒ **كريم يدفع من GitHub Desktop**،
  ثم أقرأ أنا السجل وأبلّغه بالنتيجة.
- إن فشل التوكن: اطلب منه تسجيل الخروج/الدخول في GitHub Desktop (يُجدّد التوكن) — لا تطلب كلمة مروره أبداً.

## 2) حقائق تقنية مُثبتة (لا تُخمّنها مرة أخرى)

| الموضوع | الحقيقة |
|---|---|
| الكتابة العربية من لوحة مفاتيح الحاسوب | **مستحيلة** عبر scrcpy: يُرسل أزراراً فيزيائية والهاتف يترجمها لاتينياً. الحل: الحافظة + `Ctrl+V` (منفَّذ: مربع «إرسال نص عربي»). |
| لوحة AZERTY الفرنسية | تكتب `a` فيظهر `q` — الحل: `--keyboard=uhid` + ضبط تخطيط «لوحة المفاتيح الفيزيائية» في الهاتف. |
| لقطة الشاشة | `adb exec-out screencap -p` (بايتات خام — لا تمرّ عبر PowerShell). |
| تسجيل الفيديو | `scrcpy --record=...` — يُقرأ عند الإطلاق فقط، فالتسجيل يعيد تشغيل البث. |
| الشاشات المحمية (FLAG_SECURE) | تظهر سوداء — منع من أندرويد نفسه، ولا يوجد تحايل مشروع. |
| بناء APK | p4a `v2024.01.21` (بايثون 3.11.5) + kivy 2.3.0 + Cython 3.0.12. فرع master يبني بـ3.13/3.14 فيفشل `tesselator.c`. |
| كاش البناء | لا تُخزّن `02_Android_MoMoLinkConnect/.buildozer` — حالة ناقصة منه أفشلت بناءً كاملاً. |
| فليت | `flet==1.0.5` — واجهة عربية `page.rtl = True`. |
| بايثون | ليس في PATH: `C:\Users\idris\AppData\Local\Programs\Thonny\python.exe` |
| git | `C:\Users\idris\AppData\Local\GitHubDesktop\app-3.6.7\resources\app\git\cmd\git.exe` |

## 3) قواعد تسليم

- ملفات كاملة فقط، وتشغيل `py_compile` + `_test_core.py` قبل أي تسليم.
- لا تسلّم شيئاً لم يُختبر: قل «لم يُختبر» صراحةً.
- بعد كل تغيير في `momolink_desktop.py`: أعد بناء `dist\MoMoLinkDesktopPro.exe` عبر `build_exe.bat`.
- لا تضع أي مفتاح أو توكن داخل المستودع (المستودع عام).
