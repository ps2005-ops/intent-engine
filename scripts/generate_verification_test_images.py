"""One-time generator for image-verification's synthetic test fixtures.

Real, constructed test images (not real photos, not hallucinated) -- each
built to exercise one specific case the audit's checkpoint asked for: a
clear true positive, a true negative (a required field genuinely missing),
a cropped/cut-off field, an illegible/blurry case, and a second true
positive with different values (to check consistency). Written once to
tests/fixtures/image_verification/; re-run this script to regenerate them
if the checklist or rendering changes.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "image_verification"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

_FONT_PATH = "/System/Library/Fonts/Supplemental/Arial.ttf"


def _font(size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(_FONT_PATH, size)
    except OSError:
        return ImageFont.load_default(size=size)


def _render_receipt(lines, size=(500, 350)) -> Image.Image:
    image = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(image)
    title_font = _font(28)
    body_font = _font(22)
    y = 20
    draw.text((30, y), "RECEIPT", fill="black", font=title_font)
    y += 50
    for line in lines:
        draw.text((30, y), line, fill="black", font=body_font)
        y += 40
    return image


# 1. Complete: every checklist field clearly visible and legible.
complete = _render_receipt([
    "Vendor: Acme Coffee Co",
    "Date: 2026-07-01",
    "Amount: $42.50",
])
complete.save(OUTPUT_DIR / "complete_receipt.png")

# 2. Missing field entirely: no Date line at all (genuinely absent, not cropped).
missing_date = _render_receipt([
    "Vendor: Acme Coffee Co",
    "Amount: $42.50",
])
missing_date.save(OUTPUT_DIR / "missing_date.png")

# 3. Cropped/cut off: render full receipt, then crop the canvas so the
# Amount line is cut off mid-line -- a required field visibly present but
# not fully in frame, as a real photo might be.
full_for_crop = _render_receipt([
    "Vendor: Acme Coffee Co",
    "Date: 2026-07-01",
    "Amount: $42.50",
], size=(500, 350))
# Amount line starts at y=20+50+40+40=150, height 22-ish -- crop just below
# its top edge so only the very top sliver of the text is visible, the rest
# cut off by the frame.
cropped = full_for_crop.crop((0, 0, 500, 158))
cropped.save(OUTPUT_DIR / "cropped_amount.png")

# 4. Illegible: complete receipt, heavily blurred so text can't be read.
blurry = complete.filter(ImageFilter.GaussianBlur(radius=8))
blurry.save(OUTPUT_DIR / "illegible_blurry.png")

# 5. Second complete case, different values -- checks the model isn't just
# pattern-matching the first image's specific text.
complete_2 = _render_receipt([
    "Vendor: Riverside Hardware",
    "Date: 2026-06-15",
    "Amount: $118.90",
])
complete_2.save(OUTPUT_DIR / "complete_receipt_2.png")

print(f"Wrote 5 fixture images to {OUTPUT_DIR}")
for f in sorted(OUTPUT_DIR.iterdir()):
    print(f"  {f.name}")
