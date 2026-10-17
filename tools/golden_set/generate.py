"""Synthetic ID cards for the OCR eval. Fictional issuer, fake people, no real PII.

Two sets, each with labels generated alongside the images:
- golden   (30): layout A (labels above values, sans-serif). 10 clean scans, 10 phone-photo
                 style (background, perspective, uneven light, blur, JPEG), 10 hard (strong
                 skew, glare over a field, two-line addresses, unusual names, a cut-off field).
- held_out (10): layout B (inline labels, serif font, different colours, "14 MAR 1990" dates).
                 Never used for tuning; reported separately.
- stress   (20): realistic bad captures, 2 of each (layout A and B): motion blur, low light,
                 card far away, laminate glare, the phone's shadow, security print under the
                 text, a thumb over the address, a bent card, a photocopy, and a worst case
                 (dim + shaky + shadow + heavy JPEG). Never used for tuning; reported
                 separately, with wrong pre-fills counted apart from blanks.

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


# ---- stress captures: what real phone photos and scans of an ID look like ---------------


def motion_blur(image: Image.Image, rng: random.Random) -> Image.Image:
    """Hand shake: a straight streak of 9-17 px at a random angle."""
    import cv2

    length, angle = rng.randint(9, 17), rng.uniform(0, 180)
    kernel = np.zeros((length, length), np.float32)
    kernel[length // 2, :] = 1
    rot = cv2.getRotationMatrix2D((length / 2 - 0.5, length / 2 - 0.5), angle, 1)
    kernel = cv2.warpAffine(kernel, rot, (length, length))
    kernel /= kernel.sum()
    return Image.fromarray(cv2.filter2D(np.asarray(image), -1, kernel))


def low_light(image: Image.Image, rng: random.Random) -> Image.Image:
    """Dim room: underexposed, then the camera's gain adds grainy colour noise."""
    arr = np.asarray(image).astype(np.float32) * rng.uniform(0.28, 0.4)
    noise = np.random.default_rng(rng.randint(0, 10**6))
    arr += noise.normal(0, rng.uniform(7, 11), arr.shape)  # sensor noise, per channel
    arr = (arr - arr.min()) / (arr.max() - arr.min()) * rng.uniform(150, 190)  # auto-gain
    return Image.fromarray(np.clip(arr, 0, 255).astype("uint8"))


def far_away(image: Image.Image, rng: random.Random) -> Image.Image:
    """Card small in the frame, then the browser's 2000 px resize shrinks it further."""
    image = on_background(image, rng, margin=rng.randint(420, 520))
    scale = rng.uniform(0.42, 0.5)
    return image.resize((int(image.width * scale), int(image.height * scale)),
                        Image.Resampling.BILINEAR)


def laminate_glare(image: Image.Image, rng: random.Random) -> Image.Image:
    """A specular streak off the laminate, saturating a band across the text."""
    arr = np.asarray(image).astype(np.float32)
    h, w = arr.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    slope, offset = rng.uniform(-0.35, 0.35), rng.uniform(0.3, 0.7) * h
    dist = np.abs(yy - (offset + slope * (xx - w / 2))) / rng.uniform(18, 30)
    arr += (np.exp(-(dist**2)) * 235)[:, :, None]
    return Image.fromarray(np.clip(arr, 0, 255).astype("uint8"))


def hard_shadow(image: Image.Image, rng: random.Random) -> Image.Image:
    """The phone's own shadow: a soft-edged dark polygon over part of the card."""
    w, h = image.size
    mask = Image.new("L", (w, h), 0)
    x = rng.uniform(0.35, 0.6) * w
    ImageDraw.Draw(mask).polygon(
        [(x, -10), (w + 10, -10), (w + 10, h + 10), (x + rng.uniform(-0.2, 0.2) * w, h + 10)],
        fill=255,
    )
    mask = mask.filter(ImageFilter.GaussianBlur(14))
    dark = np.asarray(mask).astype(np.float32)[:, :, None] / 255 * rng.uniform(0.5, 0.62)
    arr = np.asarray(image).astype(np.float32) * (1 - dark)
    return Image.fromarray(np.clip(arr, 0, 255).astype("uint8"))


def security_print(card: Image.Image, rng: random.Random) -> Image.Image:
    """Guilloche lines and a tinted wash printed under the text, as on real IDs."""
    w, h = card.size
    layer = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(layer)
    tint = rng.choice([(150, 190, 220), (205, 170, 200), (170, 205, 170)])
    for k in range(70):
        phase, amp = rng.uniform(0, 6.28), rng.uniform(10, 28)
        pts = [(x, k * h / 60 + amp * np.sin(x / rng.uniform(25, 45) + phase))
               for x in range(0, w, 6)]
        d.line(pts, fill=tint, width=2)
    wash = np.asarray(layer).astype(np.float32)
    arr = np.minimum(np.asarray(card).astype(np.float32), wash)  # under dark text, over paper
    return Image.fromarray(arr.astype("uint8"))


