"""Synthetic ID cards for the OCR eval. Fictional issuer, fake people, no real PII.

Two sets, each with labels generated alongside the images:
- golden   (30): layout A (labels above values, sans-serif). 10 clean scans, 10 phone-photo
                 style (background, perspective, uneven light, blur, JPEG), 10 hard (strong
                 skew, glare over a field, two-line addresses, unusual names, a cut-off field).
- held_out (10): layout B (inline labels, serif font, different colours, "14 MAR 1990" dates).
                 Never used for tuning; reported separately.

Deterministic: the same seed gives the same cards.
Run (inside the dev image, which has the fonts):  python tools/golden_set/generate.py
"""

import json
import random
import sys
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path

import numpy as np
from faker import Faker
from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = Path(__file__).resolve().parents[2] / "evals" / "datasets" / "ocr"
SEED = 20261016
W, H = 1012, 638  # ID-1 card proportions at ~300 dpi

FONT_DIRS = [Path("/usr/share/fonts/truetype"), Path("C:/Windows/Fonts")]
FONTS = {
    "sans": ["dejavu/DejaVuSans.ttf", "arial.ttf"],
    "sans_bold": ["dejavu/DejaVuSans-Bold.ttf", "arialbd.ttf"],
    "serif": ["liberation/LiberationSerif-Regular.ttf", "times.ttf"],
    "serif_bold": ["liberation/LiberationSerif-Bold.ttf", "timesbd.ttf"],
}

UNUSUAL_NAMES = [
    ("Mary-Ann", "O'Neil"), ("José", "Álvarez-Ruiz"), ("Zoë", "Van der Berg"),
    ("Siobhan", "McAllister"), ("Nguyen", "Thi Lan"), ("Jean-Luc", "D'Souza"),
]
STREET_SUFFIX = ["St", "Ave", "Rd", "Ln", "Dr", "Way", "Ct", "Blvd"]


def font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    for directory in FONT_DIRS:
        for name in FONTS[kind]:
            path = directory / name
            if path.exists():
                return ImageFont.truetype(str(path), size)
    sys.exit(f"Font for {kind} not found; run inside the dev image (fonts-dejavu, fonts-liberation)")


@dataclass
class Person:
    first: str
    middle: str
    last: str
    dob: date
    line1: str
    line2: str

    @property
    def name(self) -> str:
        return " ".join(p for p in (self.first, self.middle, self.last) if p)

    @property
    def address(self) -> str:
        return f"{self.line1}, {self.line2}"


def person(fake: Faker, rng: random.Random, unusual: bool = False, apartment: bool = False) -> Person:
    if unusual:
        first, last = rng.choice(UNUSUAL_NAMES)
        middle = ""
    else:
        first, last = fake.first_name(), fake.last_name()
        middle = rng.choice(["", "", f"{fake.random_uppercase_letter()}"])
    dob = date(1950, 1, 1) + timedelta(days=rng.randint(0, 365 * 55))
    street = fake.last_name() if rng.random() < 0.5 else fake.street_name().split()[0]
    line1 = f"{rng.randint(1, 9899)} {street} {rng.choice(STREET_SUFFIX)}"
    if apartment:
        line1 += f" Apt {rng.randint(1, 40)}{rng.choice('ABCD')}"
    line2 = f"{fake.city()}, RS {rng.randint(10000, 99999)}"
    return Person(first, middle, last, dob, line1, line2)


# ---- layouts ---------------------------------------------------------------------------


def silhouette(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], tone: str) -> None:
    x0, y0, x1, y1 = box
    draw.rectangle(box, fill=tone)
    cx = (x0 + x1) // 2
    draw.ellipse([cx - 55, y0 + 40, cx + 55, y0 + 160], fill="#9aa3ad")
    draw.pieslice([x0 + 20, y0 + 170, x1 - 20, y1 + 120], 180, 360, fill="#9aa3ad")


