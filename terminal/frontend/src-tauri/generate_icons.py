"""Génère les icônes de l'application.

Un carré sombre à coins arrondis portant une barre ambre et une barre bleue —
la même palette que le terminal. Régénérable, pour ne pas avoir à versionner
un binaire dont personne ne sait d'où il vient.

    python generate_icons.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

ICONS = Path(__file__).parent / "icons"

BG = (17, 21, 30, 255)
AMBER = (255, 180, 84, 255)
BLUE = (90, 169, 255, 255)


def draw(size: int) -> Image.Image:
    # On dessine quatre fois trop grand puis on réduit : c'est ce qui donne des
    # bords nets sans avoir à gérer l'anticrénelage à la main.
    scale = 4
    side = size * scale
    image = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    pen = ImageDraw.Draw(image)

    radius = int(side * 0.22)
    pen.rounded_rectangle([0, 0, side - 1, side - 1], radius=radius, fill=BG)

    margin = side * 0.24
    width = side * 0.13
    gap = side * 0.075
    top = side * 0.26
    bottom = side * 0.74

    # Barre ambre pleine hauteur, barre bleue plus courte : une silhouette
    # lisible même à 16 pixels.
    pen.rounded_rectangle(
        [margin, top, margin + width, bottom],
        radius=width / 2,
        fill=AMBER,
    )
    pen.rounded_rectangle(
        [margin + width + gap, top + (bottom - top) * 0.28, margin + 2 * width + gap, bottom],
        radius=width / 2,
        fill=BLUE,
    )
    pen.rounded_rectangle(
        [
            margin + 2 * (width + gap),
            top + (bottom - top) * 0.55,
            margin + 3 * width + 2 * gap,
            bottom,
        ],
        radius=width / 2,
        fill=(154, 165, 186, 255),
    )

    return image.resize((size, size), Image.LANCZOS)


def main() -> None:
    ICONS.mkdir(parents=True, exist_ok=True)

    for size, name in [
        (32, "32x32.png"),
        (128, "128x128.png"),
        (256, "128x128@2x.png"),
        (512, "icon.png"),
    ]:
        draw(size).save(ICONS / name)
        print(f"écrit {name}")

    # Le .ico embarque plusieurs tailles : Windows choisit la bonne selon le
    # contexte (barre des tâches, explorateur, alt-tab).
    draw(256).save(
        ICONS / "icon.ico",
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print("écrit icon.ico")


if __name__ == "__main__":
    main()