def thumb(image: Image.Image, rng: random.Random, box: tuple[int, int]) -> Image.Image:
    """A thumb holding the card, covering the end of a field."""
    out = image.copy()
    d = ImageDraw.Draw(out)
    cx, cy = box
    d.ellipse([cx - 120, cy - 70, cx + 140, cy + 260], fill=rng.choice(
        [(224, 172, 140), (176, 124, 92), (120, 82, 60)]))
    return out.filter(ImageFilter.GaussianBlur(1.2))


def bent(image: Image.Image, rng: random.Random) -> Image.Image:
    """A card bowed in the wallet: rows bend along a gentle curve."""
    arr = np.asarray(image)
    h, w = arr.shape[:2]
    amp, period = rng.uniform(10, 16), rng.uniform(1.4, 2.0) * w
    out = np.empty_like(arr)
    for x in range(w):
        out[:, x] = np.roll(arr[:, x], int(amp * np.sin(np.pi * x / period)), axis=0)
    return Image.fromarray(out)


def photocopy(image: Image.Image, rng: random.Random) -> Image.Image:
    """A photocopy or fax of the card, scanned at low resolution: grey, speckled, soft."""
    gray = image.convert("L")
    gray = gray.resize((gray.width // 2, gray.height // 2), Image.Resampling.BILINEAR)
    arr = np.asarray(gray).astype(np.float32)
    arr = 70 + arr * 0.62  # washed-out toner
    speckle = np.random.default_rng(rng.randint(0, 10**6)).random(arr.shape)
    arr[speckle < 0.012] = 30
    arr[speckle > 0.988] = 245
    out = Image.fromarray(np.clip(arr, 0, 255).astype("uint8")).resize(image.size)
    return jpeg(out.convert("RGB"), 40)


STRESS_KINDS = ["motion_blur", "low_light", "far_away", "laminate_glare", "hard_shadow",
                "security_print", "thumb", "bent", "photocopy", "worst_case"]


def stress_capture(
    kind: str, p: Person, rng: random.Random, layout: str
) -> tuple[Image.Image, tuple]:
    """One realistic bad capture. Returns the image and any field the right answer leaves blank."""
    card = layout_a(p, rng) if layout == "a" else layout_b(p, rng)
    missing: tuple[str, ...] = ()
    if kind == "security_print":
        return phone_photo(security_print(card, rng), rng), missing
    if kind == "thumb":  # the thumb covers the end of the address, so it can't be read whole
        at = (640, 400) if layout == "a" else (560, 300)
        card, missing = thumb(card, rng, at), ("address",)
    if kind == "bent":
        card = bent(card, rng)
    if kind == "photocopy":
        return photocopy(on_background(card, rng, margin=40), rng), missing
    if kind == "far_away":
        return jpeg(lighting(far_away(card, rng), rng), 70), missing
    image = on_background(card, rng, margin=rng.randint(60, 120))
    image = perspective(image, rng, 0.03)
    if kind == "motion_blur":
        image = motion_blur(image, rng)
    elif kind == "low_light":
        image = low_light(image, rng)
    elif kind == "laminate_glare":
        image = laminate_glare(image, rng)
    elif kind == "hard_shadow":
        image = hard_shadow(image, rng)
    elif kind == "worst_case":  # dim room, shaky hand, shadow, heavy compression
        image = motion_blur(hard_shadow(low_light(image, rng), rng), rng)
        return jpeg(image, 45), missing
    return jpeg(lighting(image, rng), rng.randint(55, 72)), missing


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

    # Stress: its own seed, so adding it left the cards above byte-identical.
    rng = random.Random(SEED + 1)
    Faker.seed(SEED + 1)
    for i, kind in enumerate(STRESS_KINDS * 2):
        layout = "a" if i < len(STRESS_KINDS) else "b"
        p = person(fake, rng, unusual=i in (4, 13), apartment=i in (7, 16))
        img, missing = stress_capture(kind, p, rng, layout)
        save(img, f"{kind}_{layout}_{i:02d}", "stress", kind, p, missing=missing)
    return labels


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    built = build()
    (OUT / "labels.json").write_text(
        json.dumps([asdict(label) for label in built], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    counts = {s: sum(1 for b in built if b.set == s) for s in ("golden", "held_out", "stress")}
    print(f"Wrote {len(built)} synthetic IDs to {OUT}: {counts}")