def layout_a(p: Person, rng: random.Random, cut_address: bool = False) -> Image.Image:
    card = Image.new("RGB", (W, H), "#f4f6f8")
    d = ImageDraw.Draw(card)
    d.rectangle([0, 0, W, 96], fill="#1f4e79")
    d.text((32, 18), "STATE OF RIVERSIDE", font=font("sans_bold", 40), fill="white")
    d.text((34, 64), "CLIENT IDENTIFICATION CARD", font=font("sans", 22), fill="#d7e3f0")
    silhouette(d, (36, 130, 286, 450), "#c8ced6")
    label, value = font("sans", 22), font("sans_bold", 34)
    x, y = 330, 128
    for title, lines in (
        ("NAME", [p.name.upper()]),
        ("DATE OF BIRTH", [p.dob.strftime("%m/%d/%Y")]),
        ("ADDRESS", [p.line1.upper(), p.line2.upper()]),
    ):
        d.text((x, y), title, font=label, fill="#5b6b7b")
        y += 30
        for line in lines:
            d.text((x, y), line, font=value, fill="#111111")
            y += 44
        y += 14
    d.text((x, y + 6), f"ID NO. {rng.randint(10**7, 10**8 - 1)}", font=label, fill="#5b6b7b")
    d.text((36, 480), f"EXPIRES {rng.randint(1, 12):02d}/{rng.randint(2028, 2034)}",
           font=label, fill="#5b6b7b")
    d.rectangle([0, H - 18, W, H], fill="#1f4e79")
    if cut_address:  # the bottom of the card (address) is outside the photo
        card = card.crop((0, 0, W, 360))
    return card


def layout_b(p: Person, rng: random.Random) -> Image.Image:
    card = Image.new("RGB", (W, H), "#fbf7ee")
    d = ImageDraw.Draw(card)
    d.rectangle([0, 0, W, 80], fill="#6b2d2d")
    d.text((W - 520, 18), "Riverside Member Card", font=font("serif_bold", 40), fill="#fbe9c9")
    silhouette(d, (W - 280, 120, W - 40, 420), "#d9cfbf")
    label, value = font("serif_bold", 28), font("serif", 32)
    y = 130
    rows = [
        ("Name:", p.name),
        ("DOB:", p.dob.strftime("%d %b %Y").upper()),
        ("Address:", p.line1),
        ("", p.line2),
    ]
    for title, text in rows:
        if title:
            d.text((40, y), title, font=label, fill="#6b2d2d")
        d.text((210, y), text, font=value, fill="#1a1a1a")
        y += 58
    d.text((40, y + 30), f"Member {rng.randint(10**5, 10**6 - 1)}", font=label, fill="#6b2d2d")
    return card


# ---- photographic effects --------------------------------------------------------------


def on_background(card: Image.Image, rng: random.Random, margin: int) -> Image.Image:
    bw, bh = card.width + 2 * margin, card.height + 2 * margin
    base = np.full((bh, bw, 3), rng.choice([(120, 92, 66), (90, 96, 104), (160, 150, 135)]),
                   dtype=np.float32)
    base += np.random.default_rng(rng.randint(0, 10**6)).normal(0, 9, base.shape)
    bg = Image.fromarray(np.clip(base, 0, 255).astype("uint8"))
    bg.paste(card, (margin, margin))
    return bg


def perspective(image: Image.Image, rng: random.Random, strength: float) -> Image.Image:
    w, h = image.size
    jitter = [rng.uniform(-strength, strength) * min(w, h) for _ in range(8)]
    src = [(0, 0), (w, 0), (w, h), (0, h)]
    dst = [(x + jitter[2 * i], y + jitter[2 * i + 1]) for i, (x, y) in enumerate(src)]
    coeffs = _perspective_coeffs(dst, src)
    return image.transform((w, h), Image.Transform.PERSPECTIVE, coeffs, Image.Resampling.BICUBIC,
                           fillcolor=(110, 100, 90))


def _perspective_coeffs(pa, pb):
    matrix = []
    for (x, y), (u, v) in zip(pa, pb, strict=True):
        matrix.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        matrix.append([0, 0, 0, x, y, 1, -v * x, -v * y])
    a = np.array(matrix, dtype=float)
    b = np.array(pb, dtype=float).reshape(8)
    return np.linalg.solve(a, b).tolist()


def lighting(image: Image.Image, rng: random.Random) -> Image.Image:
    arr = np.asarray(image).astype(np.float32)
    h, w = arr.shape[:2]
    gx = np.linspace(rng.uniform(0.75, 0.95), rng.uniform(1.0, 1.1), w)
    gy = np.linspace(rng.uniform(0.85, 1.0), rng.uniform(0.95, 1.08), h)
    arr *= np.outer(gy, gx)[:, :, None]
    return Image.fromarray(np.clip(arr, 0, 255).astype("uint8"))


