"""Process the two AutoStack logo PNGs into web-ready assets.

Inputs (user-provided, 1024x1024-ish, both with dark backgrounds):
  - light logo: dark metallic "A" + dark-gray wordmark (for LIGHT theme surfaces)
  - dark logo:  glowing white "A" + white wordmark (for DARK theme surfaces)

Outputs (frontend/src/assets/, committed to the repo):
  - autostack-mark-light.png / autostack-mark-dark.png   (mark only, transparent)
  - autostack-lockup-light.png / autostack-lockup-dark.png (mark + wordmark, transparent)

Method: background = black -> alpha via luminance-derived matte for the dark
logo (glow must stay semi-transparent, so we do proper un-premultiply against
black), and alpha-keying for the metallic logo, then autocrop + downscale.
"""
from PIL import Image
import numpy as np

SRC_LIGHT = r"C:\Users\prady\Downloads\ChatGPT Image Sep 26, 2026, 12_20_02 AM.png"
SRC_DARK = r"C:\Users\prady\Downloads\ChatGPT Image Sep 26, 2026, 12_19_57 AM.png"
OUT = "frontend/src/assets"

import os
os.makedirs(OUT, exist_ok=True)


def autocrop(im, threshold=8):
    a = np.array(im)
    alpha = a[..., 3]
    ys, xs = np.where(alpha > threshold)
    if len(xs) == 0:
        return im
    box = (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)
    return im.crop(box)


def unmix_against_black(rgb, strength):
    """Given pixels composited over black with additive glow, recover the
    emission color and alpha: alpha ≈ max_channel, color = rgb / max_channel.
    `strength` scales how aggressively dim pixels become opaque."""
    mx = rgb.max(axis=-1)
    alpha = np.clip(mx * strength, 0, 255).astype(np.uint8)
    safe = np.maximum(mx, 1)[..., None]
    color = np.clip(rgb / safe * 255.0, 0, 255).astype(np.uint8)
    return color, alpha


def process_light():
    """Metallic 'A' on near-black; wordmark is dark gray (must survive keying)."""
    im = Image.open(SRC_LIGHT).convert("RGB")
    rgb = np.array(im).astype(np.float64)
    # near-black background removal: anything below the floor becomes transparent
    floor = 26.0
    lum = rgb.max(axis=-1)
    alpha = np.clip((lum - floor) / (60.0 - floor) * 255.0, 0, 255).astype(np.uint8)
    # the wordmark (~ rgb 30-35) would be cut by that floor, so lift alpha where
    # pixels are "grayish and contiguous with the mark" — simplest robust move:
    # treat mid-gray (25..80) as partially opaque
    mid = (lum >= 24) & (lum < 80)
    alpha[mid] = np.maximum(alpha[mid], 140)
    out = np.dstack([rgb.astype(np.uint8), alpha])
    img = Image.fromarray(out, "RGBA")
    return autocrop(img)


def process_dark():
    """White glowing lockup on black -> emission matte (glow keeps soft alpha)."""
    im = Image.open(SRC_DARK).convert("RGB")
    rgb = np.array(im).astype(np.float64)
    color, alpha = unmix_against_black(rgb, strength=1.35)
    out = np.dstack([color, alpha])
    img = Image.fromarray(out, "RGBA")
    return autocrop(img, threshold=6)


def split_mark(im):
    """Mark = top ~72% of lockup height (the A glyph sits above the wordmark)."""
    w, h = im.size
    a = np.array(im)[..., 3]
    rows = np.where(a.max(axis=1) > 10)[0]
    # find the biggest vertical gap between content rows -> separates mark/word
    gaps = []
    prev = rows[0]
    start = rows[0]
    for r in rows[1:]:
        if r - prev > 12:
            gaps.append((prev, r))
        prev = r
    end = rows[-1]
    if gaps:
        g = max(gaps, key=lambda p: p[1] - p[0])
        mark_bottom = g[0]
    else:
        mark_bottom = int(h * 0.72)
    mark = im.crop((0, 0, w, mark_bottom + 2))
    return autocrop(mark)


light = process_light()
dark = process_dark()

for name, im in (("light", light), ("dark", dark)):
    lock = im.copy()
    lock.thumbnail((420, 260), Image.LANCZOS)
    lock.save(f"{OUT}/autostack-lockup-{name}.png", optimize=True)
    mark = split_mark(im)
    mark.thumbnail((160, 160), Image.LANCZOS)
    mark.save(f"{OUT}/autostack-mark-{name}.png", optimize=True)
    print(name, "lockup", lock.size, "mark", mark.size)
