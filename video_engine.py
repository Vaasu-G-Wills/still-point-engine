import os
import re
import gc
import math
import textwrap
import tempfile
import numpy as np
import urllib.request
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import (
    AudioFileClip, ImageClip, VideoFileClip,
    concatenate_videoclips, concatenate_audioclips, CompositeAudioClip,
)
from imageio_ffmpeg import get_ffmpeg_exe

class RenderCancelledException(Exception):
    pass

# ─── Configuration ────────────────────────────────────────────────────────────
# 720p instead of 1080p — cuts per-frame RAM from ~6MB to ~2.8MB (56% reduction)
VIDEO_SIZE   = (1280, 720)
FONT_SIZE    = 44
MAX_CHARS    = 48      # wrap width
SUBTITLE_Y   = 0.76   # lower-third anchor (fraction of height)
FONT_PATH    = "Roboto-Regular.ttf"
SAFE_WIDTH   = int(VIDEO_SIZE[0] * 0.88)  # 88% safe window
AUDIO_SR     = 44100                      # Global master sampling rate

# Ken Burns zoom
ZOOM_START     = 1.0
ZOOM_END       = 1.22   # more cinematic — 22% zoom travel

# Crossfade duration between contextual images (seconds)
CROSSFADE_SECS = 0.6

# ── Sprint 4: Animation settings ─────────────────────────────────────────────
SHOW_QUOTE_CALLOUTS = False  # disabled — use subtitle-only mode
SLIDE_SECS          = 0.20
SLIDE_DIST_PX       = 22
QUOTE_FADE_SECS     = 0.35

# ── Sprint 1: Visual polish settings ─────────────────────────────────────────

# Vignette: 0.0 = none, 1.0 = full black edges
VIGNETTE_STRENGTH = 0.60

# Color grade per section — (R, G, B, alpha 0-255) additive tint
# Set alpha=0 for any section to disable its tint
SECTION_TINTS = {
    "hook":       (255, 235, 180,  18),   # warm golden
    "thesis":     (255, 215, 140,  20),   # amber
    "bridge_ab":  (180, 200, 230,  12),   # cool transitional
    "antithesis": (140, 180, 240,  22),   # steel blue
    "bridge_bc":  (190, 170, 235,  12),   # transitional violet
    "synthesis":  (170, 155, 235,  20),   # soft violet
    "context":    (200, 230, 200,  18),   # cool green
    "deep_dive":  (255, 180, 180,  22),   # intense warm red
    "takeaway":   (180, 220, 255,  20),   # calm bright blue
}

# Ken Burns direction cycle (auto-assigned per image in contextual timeline)
KB_DIRECTIONS = [
    "in_center",   # zoom in, centred
    "in_left",     # zoom in, anchor left (pans right)
    "in_right",    # zoom in, anchor right (pans left)
    "out_center",  # slow zoom out from centre
    "pan_left",    # fixed zoom, pan right-to-left
    "pan_right",   # fixed zoom, pan left-to-right
]

# Particles: floating dust-mote atmosphere
N_PARTICLES      = 35
PARTICLE_MAX_A   = 55    # max opacity (0-255)
_PRNG            = np.random.RandomState(7)   # deterministic seed
_PARTICLES       = {
    "x":     _PRNG.uniform(0, 1, N_PARTICLES),
    "y":     _PRNG.uniform(0, 1, N_PARTICLES),
    "r":     _PRNG.uniform(1.0, 3.5, N_PARTICLES),
    "speed": _PRNG.uniform(0.04, 0.18, N_PARTICLES),
    "phase": _PRNG.uniform(0, 2 * np.pi, N_PARTICLES),
    "drift": _PRNG.uniform(-0.25, 0.25, N_PARTICLES),
    "alpha": _PRNG.uniform(15, PARTICLE_MAX_A, N_PARTICLES).astype(int),
}

def ensure_font():
    if not os.path.exists(FONT_PATH):
        url = "https://github.com/googlefonts/roboto/raw/main/src/hinted/Roboto-Regular.ttf"
        urllib.request.urlretrieve(url, FONT_PATH)

def load_font(size=FONT_SIZE):
    try:
        return ImageFont.truetype(FONT_PATH, size=size)
    except Exception:
        return ImageFont.load_default()

# ─── Syllable Estimator ───────────────────────────────────────────────────────

def estimate_syllables(word: str) -> int:
    word = word.lower().strip(".,!?;:'\"")
    if len(word) <= 2:
        return 1
    count = len(re.findall(r'[aeiou]+', word))
    if word.endswith('e') and count > 1:
        count -= 1
    return max(1, count)

# ─── Background Builder ───────────────────────────────────────────────────────

def make_bg_base(size, bg_image_path=None):
    """
    Load and pre-process the background image once per node.
    Returns a PIL Image at exactly `size` — the Ken Burns zoom expands
    this on-the-fly via resize-then-crop, so no pre-oversizing needed.
    """
    W, H = size
    if bg_image_path and os.path.exists(bg_image_path):
        img = Image.open(bg_image_path).convert("RGB")
        try:
            resample = Image.Resampling.LANCZOS
        except AttributeError:
            resample = Image.ANTIALIAS
        img = img.resize((W, H), resample)
        # Darken for subtitle readability
        dim = Image.new('RGB', (W, H), (0, 0, 0))
        img = Image.blend(img, dim, 0.45)
    else:
        img = Image.new('RGB', (W, H), color=(18, 18, 18))
    return img


