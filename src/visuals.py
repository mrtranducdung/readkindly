from __future__ import annotations
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from textwrap import wrap
import random
import urllib.request
import urllib.parse
import io

WIDTH = 1080
HEIGHT = 1920

STYLE_PREFIX = (
    "children's picture book illustration, cute animal characters, "
    "watercolor painting style, soft pastel colors, whimsical, adorable, "
    "detailed storybook background, golden book art style, "
    "no text, no words, "
)

def _font(size: int):
    for name in ("DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()

def _draw_centered_text(draw: ImageDraw.ImageDraw, text: str, y: int, font, fill, max_chars: int) -> int:
    lines = []
    for paragraph in text.split("\n"):
        lines.extend(wrap(paragraph, width=max_chars))
    if not lines:
        lines = [text]
    current_y = y
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_w = bbox[2] - bbox[0]
        line_h = bbox[3] - bbox[1]
        x = (WIDTH - line_w) // 2
        # drop shadow
        draw.text((x + 3, current_y + 3), line, font=font, fill=(0, 0, 0))
        draw.text((x, current_y), line, font=font, fill=fill)
        current_y += line_h + 14
    return current_y

def _fetch_ai_image(prompt: str) -> Image.Image | None:
    try:
        encoded = urllib.parse.quote(prompt)
        seed = random.randint(1, 99999)
        url = (
            f"https://image.pollinations.ai/prompt/{encoded}"
            f"?width={WIDTH}&height={HEIGHT}&nologo=true&seed={seed}&model=flux"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "kids-tiktok-agent/1.0"})
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = resp.read()
        img = Image.open(io.BytesIO(data)).convert("RGB")
        return img.resize((WIDTH, HEIGHT), Image.LANCZOS)
    except Exception as e:
        print(f"  [image-gen] failed: {e} — using fallback")
        return None

def _fallback_image() -> Image.Image:
    PALETTES = [
        ("#FFE9A8", "#FFB5A7"),
        ("#A0E7E5", "#B4F8C8"),
        ("#FFDAC1", "#C7CEEA"),
        ("#FBE7C6", "#B4F8C8"),
    ]
    bg1, bg2 = random.choice(PALETTES)
    img = Image.new("RGB", (WIDTH, HEIGHT), bg1)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((80, 400, WIDTH - 80, HEIGHT - 400), radius=80, fill=bg2)
    return img

def create_scene_image(scene_title: str, onscreen_text: str, visual_description: str, out_path: Path) -> None:
    print(f"  Generating image for: {scene_title!r}...")
    prompt = STYLE_PREFIX + visual_description
    img = _fetch_ai_image(prompt) or _fallback_image()

    # Semi-transparent overlay panels
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rectangle([(0, 0), (WIDTH, 210)], fill=(10, 10, 30, 190))          # title bar top
    od.rectangle([(0, HEIGHT - 560), (WIDTH, HEIGHT)], fill=(10, 10, 30, 200))  # text panel bottom

    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    title_font = _font(66)
    body_font = _font(78)

    _draw_centered_text(draw, scene_title, 52, title_font, "#FFE566", 22)
    _draw_centered_text(draw, onscreen_text, HEIGHT - 510, body_font, "white", 16)

    img.save(out_path)

def create_all_scenes(story_pack, out_dir: Path) -> list[Path]:
    paths = []
    for scene in story_pack.scenes:
        path = out_dir / f"scene_{scene.scene_number:02d}.png"
        create_scene_image(scene.title, scene.onscreen_text, scene.visual_description, path)
        paths.append(path)
    return paths
