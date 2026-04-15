from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from config import ASSETS_DIR, OUTPUT_DIR, get_config


BRANDING_DIR = OUTPUT_DIR / "branding"
BRANDING_DIR.mkdir(parents=True, exist_ok=True)


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    config = get_config()
    font_path = config.font_file
    if font_path.exists():
        return ImageFont.truetype(str(font_path), size=size)
    return ImageFont.load_default()


def fit_contain(image: Image.Image, width: int, height: int) -> Image.Image:
    image = image.copy()
    image.thumbnail((width, height))
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    x = (width - image.width) // 2
    y = (height - image.height) // 2
    canvas.alpha_composite(image, dest=(x, y))
    return canvas


def add_center_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    center_x: int,
    y: int,
    font: ImageFont.ImageFont,
    fill: str,
    stroke_fill: str,
    stroke_width: int = 0,
) -> None:
    bbox = draw.multiline_textbbox((0, 0), text, font=font, spacing=8, align="center", stroke_width=stroke_width)
    width = bbox[2] - bbox[0]
    draw.multiline_text(
        (center_x - (width / 2), y),
        text,
        font=font,
        fill=fill,
        spacing=8,
        align="center",
        stroke_fill=stroke_fill,
        stroke_width=stroke_width,
    )


def build_banner() -> Path:
    banner = Image.new("RGBA", (2560, 1440), "#071a35")
    draw = ImageDraw.Draw(banner, "RGBA")

    draw.rectangle((0, 0, 2560, 1440), fill=(7, 26, 53, 255))
    draw.ellipse((-220, 140, 520, 880), fill=(196, 30, 58, 225))
    draw.ellipse((1920, -80, 2740, 740), fill=(42, 87, 175, 230))
    draw.rounded_rectangle((170, 160, 2390, 1280), radius=72, fill=(12, 30, 58, 210))

    safe = (640, 360, 1920, 1080)
    draw.rounded_rectangle(safe, radius=48, outline=(255, 255, 255, 55), width=4)

    map_path = ASSETS_DIR / "content images" / "nepal_map.png"
    if map_path.exists():
        nepal_map = Image.open(map_path).convert("RGBA")
        nepal_map = fit_contain(nepal_map, 760, 420)
        shadow = Image.new("RGBA", nepal_map.size, (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow, "RGBA")
        shadow_draw.rounded_rectangle((12, 12, nepal_map.width - 12, nepal_map.height - 12), radius=36, fill=(0, 0, 0, 90))
        shadow = shadow.filter(ImageFilter.GaussianBlur(12))
        banner.alpha_composite(shadow, dest=(1540, 470))
        banner.alpha_composite(nepal_map, dest=(1500, 430))

    title_font = load_font(114)
    subtitle_font = load_font(54)
    tag_font = load_font(38)

    add_center_text(
        draw,
        "360 Nepal Explained",
        center_x=1090,
        y=430,
        font=title_font,
        fill="#f8fafc",
        stroke_fill="#020617",
        stroke_width=2,
    )
    add_center_text(
        draw,
        "History • Mystery • Development • News",
        center_x=1030,
        y=610,
        font=subtitle_font,
        fill="#fde68a",
        stroke_fill="#111827",
        stroke_width=1,
    )
    add_center_text(
        draw,
        "Simple Nepali explainers about Nepal",
        center_x=1030,
        y=690,
        font=subtitle_font,
        fill="#dbeafe",
        stroke_fill="#111827",
        stroke_width=1,
    )

    pills = [
        ("नेपालको इतिहास", 740, 840, 340),
        ("रहस्य र तथ्य", 1110, 840, 300),
        ("विकास र अर्थतन्त्र", 1450, 840, 380),
        ("समाचारको सन्दर्भ", 860, 930, 360),
        ("प्रदेश र नक्सा", 1250, 930, 300),
    ]
    for label, x, y, width in pills:
        draw.rounded_rectangle((x, y, x + width, y + 78), radius=28, fill=(10, 20, 37, 230), outline=(255, 255, 255, 42), width=2)
        add_center_text(draw, label, x + (width // 2), y + 18, tag_font, "#e5e7eb", "#020617", 1)

    out_path = BRANDING_DIR / "channel_banner_360_nepal_explained.png"
    banner.save(out_path)
    return out_path


def build_profile() -> Path:
    image = Image.new("RGBA", (800, 800), "#0b1e3b")
    draw = ImageDraw.Draw(image, "RGBA")
    draw.ellipse((40, 40, 760, 760), fill=(9, 30, 58, 255), outline=(255, 255, 255, 40), width=10)
    draw.ellipse((60, 500, 320, 760), fill=(202, 34, 52, 230))
    draw.ellipse((500, 50, 780, 330), fill=(41, 92, 180, 230))

    map_path = ASSETS_DIR / "content images" / "nepal_map.png"
    if map_path.exists():
        nepal_map = Image.open(map_path).convert("RGBA")
        nepal_map = fit_contain(nepal_map, 500, 250)
        image.alpha_composite(nepal_map, dest=(150, 160))

    title_font = load_font(84)
    small_font = load_font(40)
    add_center_text(draw, "360", 400, 430, title_font, "#facc15", "#111827", 2)
    add_center_text(draw, "Nepal Explained", 400, 535, small_font, "#f8fafc", "#111827", 1)

    out_path = BRANDING_DIR / "channel_profile_360_nepal_explained.png"
    image.save(out_path)
    return out_path


def build_watermark() -> Path:
    image = Image.new("RGBA", (150, 150), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image, "RGBA")
    draw.rounded_rectangle((8, 8, 142, 142), radius=28, fill=(195, 29, 55, 245), outline=(255, 255, 255, 70), width=2)
    font_main = load_font(44)
    font_sub = load_font(20)
    add_center_text(draw, "360", 75, 34, font_main, "#fff8e1", "#111827", 1)
    add_center_text(draw, "Nepal", 75, 82, font_sub, "#f8fafc", "#111827", 1)
    add_center_text(draw, "Explained", 75, 104, font_sub, "#f8fafc", "#111827", 1)
    out_path = BRANDING_DIR / "video_watermark_360_nepal_explained.png"
    image.save(out_path)
    return out_path


def main() -> None:
    banner = build_banner()
    profile = build_profile()
    watermark = build_watermark()
    print(banner)
    print(profile)
    print(watermark)


if __name__ == "__main__":
    main()
