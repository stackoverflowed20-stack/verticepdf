"""Gera assets/verticepdf.ico e verticepdf.png — logotipo "V" facetado do Vértice PDF."""
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).parent / "assets"
OUT.mkdir(exist_ok=True)

# Mesma geometria usada por icons.brand_pixmap() (coordenadas relativas 0..1)
V_SHAPE = [(0.23, 0.27), (0.40, 0.27), (0.50, 0.58), (0.60, 0.27), (0.77, 0.27), (0.585, 0.76), (0.415, 0.76)]
FACET = [(0.50, 0.58), (0.585, 0.76), (0.415, 0.76)]
C1, C2 = (47, 111, 224), (23, 74, 166)      # degradê #2f6fe0 -> #174aa6
FACET_COLOR = (156, 192, 255)


def render(S: int = 512) -> Image.Image:
    SS = S * 2  # supersampling para bordas suaves
    grad = Image.new("RGBA", (SS, SS))
    px = grad.load()
    for y in range(SS):
        for x in range(SS):
            t = (x + y) / (2 * SS)
            px[x, y] = tuple(int(C1[i] + (C2[i] - C1[i]) * t) for i in range(3)) + (255,)
    mask = Image.new("L", (SS, SS), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, SS - 1, SS - 1), radius=int(SS * 0.22), fill=255)
    base = Image.new("RGBA", (SS, SS), (0, 0, 0, 0))
    base.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(base)
    d.polygon([(x * SS, y * SS) for x, y in V_SHAPE], fill=(255, 255, 255, 255))
    d.polygon([(x * SS, y * SS) for x, y in FACET], fill=FACET_COLOR + (255,))
    return base.resize((S, S), Image.LANCZOS)


img = render()
img.save(OUT / "verticepdf.png")
img.save(OUT / "verticepdf.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("Ícones gerados em", OUT)
