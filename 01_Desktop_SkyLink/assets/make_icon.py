# -*- coding: utf-8 -*-
"""
مولّد أيقونة التطبيق (يُشغَّل مرة واحدة فقط — ليس مطلوباً لتشغيل التطبيق).

يُنشئ assets/icon.ico بأحجام متعددة بنفس هوية الواجهة:
خلفية متدرّجة (سماوي ← بنفسجي) + مثلث تشغيل أبيض في الوسط.

التشغيل:
    python assets/make_icon.py
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:  # pragma: no cover
    raise SystemExit("هذه الأداة تحتاج Pillow:  python -m pip install pillow")

ACCENT = (34, 211, 238)     # #22D3EE
INDIGO = (99, 102, 241)     # #6366F1
SIZE = 512                  # نعمل بحجم كبير ثم نُصغّر بجودة عالية


def build_icon() -> Image.Image:
    """يرسم الأيقونة بدقة عالية ثم يُصغّرها لإعطاء حواف ناعمة (Anti-aliasing)."""
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))

    # ---------------------------------------------------- خلفية متدرّجة
    gradient = Image.new("RGBA", (SIZE, SIZE))
    pix = gradient.load()
    for y in range(SIZE):
        for x in range(SIZE):
            t = (x + y) / (2.0 * (SIZE - 1))
            r = int(ACCENT[0] + (INDIGO[0] - ACCENT[0]) * t)
            g = int(ACCENT[1] + (INDIGO[1] - ACCENT[1]) * t)
            b = int(ACCENT[2] + (INDIGO[2] - ACCENT[2]) * t)
            pix[x, y] = (r, g, b, 255)

    # ---------------------------------------------------- قناع الزوايا الدائرية
    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, SIZE - 1, SIZE - 1], radius=int(SIZE * 0.22), fill=255
    )
    img.paste(gradient, (0, 0), mask)

    # ---------------------------------------------------- مثلث التشغيل
    draw = ImageDraw.Draw(img)
    cx, cy = SIZE * 0.53, SIZE * 0.5
    half = SIZE * 0.21
    draw.polygon(
        [
            (cx - half * 0.78, cy - half),
            (cx - half * 0.78, cy + half),
            (cx + half * 1.05, cy),
        ],
        fill=(255, 255, 255, 255),
    )

    # ---------------------------------------------------- حلقة رقيقة حول المثلث
    draw.ellipse(
        [SIZE * 0.16, SIZE * 0.16, SIZE * 0.84, SIZE * 0.84],
        outline=(255, 255, 255, 70),
        width=max(2, int(SIZE * 0.012)),
    )
    return img


def main() -> None:
    here = Path(__file__).resolve().parent
    out = here / "icon.ico"
    icon = build_icon()
    icon.save(
        out,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    # نسخة PNG للاستخدام في الواجهات/التوثيق
    icon.resize((256, 256), Image.LANCZOS).save(here / "icon.png", format="PNG")
    print(f"ICON_OK {out} ({os.path.getsize(out)} bytes)")


if __name__ == "__main__":
    main()