def glare(image: Image.Image, rng: random.Random, center: tuple[int, int]) -> Image.Image:
    arr = np.asarray(image).astype(np.float32)
    h, w = arr.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    rx, ry = rng.uniform(110, 170), rng.uniform(45, 70)
    dist = ((xx - center[0]) / rx) ** 2 + ((yy - center[1]) / ry) ** 2
    arr += (np.exp(-dist) * rng.uniform(120, 170))[:, :, None]
    return Image.fromarray(np.clip(arr, 0, 255).astype("uint8"))


def rotate(image: Image.Image, degrees: float) -> Image.Image:
    return image.rotate(degrees, resample=Image.Resampling.BICUBIC, expand=True,
                        fillcolor=(110, 100, 90))


def jpeg(image: Image.Image, quality: int) -> Image.Image:
    import io

    buf = io.BytesIO()
    image.save(buf, "JPEG", quality=quality)
    return Image.open(io.BytesIO(buf.getvalue())).convert("RGB")


def phone_photo(card: Image.Image, rng: random.Random) -> Image.Image:
    image = on_background(card, rng, margin=rng.randint(70, 140))
    image = perspective(image, rng, 0.035)
    image = lighting(image, rng)
    image = image.filter(ImageFilter.GaussianBlur(rng.uniform(0.4, 1.0)))
    return jpeg(image, rng.randint(55, 75))


# ---- sets ------------------------------------------------------------------------------


@dataclass
class Label:
    file: str
    set: str
    variant: str
    expected: dict


def build() -> list[Label]:
    rng = random.Random(SEED)
    fake = Faker("en_US")
    Faker.seed(SEED)
    labels: list[Label] = []

    def save(img: Image.Image, name: str, set_: str, variant: str, p: Person,
             missing: tuple[str, ...] = ()) -> None:
        (OUT / set_).mkdir(parents=True, exist_ok=True)
        path = OUT / set_ / f"{name}.jpg"
        img.convert("RGB").save(path, "JPEG", quality=90)
        expected = {"name": p.name, "date_of_birth": p.dob.isoformat(), "address": p.address}
        for field in missing:
            expected[field] = None  # the correct answer is "left blank"
        labels.append(Label(f"{set_}/{name}.jpg", set_, variant, expected))

    for i in range(10):
        p = person(fake, rng)
        save(on_background(layout_a(p, rng), rng, margin=24), f"clean_{i:02d}", "golden",
             "clean", p)
    for i in range(10):
        p = person(fake, rng)
        save(phone_photo(layout_a(p, rng), rng), f"photo_{i:02d}", "golden", "photo", p)
    hard_kinds = ["skew", "skew", "skew", "glare", "glare", "two_line", "two_line", "unusual",
                  "unusual", "cut_off"]
    for i, kind in enumerate(hard_kinds):
        p = person(fake, rng, unusual=kind == "unusual", apartment=kind == "two_line")
        card = layout_a(p, rng, cut_address=kind == "cut_off")
        if kind == "skew":
            img = rotate(on_background(card, rng, margin=90), rng.choice([-1, 1]) * rng.uniform(7, 12))
            img = jpeg(lighting(img, rng), 70)
        elif kind == "glare":
            img = glare(on_background(card, rng, margin=60), rng, (rng.randint(500, 760), 290))
        else:
            img = phone_photo(card, rng)
        save(img, f"hard_{kind}_{i:02d}", "golden", f"hard_{kind}", p,
             missing=("address",) if kind == "cut_off" else ())
    for i in range(10):
        p = person(fake, rng, unusual=i in (3, 7), apartment=i in (2, 6))
        card = layout_b(p, rng)
        img = phone_photo(card, rng) if i % 2 else on_background(card, rng, margin=30)
        save(img, f"layout_b_{i:02d}", "held_out", "layout_b", p)
    return labels


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    built = build()
    (OUT / "labels.json").write_text(
        json.dumps([asdict(label) for label in built], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    counts = {s: sum(1 for b in built if b.set == s) for s in ("golden", "held_out")}
    print(f"Wrote {len(built)} synthetic IDs to {OUT}: {counts}")
