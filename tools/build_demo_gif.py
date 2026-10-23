#!/usr/bin/env python3
"""Build the demo GIF and social preview from captured screenshots.

Screenshots are taken from the real local demo (`claim demo`) at 1440x960.
This script only composes already-rendered pixels; it does not call a model.

    python tools/build_demo_gif.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "assets" / "demo"
GIF_WIDTH = 1080
GIF_IMAGE_HEIGHT = 720
CAPTION_HEIGHT = 100

FRAMES = [
    ("ledger.png", "Status is part of the record",
     "状态是数据的一部分 · 5 current · 3 disputed · 2 superseded"),
    ("conflict.png", "A conflicting write is refused",
     "冲突写入被拒绝，由人显式选择取代或争议"),
    ("brief.png", "A brief that says what it left out",
     "1 KB 预算，省略 6 条并逐条计数"),
    ("search.png", "Status-blind search resurrects a dead decision",
     "关闭状态过滤，过期结论排到第一"),
    ("context.png", "Evidence is retrieved; authority stays in the store",
     "证据必须挂到 claim，再按同一状态策略过滤"),
    ("safety.png", "Backups you can verify; removal you can audit",
     "快照带 manifest 校验，删除留审计与备份"),
    ("evidence.png", "Stale hits: 54.2% → 0%",
     "代价也写在旁边：Recall@5 95.8% → 91.7%"),
    ("chain.png", "History stays; authority moves",
     "取代链保留旧决策，但不再冒充现行"),
]

FONT_CANDIDATES = {
    "regular": ["C:/Windows/Fonts/segoeui.ttf", "/System/Library/Fonts/Helvetica.ttc",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"],
    "semibold": ["C:/Windows/Fonts/seguisb.ttf", "/System/Library/Fonts/Helvetica.ttc",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
    "bold": ["C:/Windows/Fonts/segoeuib.ttf", "/System/Library/Fonts/Helvetica.ttc",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
    "cjk": ["C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msyhbd.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/System/Library/Fonts/PingFang.ttc"],
}


def font(kind, size):
    for candidate in FONT_CANDIDATES[kind]:
        if Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size)
            except OSError:
                continue
    return ImageFont.load_default()


def lettered(draw, xy, text, fill, fnt, spacing=2):
    x, y = xy
    for char in text:
        draw.text((x, y), char, font=fnt, fill=fill)
        x += draw.textlength(char, font=fnt) + spacing


def build_gif():
    frames = []
    for index, (filename, title, subtitle) in enumerate(FRAMES, 1):
        source = DEMO / filename
        if not source.is_file():
            raise SystemExit("missing screenshot: " + str(source))
        image = Image.open(source).convert("RGB")
        image = image.resize((GIF_WIDTH, GIF_IMAGE_HEIGHT), Image.LANCZOS)
        canvas = Image.new("RGB", (GIF_WIDTH, GIF_IMAGE_HEIGHT + CAPTION_HEIGHT), "#0a1220")
        draw = ImageDraw.Draw(canvas)
        draw.rectangle((0, 0, GIF_WIDTH, 3), fill="#63e2a4")
        draw.text((28, 20), f"{index:02d} / {len(FRAMES):02d}", font=font("semibold", 18), fill="#63e2a4")
        draw.text((128, 15), title, font=font("semibold", 28), fill="#eef2ea")
        draw.text((128, 53), subtitle, font=font("cjk", 17), fill="#9aa9bd")
        lettered(draw, (GIF_WIDTH - 196, 24), "CLAIMLEDGER", "#526176", font("semibold", 11), spacing=1.6)
        draw.text((GIF_WIDTH - 196, 44), "decision ledger", font=font("regular", 12), fill="#526176")
        draw.line((0, CAPTION_HEIGHT - 1, GIF_WIDTH, CAPTION_HEIGHT - 1), fill="#1d2c44")
        canvas.paste(image, (0, CAPTION_HEIGHT))
        frames.append(canvas)

    palette = frames[0].convert("P", palette=Image.ADAPTIVE, colors=256)
    converted = [palette]
    for frame in frames[1:]:
        converted.append(frame.quantize(palette=palette, dither=Image.Dither.NONE))

    output = DEMO / "claimledger-demo.gif"
    converted[0].save(
        output, save_all=True, append_images=converted[1:], duration=2800, loop=0,
        optimize=True, disposal=2)
    return output


def build_social_preview():
    width, height = 1200, 630
    canvas = Image.new("RGB", (width, height), "#0a1220")
    draw = ImageDraw.Draw(canvas)
    for y in range(height):
        shade = 8 + int(10 * (1 - y / height))
        draw.line((0, y, width, y), fill=(shade, shade + 6, shade + 16))
    for step in range(12):
        x = 520 + step * 60
        draw.line((x, 0, x, height), fill="#0e1a2c")
    for step in range(9):
        y = step * 70
        draw.line((0, y, width, y), fill="#0e1a2c")

    # Mark: three-line ledger in a rounded square.
    draw.rounded_rectangle((64, 60, 124, 120), radius=16, fill="#0e1626", outline="#2a3b58", width=2)
    draw.line((84, 76, 84, 104), fill="#2a3b58", width=3)
    draw.line((92, 82, 110, 82), fill="#63e2a4", width=6)
    draw.line((92, 94, 110, 94), fill="#7e8ca3", width=6)
    draw.line((91, 104, 111, 92), fill="#eef2f7", width=2)
    lettered(draw, (144, 78), "CLAIMLEDGER", "#eef2ea", font("semibold", 22), spacing=2.4)
    draw.text((144, 108), "the decision ledger for AI agents", font=font("regular", 16), fill="#7e8ca3")

    draw.text((64, 168), "Your agent remembers.", font=font("bold", 52), fill="#eef2ea")
    draw.text((64, 238), "Does it know", font=font("bold", 40), fill="#63e2a4")
    draw.text((64, 286), "what still counts?", font=font("bold", 40), fill="#63e2a4")
    draw.text((64, 350), "Record every decision once. Keep its status and source.", font=font("regular", 20), fill="#9aa9bd")
    draw.text((64, 382), "Supersede the old one. Never serve it as current.", font=font("regular", 20), fill="#9aa9bd")

    chips = [("CURRENT", "5", "#63e2a4"), ("DISPUTED", "3", "#e8c268"), ("SUPERSEDED", "2", "#8797ac")]
    x = 64
    for label, count, color in chips:
        w = 156 if label != "SUPERSEDED" else 190
        draw.rounded_rectangle((x, 430, x + w, 478), radius=10, fill="#111d31", outline="#24344e", width=1)
        draw.ellipse((x + 14, 448, x + 22, 456), fill=color)
        draw.text((x + 32, 440), count, font=font("semibold", 22), fill="#eef2ea")
        draw.text((x + 32, 462), label, font=font("semibold", 9), fill="#7e8ca3")
        x += w + 12

    draw.text((64, 556), "LOCAL-FIRST  ·  ZERO DEPENDENCIES  ·  ZERO MODEL CALLS  ·  MIT",
              font=font("semibold", 12), fill="#526176")

    shot = Image.open(DEMO / "ledger.png").convert("RGB")
    target_w, target_h = 500, 333
    shot = shot.resize((target_w, target_h), Image.LANCZOS)
    ox, oy = 650, 150
    mask = Image.new("L", (target_w, target_h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, target_w - 1, target_h - 1), radius=14, fill=255)
    canvas.paste(shot, (ox, oy), mask)
    draw.rounded_rectangle((ox, oy, ox + target_w, oy + target_h), radius=14, outline="#2a3b58", width=2)

    output = DEMO / "social-preview.png"
    canvas.save(output, optimize=True)
    return output


def main():
    gif = build_gif()
    social = build_social_preview()
    print("wrote", gif.relative_to(ROOT), f"{gif.stat().st_size / 1024 / 1024:.2f} MB")
    print("wrote", social.relative_to(ROOT), f"{social.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
