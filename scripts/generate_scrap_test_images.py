"""One-time generator for scrap-estimate's synthetic test fixtures.

Honest caveat, stated here and repeated in the checkpoint that uses these:
these are crude, Pillow-rendered color/shape approximations, NOT realistic
scrap-metal photos. The receipt-verification fixtures worked as a real test
because rendering actual TEXT and checking legibility is a genuine,
representative instance of what that domain judges. Grading "does this look
rusty" from a flat-colored, textureless rectangle is not a representative
instance of what real scrap-metal visual grading requires (surface texture,
reflectance, real rust patterns, depth, actual contamination materials) --
this only tests that the plumbing (a real vision call, real schema
validation, real entity-memory read/write) works end-to-end, not that the
domain's real-world judgment quality is validated.
"""

from pathlib import Path

from PIL import Image, ImageDraw

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "scrap_estimate"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 1. "Clean" lot -- silver/gray tones, minimal blotching, no contamination shapes.
clean = Image.new("RGB", (500, 400), (190, 192, 196))
draw = ImageDraw.Draw(clean)
for i in range(6):
    x, y = 40 + i * 70, 60 + (i % 2) * 180
    draw.ellipse([x, y, x + 90, y + 140], fill=(170, 173, 178), outline=(140, 142, 146))
clean.save(OUTPUT_DIR / "clean_metal.png")

# 2. "Heavily rusted" lot -- reddish-brown tones dominate.
rusty = Image.new("RGB", (500, 400), (120, 70, 40))
draw = ImageDraw.Draw(rusty)
for i in range(6):
    x, y = 40 + i * 70, 60 + (i % 2) * 180
    draw.ellipse([x, y, x + 90, y + 140], fill=(101, 55, 30), outline=(80, 42, 20))
rusty.save(OUTPUT_DIR / "rusty_metal.png")

# 3. Metal with an obvious non-metal contamination shape (bright blue rectangle,
# standing in for something like plastic housing).
contaminated = Image.new("RGB", (500, 400), (190, 192, 196))
draw = ImageDraw.Draw(contaminated)
for i in range(6):
    x, y = 40 + i * 70, 60 + (i % 2) * 180
    draw.ellipse([x, y, x + 90, y + 140], fill=(170, 173, 178), outline=(140, 142, 146))
draw.rectangle([180, 150, 280, 220], fill=(40, 90, 200))  # bright blue "plastic" block
contaminated.save(OUTPUT_DIR / "contaminated_metal.png")

print(f"Wrote 3 fixture images to {OUTPUT_DIR}")
for f in sorted(OUTPUT_DIR.iterdir()):
    print(f"  {f.name}")
print("\nCAVEAT: these are crude color/shape approximations, not realistic scrap-metal "
      "photos -- see this script's module docstring.")
