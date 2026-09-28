"""Process the two AutoStack logo PNGs into web-ready assets.

Inputs (user-provided reference images):
  - light logo (SRC_LIGHT): metallic "A" + dark "AutoStack" wordmark on black
    -> used in LIGHT theme (metallic mark + dark text)
  - dark logo (SRC_DARK): metallic "A" + white/glowing "AutoStack" on black
    -> used in DARK theme (metallic mark + white text)

Outputs:
  - frontend/src/assets/autostack-{mark,lockup}-{light,dark}.png (transparent)
  - frontend/public/favicon-{light,dark}.png (mark-only favicons)

Method (v7): the light source is floor-keyed crisp (opaque content, luminance
stretch). The DARK variant is derived from the SAME crisp light source and
recolors it for dark surfaces: metallic "A" slightly brightened, wordmark
pushed to white. The puffy dark-source image cannot be de-glowed (its halo is
as bright as the letters — no key can separate them), so it is no longer used
as a source. Both assets are crisp by construction; the UI applies no filters.
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


def key_crisp(path, floor=12.0, ramp=40.0, out_lo=55.0, span=150.0):
    """LIGHT source: crisp keying — background keyed off, content fully opaque,
    luminance stretched into a readable metallic range.

    v5 fix: the source's "AutoStack" wordmark is deliberately DIM dark-metallic
    text (luminance ≈13–40 on a pure-black field). The old floor of 26 keyed
    most of those strokes away, leaving a sparse, illegible caption. floor=12
    keeps every wordmark stroke fully opaque while the pure-black background
    (0–11) still keys clean — verified: the inter-band gap stays empty."""
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


def key_dark_from_light(path, floor=12.0, ramp=40.0, out_lo=55.0, span=150.0,
                        mark_brighten=1.14, mark_lift=8.0):
    """DARK variant derived from the CRISP light source (v7).

    The puffy dark-source wordmark cannot be de-glowed — its halo is as bright
    as the letters, so luminance keying either keeps the bloom or eats the
    glyphs. Instead we reuse the light source's clean geometry (same metallic
    "A", same wordmark shapes, fully opaque) and recolor for dark surfaces:
      - mark region (above the same split line split_mark uses): metal tone
        brightened a touch so it reads on near-black backgrounds;
      - wordmark region (below the split): every stroke mapped to white
        (235–255) with slight per-pixel variation retained so it doesn't band.
    Alpha is untouched from the crisp key — no halo can exist by construction.
    """
    im = key_crisp(path, floor=floor, ramp=ramp, out_lo=out_lo, span=span)
    arr = np.array(im)
    rgb = arr[..., :3].astype(np.float64)
    alpha = arr[..., 3]
    h = arr.shape[0]
    prof = alpha.max(axis=1)
    lo, hi = int(h * 0.45), int(h * 0.75)
    mark_bottom = lo + int(np.argmin(prof[lo:hi])) if hi > lo else int(h * 0.6)
    lum = rgb.max(axis=-1)
    word = np.zeros(lum.shape, dtype=bool)
    word[mark_bottom + 2:, :] = True
    visible = alpha > 0
    wm = word & visible
    metal = (~word) & visible
    out = rgb.copy()
    wl = lum[wm]
    if wl.size:
        span_wl = max(1.0, float(wl.max() - wl.min()))
        target = 235.0 + (wl - wl.min()) / span_wl * 20.0  # 235–255 white
        for c in range(3):
            out[..., c][wm] = target
    out[metal] = np.clip(rgb[metal] * mark_brighten + mark_lift, 0, 255)
    return Image.fromarray(np.dstack([out.clip(0, 255).astype(np.uint8), alpha]), "RGBA")


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


light = key_crisp(SRC_LIGHT, floor=12.0, ramp=40.0, out_lo=55.0, span=150.0)
dark = key_dark_from_light(SRC_LIGHT)  # v7: crisp geometry, recolored for dark

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
