"""Nocne wersje przelacznikow (Icons/night/): te same obrazki przyciemnione, bez jasnej bialej galki.
Uruchomic ponownie po zmianie ikon:  poetry run python Icons/make_night_icons.py"""
from pathlib import Path
from PIL import Image

HERE = Path(__file__).parent
DIM = 0.55      # mnoznik jasnosci (alfa bez zmian)
NAMES = ["SwitchOn", "SwitchOff", "SwitchOnGrey", "SwitchOffGrey", "ToggleOnOrange", "ToggleOffGreen",
         "ToggleOnBlue", "ToggleOffBlue", "ToggleOffOrange", "ToggleOnYellow"]

for name in NAMES:
    src = HERE / f"{name}.png"
    if not src.exists():
        continue
    im = Image.open(src).convert("RGBA")
    r, g, b, a = im.split()
    r, g, b = (ch.point(lambda v: int(v * DIM)) for ch in (r, g, b))
    Image.merge("RGBA", (r, g, b, a)).save(HERE / "night" / f"{name}.png")
    print("night", name)
