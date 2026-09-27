"""Process the two AutoStack logo PNGs into web-ready assets.

Inputs (user-provided):
  - light logo: metallic "A" + dark wordmark on black (for LIGHT theme surfaces)
  - dark logo:  metallic "A" + white wordmark on near-black (for DARK theme surfaces)

Outputs (frontend/src/assets/, committed to the repo):
  - autostack-mark-light.png / autostack-mark-dark.png   (mark only, transparent)
  - autostack-lockup-light.png / autostack-lockup-dark.png (mark + wordmark, transparent)

Method (v3): both sources are keyed with the same crisp pipeline — floor-key
the background, force content pixels fully opaque, and stretch their luminance
into a readable metallic range. The dark source is a baked-in glow render, so
its floor is higher (36) to cut the halo; the UI applies no filters at all
(crisp by asset). Earlier attempts unmixing the dark logo against black left
it soft and fuzzy (alpha mean ~185/255) — that approach is gone.
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


def key_crisp(path, floor=26.0, ramp=60.0, out_lo=55.0, span=150.0):
    """Floor-key the background, make every content pixel fully opaque, and
    stretch its luminance into a readable metallic range [out_lo..out_lo+span].
    Floor/ramp tune how aggressively the glow halo around the glyph is cut."""
    im = Image.open(path).convert("RGB")
    rgb = np.array(im).astype(np.float64)
    lum = rgb.max(axis=-1)
    alpha_f = np.clip((lum - floor) / (ramp - floor), 0.0, 1.0)
    content = lum >= floor
    alpha_f[content] = 1.0
    stretched = (rgb - floor) / max(255.0 - floor, 1.0)
    stretched = np.clip(stretched, 0.0, 1.0) * span + out_lo
    out_rgb = np.where(content[..., None], stretched, rgb)
    out = np.dstack([out_rgb.clip(0, 255).astype(np.uint8),
                     (alpha_f * 255).astype(np.uint8)])
    return autocrop(Image.fromarray(out, "RGBA"))


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


light = key_crisp(SRC_LIGHT, floor=26.0, ramp=60.0, out_lo=55.0, span=150.0)
dark = key_crisp(SRC_DARK, floor=36.0, ramp=110.0, out_lo=70.0, span=170.0)

for name, im in (("light", light), ("dark", dark)):
    lock = im.copy()
    lock.thumbnail((420, 260), Image.LANCZOS)
    lock.save(f"{OUT}/autostack-lockup-{name}.png", optimize=True)
    mark = split_mark(im)
    mark.thumbnail((160, 160), Image.LANCZOS)
    mark.save(f"{OUT}/autostack-mark-{name}.png", optimize=True)
    print(name, "lockup", lock.size, "mark", mark.size)
