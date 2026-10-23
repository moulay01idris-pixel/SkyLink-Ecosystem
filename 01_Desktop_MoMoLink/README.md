# MoMoLink Desktop Pro — تطبيق الحاسوب

تطبيق واحد لبث شاشة هاتف أندرويد والتحكم بها، بكابل USB أو عبر Wi-Fi.

## التشغيل

```
انقر مرتين على run_desktop.bat
```

أو يدوياً:

```bat
py -m pip install -r requirements.txt
py momolink_desktop.py
```

## البناء إلى ملف EXE واحد

```
انقر مرتين على build_exe.bat
```

الناتج: `dist\MoMoLinkDesktopPro.exe`

## محتويات المجلد

| العنصر | الوظيفة |
|---|---|
| `momolink_desktop.py` | الكود الكامل (واجهة + منطق الاتصال) |
| `scrcpy/` | scrcpy 5.0.1 + adb مدمجة — لا حاجة لتثبيت |
| `assets/icon.ico` | أيقونة التطبيق (مولَّدة بـ`make_icon.py`) |
| `run_desktop.bat` | تشغيل بنقرة مزدوجة |
| `build_exe.bat` | تحويل إلى EXE بنقرة مزدوجة |
| `requirements.txt` | مكتبة الواجهة `flet==1.0.5` |

## أين تُحفظ الإعدادات؟

`%APPDATA%\MoMoLink\config.json` — آخر طريقة اتصال، آخر IP، وجودة البث.
لا تُحفظ أي بيانات شخصية، ولا كلمات مرور.

## ملاحظات

- على **macOS**: التطبيق يبحث عن `scrcpy` في `PATH` (ثبّتها بـ`brew install scrcpy`).
- إن نقلت `MoMoLinkDesktopPro.exe` إلى حاسوب آخر: يكفي الملف وحده (scrcpy مدمجة داخله).
