"""Process the two AutoStack logo PNGs into web-ready assets.

Inputs (user-provided reference images):
  - light logo (SRC_LIGHT): metallic "A" + dark "AutoStack" wordmark on black
    -> used in LIGHT theme (crisp treatment, exactly as supplied)
  - dark logo (SRC_DARK): metallic "A" + white/glowing "AutoStack" on black
    -> used in DARK theme (the glow IS the design; it is preserved)

Outputs:
  - frontend/src/assets/autostack-{mark,lockup}-{light,dark}.png (transparent)
  - frontend/public/favicon-{light,dark}.png (mark-only favicons)

Method (v4): the light source is floor-keyed crisp (opaque content, luminance
stretch) exactly as in v3. The dark source keeps its baked-in glow through an
emission matte (unmix against black): alpha = max-channel, color = rgb/alpha —
the halo survives as semi-transparent pixels instead of being clipped away.
The UI applies no filters to either variant; each asset already looks like its
reference image on its own background.
"""
from PIL import Image
import numpy as np
import os

SRC_LIGHT = r"C:\Users\prady\Downloads\ChatGPT Image Sep 26, 2026, 12_20_02 AM.png"
SRC_DARK = r"C:\Users\prady\Downloads\ChatGPT Image Sep 26, 2026, 12_19_57 AM.png"
OUT = "frontend/src/assets"
PUBLIC = "frontend/public"

os.makedirs(OUT, exist_ok=True)
os.makedirs(PUBLIC, exist_ok=True)


def autocrop(im, threshold=8):
    a = np.array(im)
    alpha = a[..., 3]
    ys, xs = np.where(alpha > threshold)
    if len(xs) == 0:
        return im
    box = (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)
    return im.crop(box)


def key_crisp(path, floor=26.0, ramp=60.0, out_lo=55.0, span=150.0):
    """LIGHT source: crisp keying — background keyed off, content fully opaque,
    luminance stretched into a readable metallic range."""
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


def key_glow(path, floor=6.0):
    """DARK source: emission matte — the baked-in glow is the design. alpha =
    max channel (dim pixels semi-transparent), color = emission recovered by
    un-premultiplying against black. A tiny floor removes sensor noise."""
    im = Image.open(path).convert("RGB")
    rgb = np.array(im).astype(np.float64)
    alpha = np.clip(rgb.max(axis=-1) - floor, 0.0, 255.0)
    safe = np.maximum(rgb.max(axis=-1), 1.0)[..., None]
    color = np.clip(rgb / safe * 255.0, 0, 255).astype(np.uint8)
    out = np.dstack([color, alpha.astype(np.uint8)])
    return autocrop(Image.fromarray(out, "RGBA"), threshold=4)


def split_mark(im):
    """Mark = the part above the lowest-alpha row band between 45% and 75% of
    the lockup height (the A glyph vs the wordmark). The crisp light source has
    a true zero gap there; the dark source's glow only dips, so we split at the
    local minimum instead of requiring an empty gap."""
    w, h = im.size
    a = np.array(im)[..., 3]
    prof = a.max(axis=1)
    lo, hi = int(h * 0.45), int(h * 0.75)
    if hi > lo:
        mark_bottom = lo + int(np.argmin(prof[lo:hi]))
    else:
        mark_bottom = int(h * 0.6)
    mark = im.crop((0, 0, w, mark_bottom + 2))
    return autocrop(mark)


light = key_crisp(SRC_LIGHT, floor=26.0, ramp=60.0, out_lo=55.0, span=150.0)
dark = key_glow(SRC_DARK, floor=6.0)

for name, im in (("light", light), ("dark", dark)):
    lock = im.copy()
    lock.thumbnail((420, 260), Image.LANCZOS)
    lock.save(f"{OUT}/autostack-lockup-{name}.png", optimize=True)
    mark = split_mark(im)
    mark.save(f"{OUT}/autostack-mark-{name}.png", optimize=True)
    fav = mark.copy()
    fav.thumbnail((64, 64), Image.LANCZOS)
    canvas = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    canvas.paste(fav, ((64 - fav.width) // 2, (64 - fav.height) // 2), fav)
    canvas.save(f"{PUBLIC}/favicon-{name}.png", optimize=True)
    print(name, "lockup", lock.size, "mark", mark.size)
