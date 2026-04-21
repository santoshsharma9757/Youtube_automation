from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from config import OUTPUT_DIR, get_config


BRANDING_DIR = OUTPUT_DIR / "branding"
BRANDING_DIR.mkdir(parents=True, exist_ok=True)


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    config = get_config()
    if config.font_file.exists():
        return ImageFont.truetype(str(config.font_file), size=size)
    return ImageFont.load_default()


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
    draw.rounded_rectangle((1490, 410, 2190, 860), radius=48, fill=(196, 30, 58, 120))
    draw.rounded_rectangle((1540, 460, 2240, 910), radius=48, fill=(42, 87, 175, 120))

    title_font = load_font(114)
    subtitle_font = load_font(54)
    tag_font = load_font(38)

    add_center_text(draw, "DailyFitX", 1090, 430, title_font, "#f8fafc", "#020617", 2)
    add_center_text(draw, "Fitness • Yoga • Motivation • Recovery", 1030, 610, subtitle_font, "#fde68a", "#111827", 1)
    add_center_text(draw, "Simple, high-retention wellness shorts", 1030, 690, subtitle_font, "#dbeafe", "#111827", 1)

    pills = [
        ("Fat Loss", 760, 840, 220),
        ("Yoga Flow", 1010, 840, 240),
        ("Motivation", 1280, 840, 260),
        ("Breathwork", 840, 930, 260),
        ("Home Workout", 1140, 930, 320),
    ]
    for label, x, y, width in pills:
        draw.rounded_rectangle((x, y, x + width, y + 78), radius=28, fill=(10, 20, 37, 230), outline=(255, 255, 255, 42), width=2)
        add_center_text(draw, label, x + (width // 2), y + 18, tag_font, "#e5e7eb", "#020617", 1)

    out_path = BRANDING_DIR / "channel_banner_dailyfitx.png"
    banner.save(out_path)
    return out_path


def build_profile() -> Path:
    image = Image.new("RGBA", (800, 800), "#0b1e3b")
    draw = ImageDraw.Draw(image, "RGBA")
    draw.ellipse((40, 40, 760, 760), fill=(9, 30, 58, 255), outline=(255, 255, 255, 40), width=10)
    draw.ellipse((60, 500, 320, 760), fill=(202, 34, 52, 230))
    draw.ellipse((500, 50, 780, 330), fill=(41, 92, 180, 230))
    draw.rounded_rectangle((140, 150, 660, 360), radius=40, fill=(255, 255, 255, 18))

    title_font = load_font(84)
    small_font = load_font(40)
    add_center_text(draw, "DFX", 400, 255, title_font, "#facc15", "#111827", 2)
    add_center_text(draw, "DailyFitX", 400, 510, small_font, "#f8fafc", "#111827", 1)

    out_path = BRANDING_DIR / "channel_profile_dailyfitx.png"
    image.save(out_path)
    return out_path


def build_watermark() -> Path:
    image = Image.new("RGBA", (150, 150), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image, "RGBA")
    draw.rounded_rectangle((8, 8, 142, 142), radius=28, fill=(195, 29, 55, 245), outline=(255, 255, 255, 70), width=2)
    font_main = load_font(44)
    font_sub = load_font(20)
    add_center_text(draw, "DFX", 75, 34, font_main, "#fff8e1", "#111827", 1)
    add_center_text(draw, "Daily", 75, 82, font_sub, "#f8fafc", "#111827", 1)
    add_center_text(draw, "FitX", 75, 104, font_sub, "#f8fafc", "#111827", 1)
    out_path = BRANDING_DIR / "video_watermark_dailyfitx.png"
    image.save(out_path)
    return out_path


def main() -> None:
    print(build_banner())
    print(build_profile())
    print(build_watermark())


if __name__ == "__main__":
    main()
