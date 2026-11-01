"""Generate the ComputeTorrent Windows icon from vector-like Pillow drawing."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

SIZE = 1024
OUT = Path(__file__).resolve().parent
base = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
draw = ImageDraw.Draw(base)
draw.rounded_rectangle((34, 34, 990, 990), radius=235, fill="#111c3e", outline="#365584", width=12)

glow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
g = ImageDraw.Draw(glow)
g.arc((183, 183, 841, 841), 51, 309, fill=(30, 213, 251, 195), width=115)
base.alpha_composite(glow.filter(ImageFilter.GaussianBlur(38)))

draw = ImageDraw.Draw(base)
draw.arc((183, 183, 841, 841), 51, 309, fill="#29d8f7", width=112)
draw.arc((261, 261, 763, 763), 61, 299, fill="#3661d8", width=22)

# Three bright endpoints suggest connected volunteer machines.
for x, y, radius, color in [
    (712, 273, 49, "#a6f5ff"),
    (712, 751, 49, "#a6f5ff"),
    (281, 512, 34, "#f3fbff"),
]:
    draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=color)

# The bolt stays recognizable at Windows taskbar sizes.
draw.polygon([(528, 289), (392, 526), (494, 526), (444, 735),
              (647, 468), (541, 468), (603, 289)], fill="#f7fbff")

png = OUT / "computetorrent-icon.png"
ico = OUT / "computetorrent-icon.ico"
base.save(png)
base.save(ico, format="ICO", sizes=[(16, 16), (24, 24), (32, 32),
                                     (48, 48), (64, 64), (128, 128), (256, 256)])
print(png)
print(ico)
