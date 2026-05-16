import os
import textwrap
from PIL import Image, ImageDraw, ImageFont, ImageFilter

def generate_thumbnail(topic_dir: str, title: str, hook_text: str):
    """
    Generates a 1280x720 thumbnail with cinematic text overlay.
    Looks for a background image in the topic_dir.
    Saves to topic_dir/thumbnail.jpg
    """
    out_path = os.path.join(topic_dir, "thumbnail.jpg")
    
    # 1. Find a suitable background image
    bg_img_path = None
    # Try finding bg_hook.jpg or any bg_*.jpg
    for fname in os.listdir(topic_dir):
        if fname.startswith("bg_") and fname.endswith(".jpg"):
            bg_img_path = os.path.join(topic_dir, fname)
            if "hook" in fname:
                break # best match

    # 2. Create base image
    W, H = 1280, 720
    if bg_img_path and os.path.exists(bg_img_path):
        img = Image.open(bg_img_path).convert("RGB")
        # Resize to fill
        img_ratio = img.width / img.height
        target_ratio = W / H
        if img_ratio > target_ratio:
            # Image is wider, crop width
            new_w = int(img.height * target_ratio)
            x_offset = (img.width - new_w) // 2
            img = img.crop((x_offset, 0, x_offset + new_w, img.height))
        else:
            # Image is taller, crop height
            new_h = int(img.width / target_ratio)
            y_offset = (img.height - new_h) // 2
            img = img.crop((0, y_offset, img.width, y_offset + new_h))
        
        try:
            resample = Image.Resampling.LANCZOS
        except AttributeError:
            resample = Image.ANTIALIAS
        img = img.resize((W, H), resample)

        # Apply a subtle blur and heavy vignette/darkening to make text pop
        img = img.filter(ImageFilter.GaussianBlur(radius=2))
        dim = Image.new('RGB', (W, H), (0, 0, 0))
        img = Image.blend(img, dim, 0.6) # 60% black
    else:
        # Fallback to dark grey gradient
        img = Image.new('RGB', (W, H), color=(20, 20, 20))

    draw = ImageDraw.Draw(img)

    # 3. Load Fonts
    # We will try to find a bold sans-serif font. Linux fallback is usually DejaVuSans-Bold
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    ]
    font_title = None
    font_hook = None
    
    for path in font_paths:
        if os.path.exists(path):
            try:
                font_title = ImageFont.truetype(path, 80)
                font_hook = ImageFont.truetype(path, 40)
                break
            except Exception:
                pass
                
    if not font_title:
        font_title = ImageFont.load_default()
        font_hook = ImageFont.load_default()

    # 4. Draw Title
    # Break title into max 25 chars per line
    wrapped_title = textwrap.wrap(title.upper(), width=25)
    
    y_text = 150
    for line in wrapped_title:
        # Get bounding box
        left, top, right, bottom = draw.textbbox((0, 0), line, font=font_title)
        line_w = right - left
        x_text = (W - line_w) / 2
        # Drop shadow
        draw.text((x_text+4, y_text+4), line, font=font_title, fill=(0, 0, 0, 180))
        # Main text
        draw.text((x_text, y_text), line, font=font_title, fill=(255, 255, 255))
        y_text += (bottom - top) + 15

    # 5. Draw Hook Snippet (First 15-20 words)
    words = hook_text.split()
    snippet = " ".join(words[:20]) + ("..." if len(words) > 20 else "")
    wrapped_hook = textwrap.wrap(snippet, width=50)
    
    y_text += 80
    for line in wrapped_hook:
        left, top, right, bottom = draw.textbbox((0, 0), line, font=font_hook)
        line_w = right - left
        x_text = (W - line_w) / 2
        # Drop shadow
        draw.text((x_text+2, y_text+2), line, font=font_hook, fill=(0, 0, 0, 200))
        # Main text (yellow-ish for contrast)
        draw.text((x_text, y_text), line, font=font_hook, fill=(255, 215, 0))
        y_text += (bottom - top) + 10

    # 6. Draw "Still Point" branding at bottom
    left, top, right, bottom = draw.textbbox((0, 0), "STILL POINT", font=font_hook)
    bw = right - left
    draw.text(((W - bw)/2, H - 80), "STILL POINT", font=font_hook, fill=(255, 255, 255, 100))

    img.save(out_path, format="JPEG", quality=90)
    return out_path