def make_zoomed_frame(
    base_img_np:  np.ndarray,
    t:            float,
    total_duration: float,
    out_size:     tuple,
    direction:    str = "in_center",
) -> np.ndarray:
    """
    Ken Burns zoom using resize-then-crop.
    `direction` controls where the crop window sits, creating pan/zoom/out variety.
    """
    W, H = out_size

    try:
        lanczos = Image.Resampling.LANCZOS
    except AttributeError:
        lanczos = Image.LANCZOS

    progress   = t / max(total_duration, 0.001)  # 0.0 → 1.0

    if direction == "out_center":
        # Zoom OUT: start at ZOOM_END, end at ZOOM_START
        scale = ZOOM_END - (ZOOM_END - ZOOM_START) * progress
    else:
        scale = ZOOM_START + (ZOOM_END - ZOOM_START) * progress

    new_w = math.ceil(W * scale); new_w += new_w % 2
    new_h = math.ceil(H * scale); new_h += new_h % 2

    img = Image.fromarray(base_img_np).resize((new_w, new_h), lanczos)

    cx = (new_w - W) // 2
    cy = (new_h - H) // 2

    if direction == "in_left":
        x = max(0, cx // 4)           # anchor near left, drift right
        y = cy
    elif direction == "in_right":
        x = min(new_w - W, cx + cx * 3 // 4)   # anchor near right, drift left
        y = cy
    elif direction == "pan_left":
        x = int((new_w - W) * (1.0 - progress))  # start right, drift left
        y = cy
    elif direction == "pan_right":
        x = int((new_w - W) * progress)           # start left, drift right
        y = cy
    else:  # in_center or out_center
        x, y = cx, cy

    x = max(0, min(x, new_w - W))
    y = max(0, min(y, new_h - H))
    img = img.crop([x, y, x + W, y + H])
    if img.size != (W, H):
        img = img.resize((W, H), lanczos)

    result = np.array(img)
    img.close()
    return result


# ── Sprint 1 helpers ──────────────────────────────────────────────────────────

def _build_vignette(size: tuple, strength: float) -> np.ndarray:
    """Pre-compute a (H, W, 1) float32 multiplicative vignette mask."""
    W, H = size
    cx, cy = W / 2.0, H / 2.0
    Y, X = np.ogrid[:H, :W]
    dist  = np.sqrt(((X - cx) / cx) ** 2 + ((Y - cy) / cy) ** 2)
    mask  = 1.0 - strength * np.clip(dist ** 1.5, 0, 1)
    return np.clip(mask, 0, 1).astype(np.float32)[:, :, np.newaxis]

# Pre-compute once at module load (cheap, ~1ms)
_VIGNETTE = _build_vignette(VIDEO_SIZE, VIGNETTE_STRENGTH)


def apply_vignette(frame_np: np.ndarray) -> np.ndarray:
    """Darken frame edges. Pure numpy multiply — ~0.5ms per frame."""
    return np.clip(frame_np.astype(np.float32) * _VIGNETTE, 0, 255).astype(np.uint8)


def apply_color_grade(frame_np: np.ndarray, node_name: str) -> np.ndarray:
    """Add a subtle colour tint to signal the dialectic phase."""
    tint = SECTION_TINTS.get(node_name)
    if not tint:
        return frame_np
    r, g, b, alpha = tint
    if alpha == 0:
        return frame_np
    tint_f = np.array([r, g, b], dtype=np.float32) * (alpha / 255.0)
    return np.clip(frame_np.astype(np.float32) + tint_f, 0, 255).astype(np.uint8)


def apply_particles(frame_np: np.ndarray, t: float, out_size: tuple) -> np.ndarray:
    """
    Composite floating dust-mote particles onto the frame.
    Uses sinusoidal motion seeded deterministically — ~2ms per frame.
    """
    W, H = out_size
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw    = ImageDraw.Draw(overlay)

    p = _PARTICLES
    for i in range(N_PARTICLES):
        # Gentle float upward + sinusoidal sway
        y_pos = (p["y"][i] - p["speed"][i] * t * 0.015) % 1.0
        x_pos = (p["x"][i] + p["drift"][i] * math.sin(p["phase"][i] + t * p["speed"][i])) % 1.0
        px, py = int(x_pos * W), int(y_pos * H)
        r = max(1, int(p["r"][i]))
        draw.ellipse([px - r, py - r, px + r, py + r], fill=(255, 255, 255, p["alpha"][i]))

    base   = Image.fromarray(frame_np).convert("RGBA")
    result = np.array(Image.alpha_composite(base, overlay).convert("RGB"))
    base.close(); overlay.close()
    return result

def _load_timeline_images(bg_timeline: list[dict], total_duration: float) -> list[dict]:
    """
    Pre-loads all images in a contextual timeline as numpy arrays,
    computes time boundaries, and assigns a KB direction to each image.
    """
    total_chars = sum(item.get("char_count", 1) for item in bg_timeline) or 1
    loaded  = []
    t_cursor = 0.0
    for idx, item in enumerate(bg_timeline):
        frac      = item.get("char_count", 1) / total_chars
        t_end     = t_cursor + frac * total_duration
        bg_pil    = make_bg_base(VIDEO_SIZE, item.get("path"))
        bg_np     = np.array(bg_pil)
        direction = KB_DIRECTIONS[idx % len(KB_DIRECTIONS)]   # cycle directions
        loaded.append({
            **item,
            "np":        bg_np,
            "t_start":   t_cursor,
            "t_end":     t_end,
            "direction": direction,
        })
        t_cursor = t_end
    if loaded:
        loaded[-1]["t_end"] = total_duration
    return loaded



# ─── Sprint 2: Card Renderers ────────────────────────────────────────────────

def _card_base(color=(8, 8, 12)) -> Image.Image:
    """Return a fresh dark card at VIDEO_SIZE."""
    return Image.new("RGB", VIDEO_SIZE, color)


def _lanczos():
    try:
        return Image.Resampling.LANCZOS
    except AttributeError:
        return Image.LANCZOS


def draw_progress_bar(
    frame_np:       np.ndarray,
    t:              float,
    total_duration: float,
    node_idx:       int = 0,
    total_nodes:    int = 1,
    node_name:      str = "",
) -> np.ndarray:
    """
    Draw a 3px progress bar at the very bottom of the frame.
    Shows OVERALL video progress, coloured by section tint.
    """
    W, H = VIDEO_SIZE
    node_progress  = t / max(total_duration, 0.001)
    overall        = (node_idx + node_progress) / max(total_nodes, 1)
    bar_w          = max(1, int(W * overall))

    tint = SECTION_TINTS.get(node_name, (170, 155, 235, 255))
    colour = np.array([tint[0], tint[1], tint[2]], dtype=np.uint8)

    result = frame_np.copy()
    result[H - 3 : H, :bar_w] = colour
    return result


def _render_styled_text_card(
    main_text:    str,
    sub_text:     str  = "",
    rule_color:   tuple = (170, 150, 230),
    main_size:    int   = 64,
    sub_size:     int   = 32,
) -> np.ndarray:
    """
    Render a full-frame dark card with:
      ─── rule ───
        main_text
      ─── rule ───
        sub_text
    Returns a numpy RGB array.
    """
    W, H = VIDEO_SIZE
    card = _card_base()
    draw = ImageDraw.Draw(card)

    font_main = load_font(main_size)
    font_sub  = load_font(sub_size)

    # Measure main text
    bb    = draw.textbbox((0, 0), main_text, font=font_main)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]

    cy = H // 2
    # Rules extend a little wider than the text
    rule_w  = min(tw + 140, W - 120)
    rule_x1 = (W - rule_w) // 2
    rule_x2 = rule_x1 + rule_w

    # Top rule
    rule_top_y = cy - th // 2 - 28
    draw.line([(rule_x1, rule_top_y), (rule_x2, rule_top_y)], fill=rule_color, width=1)

    # Main text
    tx = (W - tw) // 2
    ty = cy - th // 2 - bb[1]
    draw.text((tx, ty), main_text, font=font_main, fill=(235, 235, 240))

    # Bottom rule
    rule_bot_y = cy + th // 2 + th // 4 + 18
    draw.line([(rule_x1, rule_bot_y), (rule_x2, rule_bot_y)], fill=rule_color, width=1)

    # Sub-text below rules
    if sub_text:
        bb2 = draw.textbbox((0, 0), sub_text, font=font_sub)
        tw2 = bb2[2] - bb2[0]
        draw.text(
            ((W - tw2) // 2, rule_bot_y + 20 - bb2[1]),
            sub_text, font=font_sub,
            fill=(140, 128, 185),
        )

    return np.array(card)


def make_title_card_clip(title: str, duration: float = 2.5):
    """
    Section title card — fade in → hold → fade out.
    Returns a MoviePy ImageClip.
    """
    from moviepy.editor import ImageClip
    fade = min(0.4, duration * 0.3)
    frame = _render_styled_text_card(title, rule_color=(150, 130, 210))
    return ImageClip(frame).set_duration(duration).fadein(fade).fadeout(fade)


def make_intro_clip(topic: str, duration: float = 4.0):
    """
    Opening title sequence — topic name + programme brand.
    Returns a MoviePy ImageClip.
    """
    from moviepy.editor import ImageClip
    from config import CHANNEL_NAME
    fade = min(0.6, duration * 0.25)
    frame = _render_styled_text_card(
        main_text  = topic,
        sub_text   = CHANNEL_NAME,
        rule_color = (200, 180, 255),
        main_size  = 72,
        sub_size   = 30,
    )
    return ImageClip(frame).set_duration(duration).fadein(fade).fadeout(fade)


def make_outro_clip(next_topic: str = "", duration: float = 5.0):
    """
    Outro subscribe card.
    Returns a MoviePy ImageClip.
    """
    from moviepy.editor import ImageClip
    from config import CHANNEL_NAME, CHANNEL_HANDLE
    fade = min(0.6, duration * 0.2)

    W, H = VIDEO_SIZE
    card = _card_base((5, 5, 10))
    draw = ImageDraw.Draw(card)

    font_lg = load_font(68)
    font_md = load_font(34)
    font_sm = load_font(26)

    cy = H // 2 - 20

    # Channel name
    bb = draw.textbbox((0, 0), CHANNEL_NAME, font=font_lg)
    tw = bb[2] - bb[0]
    draw.text(((W - tw) // 2, cy - 60 - bb[1]), CHANNEL_NAME, font=font_lg, fill=(235, 235, 240))

    # Handle + subscribe prompt
    handle_text = f"@{CHANNEL_HANDLE}  ·  Subscribe"
    bb2 = draw.textbbox((0, 0), handle_text, font=font_md)
    tw2 = bb2[2] - bb2[0]
    draw.text(((W - tw2) // 2, cy + 10 - bb2[1]), handle_text, font=font_md, fill=(160, 140, 215))

    # Decorative rule
    line_w = min(tw2 + 80, W - 160)
    lx = (W - line_w) // 2
    draw.line([(lx, cy + 54), (lx + line_w, cy + 54)], fill=(90, 80, 130), width=1)

    # Next topic teaser
    if next_topic:
        teaser = f"Next: {next_topic}"
        bb3 = draw.textbbox((0, 0), teaser, font=font_sm)
        tw3 = bb3[2] - bb3[0]
        draw.text(((W - tw3) // 2, cy + 70 - bb3[1]), teaser, font=font_sm, fill=(120, 110, 160))

    frame = np.array(card)
    return ImageClip(frame).set_duration(duration).fadein(fade).fadeout(fade)


# ─── Frame Renderer ───────────────────────────────────────────────────────────

def draw_quote_callout(
    base_frame_np: np.ndarray,
    quote_text:    str,
    font_large,
    opacity:       float = 1.0,
) -> np.ndarray:
    """
    Full-screen cinematic quote moment.
    Dims the background, centres the quote with decorative marks.
    opacity (0-1) drives the fade-in / fade-out blend.
    """
    W, H = VIDEO_SIZE
    # 1. Dim background
    frame = Image.fromarray(base_frame_np).convert("RGBA")
    dim   = Image.new("RGBA", (W, H), (0, 0, 0, int(175 * opacity)))
    frame = Image.alpha_composite(frame, dim)
    draw  = ImageDraw.Draw(frame)

    # 2. Opening quotation mark (decorative, top-left of text block)
    font_q = load_font(100)
    font_t = font_large

    # Wrap text
    wrapped = "\n".join(textwrap.wrap(quote_text, width=42))
    lines   = wrapped.split("\n")

    bbs         = [draw.textbbox((0, 0), ln, font=font_t) for ln in lines]
    line_hs     = [bb[3] - bb[1] for bb in bbs]
    line_ws     = [bb[2] - bb[0] for bb in bbs]
    block_h     = sum(line_hs) + 12 * (len(lines) - 1)
    block_w     = max(line_ws) if line_ws else 0

    cy      = H // 2
    start_y = cy - block_h // 2
    start_x = (W - block_w) // 2

    # Decorative open-quote mark
    qbb = draw.textbbox((0, 0), "\u201c", font=font_q)
    col_quote = (200, 175, 255, int(160 * opacity))
    draw.text(
        (start_x - 10, start_y - 55 - qbb[1]),
        "\u201c", font=font_q, fill=col_quote,
    )

    # Text lines
    col_text   = (245, 242, 255, int(255 * opacity))
    col_shadow = (0,   0,   0,   int(200 * opacity))
    y = start_y
    for i, line in enumerate(lines):
        lw = line_ws[i]
        x  = (W - lw) // 2
        asc = bbs[i][1]
        draw.text((x + 2, y - asc + 2), line, font=font_t, fill=col_shadow)
        draw.text((x,     y - asc),     line, font=font_t, fill=col_text)
        y += line_hs[i] + 12

    # Thin rule below
    rule_w = min(block_w + 100, W - 120)
    rx = (W - rule_w) // 2
    ry = start_y + block_h + 22
    draw.line([(rx, ry), (rx + rule_w, ry)],
              fill=(170, 145, 230, int(150 * opacity)), width=1)

    return np.array(frame.convert("RGB"))


def draw_subtitle_on_frame(base_img, text, font, highlight_word=None,
                           highlight_word_idx: int = -1, y_offset: int = 0,
                           subtitle_mode: str = "chunk"):
    """
    Render subtitles onto base_img.
    highlight_word_idx: the exact positional index (0-based) of the word to
    highlight in yellow — prevents duplicate matches (e.g. multiple 'of').
    subtitle_mode: 'sentence', 'chunk', or 'word'
    """
    if not text:
        return np.array(base_img)
    img = base_img.copy()
    W, H = img.size

    # --- WORD MODE (PREMIUM HIGHLIGHT) ---
    if subtitle_mode == "word" and highlight_word:
        draw = ImageDraw.Draw(img, "RGBA")
        
        # Load fonts
        main_font = font # Normal size for full sentence
        active_font = load_font(int(font.size * 1.15)) # Slightly larger for active word
        
        # Wrap the full sentence context
        wrapped  = "\n".join(textwrap.wrap(text, width=MAX_CHARS))
        lines    = wrapped.split("\n")
        
        line_bboxes   = [draw.textbbox((0, 0), line, font=main_font) for line in lines]
        line_heights  = [bb[3] - bb[1] for bb in line_bboxes]
        line_widths   = [bb[2] - bb[0] for bb in line_bboxes]
        line_spacing  = 12
        block_h       = sum(line_heights) + line_spacing * (len(lines) - 1)
        block_w       = max(line_widths) if line_widths else 0

        anchor_y = int(H * SUBTITLE_Y) + y_offset
        
        # Draw pill background
        pad_x, pad_y = 30, 16
        pill = [(W-block_w)//2 - pad_x, anchor_y - pad_y, (W+block_w)//2 + pad_x, anchor_y + block_h + pad_y]
        overlay = Image.new("RGBA", img.size, (0,0,0,0))
        ov_draw = ImageDraw.Draw(overlay)
        ov_draw.rounded_rectangle(pill, radius=16, fill=(0,0,0,140))
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
        draw = ImageDraw.Draw(img, "RGBA")

        # --- PIXEL-BASED WRAPPING (The "Safe Window" Fix) ---
        words = text.split()
        lines = []
        current_line = []
        for w in words:
            test_line = " ".join(current_line + [w])
            w_bb = draw.textbbox((0, 0), test_line, font=main_font)
            if (w_bb[2] - w_bb[0]) <= SAFE_WIDTH:
                current_line.append(w)
            else:
                lines.append(" ".join(current_line))
                current_line = [w]
        if current_line:
            lines.append(" ".join(current_line))

        y_cursor = anchor_y
        global_w = 0
        for i, line in enumerate(lines):
            # Recalculate width for centering
            l_bb = draw.textbbox((0, 0), line, font=main_font)
            lw = l_bb[2] - l_bb[0]
            lh = l_bb[3] - l_bb[1]
            x_cursor = (W - lw) / 2
            ascender_off = l_bb[1]
            
            for w in line.split():
                is_active = (global_w == highlight_word_idx)
                f = active_font if is_active else main_font
                
                # Active word gets a glow and bright color
                col = (255, 235, 60, 255) if is_active else (255, 255, 255, 160) # Muted white for inactive
                
                # Calculate bounds for current word
                w_bb = draw.textbbox((0, 0), w + " ", font=f)
                ww = w_bb[2] - w_bb[0]
                
                if is_active:
                    # Glow/Outer Shadow for active word
                    for off in [1, 2]:
                        draw.text((x_cursor+off, y_cursor-ascender_off+off), w + " ", font=f, fill=(0,0,0,100))
                    draw.text((x_cursor, y_cursor-ascender_off), w + " ", font=f, fill=(255, 255, 255, 255))
                    draw.text((x_cursor, y_cursor-ascender_off), w + " ", font=f, fill=col)
                else:
                    draw.text((x_cursor, y_cursor-ascender_off), w + " ", font=f, fill=col)
                
                x_cursor += ww
                global_w += 1
            y_cursor += line_heights[i] + line_spacing
        return np.array(img)

    # --- CHUNK & SENTENCE MODE ---

    wrapped  = "\n".join(textwrap.wrap(text, width=MAX_CHARS))
    lines    = wrapped.split("\n")

    draw          = ImageDraw.Draw(img, "RGBA")
    line_bboxes   = [draw.textbbox((0, 0), line, font=font) for line in lines]
    line_heights  = [bb[3] - bb[1] for bb in line_bboxes]
    line_widths   = [bb[2] - bb[0] for bb in line_bboxes]
    line_spacing  = 10
    block_h       = sum(line_heights) + line_spacing * (len(lines) - 1)
    block_w       = max(line_widths) if line_widths else 0

    anchor_y = int(H * SUBTITLE_Y) + y_offset
    anchor_y = min(anchor_y, H - block_h - 30)

    # Semi-transparent pill background for readability
    pad_x, pad_y = 30, 14
    pill = [
        (W - block_w) // 2 - pad_x,
        anchor_y - pad_y,
        (W + block_w) // 2 + pad_x,
        anchor_y + block_h + pad_y,
    ]
    overlay    = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ov_draw    = ImageDraw.Draw(overlay)
    ov_draw.rounded_rectangle(pill, radius=14, fill=(0, 0, 0, 155))
    img        = img.convert("RGBA")
    img        = Image.alpha_composite(img, overlay).convert("RGB")
    draw       = ImageDraw.Draw(img)

    y_cursor = anchor_y
    global_w  = 0        # tracks absolute word position across wrapped lines
    for i, line in enumerate(lines):
        bb           = line_bboxes[i]
        ascender_off = bb[1]
        lw           = bb[2] - bb[0]
        x            = (W - lw) / 2

        if highlight_word:
            cursor_x = x
            for w in line.split():
                wb  = draw.textbbox((0, 0), w + " ", font=font)
                ww  = wb[2] - wb[0]
                # Only highlight the word at the exact index stored in the segment
                is_hl = (
                    w.lower().strip(".,!?;:'\"") ==
                    highlight_word.lower().strip(".,!?;:'\"")
                    and global_w == highlight_word_idx
                )
                col = (255, 220, 0) if is_hl else (255, 255, 255)
                draw.text((cursor_x + 2, y_cursor - ascender_off + 2), w + " ", font=font, fill=(0, 0, 0))
                draw.text((cursor_x,     y_cursor - ascender_off),     w + " ", font=font, fill=col)
                cursor_x += ww
                global_w += 1
        else:
            draw.text((x + 2, y_cursor - ascender_off + 2), line, font=font, fill=(0, 0, 0))
            draw.text((x,     y_cursor - ascender_off),     line, font=font, fill=(255, 255, 255))
            global_w += len(line.split())

        y_cursor += line_heights[i] + line_spacing

    return np.array(img)

# ─── Sprint 3: Music Helper ───────────────────────────────────────────────────

# Which mood track to use per section (first match wins)
_MUSIC_MAP = {
    "hook":       ["contemplative", "resolved"],
    "thesis":     ["contemplative"],
    "bridge_ab":  ["tense", "contemplative"],
    "antithesis": ["tense"],
    "bridge_bc":  ["tense", "resolved"],
    "synthesis":  ["resolved", "contemplative"],
    "context":    ["contemplative"],
    "deep_dive":  ["tense", "contemplative"],
    "takeaway":   ["resolved", "contemplative"],
}
_AUDIO_EXTS = ["mp3", "wav", "ogg", "m4a", "flac"]


def _get_music_clip(node_name: str, duration: float):
    """
    Load the ambient track for a node, loop it to `duration`, and apply
    MUSIC_VOLUME.

    Returns a MoviePy AudioClip, or None if the music/ folder is empty.
    """
    from config import MUSIC_DIR, MUSIC_VOLUME
    if not os.path.isdir(MUSIC_DIR):
        return None

    prefs = _MUSIC_MAP.get(node_name, ["contemplative"])
    for pref in prefs:
        for ext in _AUDIO_EXTS:
            path = os.path.join(MUSIC_DIR, f"{pref}.{ext}")
            if os.path.exists(path):
                try:
                    track = AudioFileClip(path)
                    if track.duration < duration:
                        loops = math.ceil(duration / track.duration)
                        track = concatenate_audioclips([track] * loops)
                    return track.subclip(0, duration).volumex(MUSIC_VOLUME)
                except Exception as e:
                    print(f"[music] {path}: {e}")
    return None


# ─── Node Renderer — writes ONE node directly to a temp file ─────────────────

def render_node_to_tempfile(
    text_block,
    audio_path,
    bg_path      = None,
    bg_timeline  = None,
    node_name    = "",
    node_idx     = 0,
    total_nodes  = 1,
    key_quotes   = None,   # list[str] — sentences that trigger full-screen callout
    word_by_word = True,
    subtitle_mode = "chunk",
    tmp_dir      = None,
    check_cancel = None,
):
    """
    Renders ONE dialectic node to a temporary .mp4 file.

    Visual pipeline per frame:
      zoom (Ken Burns) → color grade → particles → vignette → subtitles
    """
    if not os.path.exists(audio_path):
        return None

    from moviepy.editor import VideoClip

    audio_clip     = AudioFileClip(audio_path)
    total_duration = audio_clip.duration
    font           = load_font(FONT_SIZE)

    # ── Optional music mix ───────────────────────────────────────────
    music_clip = _get_music_clip(node_name, total_duration)
    if music_clip:
        mixed_audio = CompositeAudioClip([audio_clip, music_clip])
        print(f"[music] Mixed into {node_name} at {total_duration:.1f}s")
    else:
        mixed_audio = audio_clip

    # ── Prepare background(s) ────────────────────────────────────────
    if bg_timeline and len(bg_timeline) > 0:
        loaded_timeline = _load_timeline_images(bg_timeline, total_duration)
        use_timeline    = True
        simple_dir      = "in_center"  # unused in timeline mode
    else:
        base_bg_pil = make_bg_base(VIDEO_SIZE, bg_path)
        base_bg_np  = np.array(base_bg_pil)
        del base_bg_pil
        use_timeline = False
        # Assign a unique KB direction per node so every section moves differently
        simple_dir   = KB_DIRECTIONS[node_idx % len(KB_DIRECTIONS)]

    # ── Build subtitle segments ───────────────────────────────────────
    sentences  = re.split(r'(?<=[.!?]) +', text_block.replace('\n', ' '))
    sentences  = [s.strip() for s in sentences if len(s.strip()) > 2] or [text_block.strip()]
    segments   = []
    elapsed    = 0.0

    # ── WORD MODE: try forced-alignment timestamps first ─────────────
    if subtitle_mode == "word":
        forced_timestamps = []
        try:
            from aligner import load_timestamps
            forced_timestamps = load_timestamps(audio_path)
        except Exception:
            pass  # silently degrade to syllable fallback

        if forced_timestamps:
            # Map timestamped words back to sentences for visual context
            word_ptr = 0
            for sent in sentences:
                sent_words = sent.split()
                for i, s_word in enumerate(sent_words):
                    if word_ptr < len(forced_timestamps):
                        entry = forced_timestamps[word_ptr]
                        # 0.03s lead-in for more natural human response time
                        t0 = max(0, float(entry.get("start", 0)) - 0.03)
                        t1 = float(entry.get("end", 0))
                        segments.append((sent, s_word, i, t0, t1))
                        word_ptr += 1
            print(f"[video_engine] Robust Whisper-aligned segments built: {len(segments)} words from {node_name}")

    # ── CHUNK / SENTENCE / WORD-fallback (syllable estimation) ───────
    if not segments and word_by_word:
        all_words_flat = [(w, sent) for sent in sentences for w in sent.split() if w.strip()]
        total_syl = sum(estimate_syllables(w) for w, _ in all_words_flat) or len(all_words_flat)
        sent_word_counts: dict = {}

        CHUNK_SIZE = 6
        if subtitle_mode == "chunk":
            chunked_words = []
            for i in range(0, len(all_words_flat), CHUNK_SIZE):
                chunk = all_words_flat[i:i+CHUNK_SIZE]
                chunk_text = " ".join([w for w, _ in chunk])
                for w, _ in chunk:
                    chunked_words.append((w, chunk_text))
            all_words = chunked_words
        else:
            all_words = all_words_flat

        for word, context in all_words:
            pos = sent_word_counts.get(context, 0)
            sent_word_counts[context] = pos + 1
            syl = estimate_syllables(word)
            dur = max((syl / total_syl) * total_duration, 0.08)
            segments.append((context, word, pos, elapsed, elapsed + dur))
            elapsed += dur

    elif not segments:
        total_chars = sum(len(s) for s in sentences) or 1
        for sentence in sentences:
            dur = (len(sentence) / total_chars) * total_duration
            segments.append((sentence, None, 0, elapsed, elapsed + dur))
            elapsed += dur

    # ── Pre-compute sentence time bounds (needed for quote fade timing) ───
    sentence_bounds = {}   # sentence_text -> [t_start, t_end]
    for seg_text, _, _idx, t0, t1 in segments:
        if seg_text not in sentence_bounds:
            sentence_bounds[seg_text] = [t0, t1]
        else:
            sentence_bounds[seg_text][0] = min(sentence_bounds[seg_text][0], t0)
            sentence_bounds[seg_text][1] = max(sentence_bounds[seg_text][1], t1)

    # ── Identify which sentences are key quotes (fuzzy match) ────────────
    _quotes = key_quotes or []
    def _is_quote(sentence: str) -> bool:
        sl = sentence.lower()
        for q in _quotes:
            ql = q.lower()
            if ql in sl or sl in ql:
                return True
            sw = set(sl.split()); qw = set(ql.split())
            if qw and len(qw & sw) / len(qw) > 0.80:
                return True
        return False
    quote_sentences = {s for s in sentence_bounds if _is_quote(s)}
    def make_frame(t):
        if check_cancel and check_cancel():
            raise RenderCancelledException("Render cancelled by user")

        # ─ 1. Ken Burns zoom (with direction) ───────────────────────
        if use_timeline:
            active_np  = loaded_timeline[-1]["np"]
            active_dir = loaded_timeline[-1].get("direction", "in_center")
            next_np    = None
            next_dir   = "in_center"
            blend_frac = 0.0
            for i, seg in enumerate(loaded_timeline):
                if seg["t_start"] <= t < seg["t_end"]:
                    active_np  = seg["np"]
                    active_dir = seg.get("direction", "in_center")
                    time_to_end = seg["t_end"] - t
                    if time_to_end < CROSSFADE_SECS and i + 1 < len(loaded_timeline):
                        next_np    = loaded_timeline[i + 1]["np"]
                        next_dir   = loaded_timeline[i + 1].get("direction", "in_center")
                        blend_frac = 1.0 - (time_to_end / CROSSFADE_SECS)
                    break

            zoomed = make_zoomed_frame(active_np, t, total_duration, VIDEO_SIZE, active_dir)
            if next_np is not None and blend_frac > 0:
                zoomed_next = make_zoomed_frame(next_np, t, total_duration, VIDEO_SIZE, next_dir)
                zoomed = (zoomed * (1.0 - blend_frac) + zoomed_next * blend_frac).astype(np.uint8)
        else:
            zoomed = make_zoomed_frame(base_bg_np, t, total_duration, VIDEO_SIZE, simple_dir)

        # ─ 2. Color grade (section tint) ────────────────────────────
        zoomed = apply_color_grade(zoomed, node_name)

        # ─ 3. Floating particle overlay ─────────────────────────────
        zoomed = apply_particles(zoomed, t, VIDEO_SIZE)

        # ─ 4. Vignette (darkened edges) ─────────────────────────────
        zoomed = apply_vignette(zoomed)

        # ─ 5. Progress bar ───────────────────────────────────────────
        from config import SHOW_PROGRESS_BAR
        if SHOW_PROGRESS_BAR:
            zoomed = draw_progress_bar(zoomed, t, total_duration, node_idx, total_nodes, node_name)

        return zoomed

    tmp_path = os.path.join(tmp_dir or tempfile.gettempdir(), f"node_{os.urandom(4).hex()}.mp4")
    node_vid = VideoClip(make_frame, duration=total_duration).set_audio(mixed_audio)
    node_vid.write_videofile(
        tmp_path, 
        fps=24, 
        codec="libx264", 
        audio_codec="aac", 
        audio_fps=AUDIO_SR,
        logger=None,
        ffmpeg_params=["-vsync", "cfr"]
    )

    node_vid.close()
    audio_clip.close()
    if music_clip:
        music_clip.close()
    if use_timeline:
        del loaded_timeline
    else:
        del base_bg_np
    del segments, node_vid, audio_clip
    gc.collect()

    return tmp_path

# ─── Master Video Builder ─────────────────────────────────────────────────────

def render_card_to_tempfile(card_clip, duration, tmp_dir):
    """
    Renders an ImageClip card to a temporary .mp4 with a silent audio track
    so it matches nodes' codec/audio properties for FFMPEG copy concatenation.
    """
    from moviepy.editor import AudioClip
    silent_audio = AudioClip(lambda t: 0.0, duration=duration, fps=AUDIO_SR)
    card_clip = card_clip.set_audio(silent_audio)
    
    tmp_path = os.path.join(tmp_dir, f"card_{os.urandom(4).hex()}.mp4")
    card_clip.write_videofile(
        tmp_path,
        fps=24,
        codec="libx264",
        audio_codec="aac",
        audio_fps=AUDIO_SR,
        logger=None,
        ffmpeg_params=["-vsync", "cfr"]
    )
    card_clip.close()
    silent_audio.close()
    return tmp_path

def build_master_video(
    topic_dir,
    script_data,
    bg_images         = None,
    bg_timelines      = None,
    section_titles    = None,   # {node: "Chapter title"} — generated by LLM if None
    next_topic        = "",     # shown in outro CTA
    word_by_word      = True,
    subtitle_mode     = "chunk",
    progress_callback = None,
    check_cancel      = None,
):
    from config import (
        SHOW_INTRO_CARD, SHOW_TITLE_CARDS, SHOW_OUTRO_CARD,
        TITLE_CARD_SECS, INTRO_CARD_SECS, OUTRO_CARD_SECS,
    )
    ensure_font()
    if bg_images    is None: bg_images    = {}
    if bg_timelines is None: bg_timelines = {}

    topic        = script_data.get("topic", "")
    sections     = script_data.get("sections", {})
    audio_folder = os.path.join(topic_dir, "audio")
    tmp_dir      = os.path.join(topic_dir, "_tmp")
    os.makedirs(tmp_dir, exist_ok=True)

    # ── LLM Quote Identification ─────────────────────────────────────
    key_quotes = []
    if SHOW_QUOTE_CALLOUTS:
        if progress_callback:
            progress_callback(0, 1, "💬 Identifying key quotes…")
        try:
            from title_gen import identify_key_quotes
            key_quotes = identify_key_quotes(topic, sections)
            print(f"[video_engine] Key quotes: {key_quotes}")
        except Exception as e:
            print(f"[video_engine] Quote identification failed: {e}")

    # ── LLM Section Titles ────────────────────────────────────────────
    if section_titles is None and SHOW_TITLE_CARDS:
        if progress_callback:
            progress_callback(0, 1, "🧠 Generating chapter titles…")
        try:
            from title_gen import generate_section_titles
            section_titles = generate_section_titles(topic, sections)
        except Exception as e:
            print(f"[video_engine] Title gen failed: {e}")
            section_titles = {}
    section_titles = section_titles or {}

    nodes = [
        ("hook",       sections.get("hook", "")),
        ("thesis",     sections.get("thesis", "")),
        ("bridge_ab",  sections.get("bridge_ab", "")),
        ("antithesis", sections.get("antithesis", "")),
        ("bridge_bc",  sections.get("bridge_bc", "")),
        ("synthesis",  sections.get("synthesis", "")),
        ("context",    sections.get("context", "")),
        ("deep_dive",  sections.get("deep_dive", "")),
        ("takeaway",   sections.get("takeaway", "")),
    ]
    nodes_to_render = [
        (n, t) for n, t in nodes
        if t.strip() and os.path.exists(os.path.join(audio_folder, f"{n}.wav"))
    ]
    total = len(nodes_to_render)

    temp_files = []
    elapsed_time = 0.0
    master_word_timestamps = []

    # ── Intro title card ─────────────────────────────────────────────
    if SHOW_INTRO_CARD and topic:
        if progress_callback:
            progress_callback(0, total, "🎞️ Rendering intro card…")
        intro_clip = make_intro_clip(topic, INTRO_CARD_SECS)
        intro_path = render_card_to_tempfile(intro_clip, INTRO_CARD_SECS, tmp_dir)
        temp_files.append(intro_path)
        elapsed_time += INTRO_CARD_SECS

    # ── Node render loop ─────────────────────────────────────────────
    for idx, (node_name, text) in enumerate(nodes_to_render):
        audio_path  = os.path.join(audio_folder, f"{node_name}.wav")
        bg_timeline = bg_timelines.get(node_name)
        bg_path     = None if bg_timeline else (bg_images.get(node_name) or bg_images.get("thesis"))

        # Insert title card before the node (not bridges, which have no title)
        if SHOW_TITLE_CARDS and node_name in section_titles:
            title = section_titles[node_name]
            print(f"[video_engine] Title card: \"{title}\"")
            title_clip = make_title_card_clip(title, TITLE_CARD_SECS)
            title_path = render_card_to_tempfile(title_clip, TITLE_CARD_SECS, tmp_dir)
            temp_files.append(title_path)
            elapsed_time += TITLE_CARD_SECS

        label = node_name.replace("_", " → ").capitalize()
        if progress_callback:
            progress_callback(idx, total, f"🎬 Rendering {idx+1}/{total}: {label}")

        print(f"[video_engine] Rendering node: {node_name} "
              f"({'contextual: ' + str(len(bg_timeline)) + ' images' if bg_timeline else 'simple bg'})...")
        tmp_path = render_node_to_tempfile(
            text_block   = text,
            audio_path   = audio_path,
            bg_path      = bg_path,
            bg_timeline  = bg_timeline,
            node_name    = node_name,
            node_idx     = idx,
            total_nodes  = total,
            key_quotes   = key_quotes,
            word_by_word = word_by_word,
            subtitle_mode = subtitle_mode,
            tmp_dir      = tmp_dir,
            check_cancel = check_cancel,
        )
        if tmp_path:
            temp_files.append(tmp_path)
            
            # Read clip duration using VideoFileClip to adjust total elapsed_time
            node_vid = VideoFileClip(tmp_path)
            node_duration = node_vid.duration
            node_vid.close()
            
            # Map timestamps from aligner.py into our cumulative master timestamps
            from aligner import load_timestamps
            node_ts = load_timestamps(audio_path)
            for ts in node_ts:
                master_word_timestamps.append({
                    "word": ts["word"],
                    "start": ts["start"] + elapsed_time,
                    "end": ts["end"] + elapsed_time
                })
            
            elapsed_time += node_duration
        gc.collect()

    # ── Outro CTA ────────────────────────────────────────────────────
    if SHOW_OUTRO_CARD:
        if progress_callback:
            progress_callback(total, total, "🎬 Rendering outro card…")
        outro_clip = make_outro_clip(next_topic, OUTRO_CARD_SECS)
        outro_path = render_card_to_tempfile(outro_clip, OUTRO_CARD_SECS, tmp_dir)
        temp_files.append(outro_path)
        elapsed_time += OUTRO_CARD_SECS

    if progress_callback:
        progress_callback(total, total, "🔗 Stitching everything together…")

    if not temp_files:
        raise ValueError("No renderable segments found.")

    # ── FFMPEG Stream-Copy Concatenation (Zero Drift) ──────────────────
    clean_master_path = os.path.join(tmp_dir, "clean_master.mp4")
    print(f"[video_engine] FFMPEG Concat Demuxer: stitching {len(temp_files)} segments…")
    
    # Create the concat instruction file
    concat_list_path = os.path.join(tmp_dir, "concat_list.txt")
    with open(concat_list_path, "w") as f:
        for tmp in temp_files:
            f.write(f"file '{os.path.abspath(tmp)}'\n")

    # Run FFMPEG concat demuxer to produce clean master video (no subtitles yet)
    import subprocess
    ffmpeg_bin = get_ffmpeg_exe()
    cmd = [
        ffmpeg_bin, "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", concat_list_path,
        "-c", "copy",
        clean_master_path
    ]
    
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        print(f"[video_engine] Clean master video built successfully: {clean_master_path}")
    except subprocess.CalledProcessError as e:
        print(f"[video_engine] FFMPEG Concat failed: {e.stderr.decode()}")
        # Fallback using MoviePy compose if somehow ffmpeg copy failed
        master = concatenate_videoclips([VideoFileClip(f) for f in temp_files], method="compose")
        master.write_videofile(clean_master_path, fps=24, codec="libx264", audio_codec="aac", audio_fps=AUDIO_SR, logger=None)
        master.close()

    # ── Generate and Burn Subtitles (.ass) ──────────────────────────
    output_path = os.path.join(topic_dir, "master_video.mp4")
    if master_word_timestamps:
        if progress_callback:
            progress_callback(total, total, "✍️ Burning in .ass subtitles…")
            
        ass_path = os.path.join(tmp_dir, "master_subs.ass")
        from ass_generator import generate_ass
        generate_ass(master_word_timestamps, ass_path, video_width=VIDEO_SIZE[0], video_height=VIDEO_SIZE[1])
        
        # Burn subtitle file using libass (FFmpeg video filter)
        # -c:a copy allows stream copying the audio directly (super fast, no drift!)
        burn_cmd = [
            ffmpeg_bin, "-y",
            "-i", clean_master_path,
            "-vf", f"ass={ass_path}",
            "-c:v", "libx264",
            "-crf", "18",
            "-preset", "veryfast",
            "-c:a", "copy",
            output_path
        ]
        try:
            print(f"[video_engine] Running FFMPEG libass subtitle burn-in pass…")
            subprocess.run(burn_cmd, check=True, capture_output=True)
            print(f"[video_engine] Subtitles successfully burned into {output_path}")
        except subprocess.CalledProcessError as e:
            print(f"[video_engine] FFMPEG Subtitle burn failed: {e.stderr.decode()}")
            # If libass fails, copy clean video as final output
            import shutil
            shutil.copy(clean_master_path, output_path)
    else:
        # No timestamps to generate subtitles, just copy the clean master
        import shutil
        shutil.copy(clean_master_path, output_path)

    # Cleanup
    gc.collect()
    import shutil
    shutil.rmtree(tmp_dir, ignore_errors=True)

    return output_path
