"""Document reader: upload validation, parsing, never guessing, engine failure."""

import io
import shutil
from datetime import date

import numpy as np
import pytest
from PIL import Image, ImageDraw

from app.ocr import DocumentReader
from app.ocr.engines import FakeEngine, Line, TesseractEngine
from app.ocr.parse import clean_name, extract, parse_date
from app.ocr.preprocess import find_card, prepare
from app.ocr.validation import UploadRejected, load_image, sniff

MAX = 8 * 1024 * 1024


def png_bytes(size=(800, 500), color="white", draw_card=True) -> bytes:
    image = Image.new("RGB", size, "#556")
    if draw_card:
        d = ImageDraw.Draw(image)
        d.rectangle([80, 60, size[0] - 80, size[1] - 60], fill=color)
        d.text((120, 100), "NAME", fill="black")
    buf = io.BytesIO()
    image.save(buf, "PNG")
    return buf.getvalue()


def jpeg_with_exif_orientation() -> bytes:
    image = Image.new("RGB", (300, 100), "white")
    exif = image.getexif()
    exif[0x0112] = 6  # rotate 90 degrees
    exif[0x8825] = {2: (40.0, 26.0, 0.0)}  # GPS info that must not survive
    buf = io.BytesIO()
    image.save(buf, "JPEG", exif=exif)
    return buf.getvalue()


# ---- validation ------------------------------------------------------------------------


def test_sniff_by_content_not_name():
    assert sniff(png_bytes()) == "png"
    assert sniff(b"\xff\xd8\xff\xe0rest") == "jpeg"
    assert sniff(b"\x00\x00\x00\x18ftypheic....") == "heic"
    assert sniff(b"%PDF-1.7 not an image") is None


@pytest.mark.parametrize(
    "data,reason",
    [
        (b"", "empty"),
        (b"%PDF-1.4 fake pdf", "wrong_type"),
        (b"GIF89a....", "wrong_type"),
        (b"\x89PNG\r\n\x1a\n" + b"garbage" * 20, "corrupt"),
        (b"\xff\xd8\xff" + b"\x00" * (MAX + 1), "too_large"),
    ],
    ids=["empty", "pdf", "gif", "corrupt-png", "oversized"],
)
def test_bad_uploads_are_rejected_with_a_reason(data, reason):
    with pytest.raises(UploadRejected) as err:
        load_image(data, MAX)
    assert err.value.reason == reason
    assert err.value.message  # always a plain-language message


def test_orientation_is_applied_and_metadata_dropped():
    image = load_image(jpeg_with_exif_orientation(), MAX)
    assert image.size == (100, 300)  # rotated
    assert not image.getexif()  # GPS and everything else gone


# ---- parsing ---------------------------------------------------------------------------


def lines(*texts, conf=92.0):
    return [Line(t, conf) for t in texts]


def test_labels_above_values():
    found = extract(
        lines(
            "STATE OF RIVERSIDE",
            "NAME",
            "JANE Q DOE",
            "DATE OF BIRTH",
            "03/14/1990",
            "ADDRESS",
            "123 MAIN ST",
            "SPRINGFIELD, RS 12345",
            "ID NO. 4482910",
        )
    )
    assert found["name"].value == "Jane Q Doe"
    assert found["date_of_birth"].value == "1990-03-14"
    assert found["address"].value == "123 MAIN ST, SPRINGFIELD, RS 12345"


def test_labels_inline_and_fuzzy():
    found = extract(
        lines(
            "Name: Mary-Ann O'Neil",
            "DOB 14 Mar 1985",
            "Addr: 9 Harbor Way Apt 4, Port Lane, RS 20001",
        )
    )
    assert found["name"].value == "Mary-Ann O'Neil"
    assert found["date_of_birth"].value == "1985-03-14"
    assert found["address"].value.startswith("9 Harbor Way")
    misread = extract(lines("NAMF", "ROBERT SMITH"))
    assert misread["name"].value == "Robert Smith"


def test_partial_card_leaves_missing_fields_blank():
    found = extract(lines("NAME", "JANE DOE", "DATE OF BIRTH", "1990-03-14"))
    assert found["name"] and found["date_of_birth"]
    assert found["address"] is None


@pytest.mark.parametrize(
    "text,expected",
    [
        ("1990-03-14", "1990-03-14"),
        ("03/14/1990", "1990-03-14"),
        ("14 MAR 1990", "1990-03-14"),
        ("March 14, 1990", "1990-03-14"),
        ("13/45/1990", None),
        ("2099-01-01", None),
        ("no date here", None),
        ("O3/14/199O", "1990-03-14"),
    ],
)
def test_parse_date(text, expected):
    assert parse_date(text, today=date(2026, 10, 16)) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("JANE DOE", "Jane Doe"),
        ("J", None),
        ("JANE", None),
        ("12345 67890", None),
    ],
)
def test_clean_name(text, expected):
    assert clean_name(text) == expected


# ---- reader ----------------------------------------------------------------------------


def reader(engine, threshold=70):
    return DocumentReader(engine, threshold, MAX)


def test_reader_returns_confident_fields(fake_engine):
    result = reader(fake_engine).read_identity(png_bytes())
    assert result.fields["name"].value == "Jane Q Doe"
    assert result.fields["date_of_birth"].value == "1990-03-14"
    assert result.failure_reason is None


def test_low_confidence_fields_are_left_blank_not_guessed():
    engine = FakeEngine(lines("NAME", "JANE DOE", "DATE OF BIRTH", "1990-03-14", conf=40))
    result = reader(engine).read_identity(png_bytes())
    assert result.fields["name"].value is None
    assert result.fields["name"].confidence == 40
    assert result.failure_reason == "unreadable"


def test_no_text_is_reported():
    result = reader(FakeEngine([])).read_identity(png_bytes())
    assert not result.any_read and result.failure_reason == "no_text"


def test_engine_crash_degrades_to_manual_entry():
    result = reader(FakeEngine(error=RuntimeError("tesseract died"))).read_identity(png_bytes())
    assert result.failure_reason == "engine_error"
    assert all(f.value is None for f in result.fields.values())


def test_reader_rejects_bad_upload_before_ocr():
    with pytest.raises(UploadRejected):
        reader(FakeEngine([])).read_identity(b"not an image")


# ---- preprocessing ---------------------------------------------------------------------


def test_card_is_found_and_flattened():
    image = Image.open(io.BytesIO(png_bytes(size=(1000, 700))))
    bgr = np.asarray(image)[:, :, ::-1].copy()
    card = find_card(bgr)
    assert card is not None
    h, w = card.shape[:2]
    assert w > h and 700 < w < 900


def test_prepare_returns_grayscale_candidates():
    image = Image.open(io.BytesIO(png_bytes()))
    candidates = prepare(image)
    assert candidates and all(c.ndim == 2 for c in candidates)


@pytest.mark.tesseract
@pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract not installed")
def test_tesseract_reads_rendered_text():
    image = Image.new("L", (900, 200), 255)
    ImageDraw.Draw(image).text((20, 60), "NAME JANE DOE", fill=0)
    image = image.resize((2700, 600))
    read = TesseractEngine().read(np.asarray(image))
    assert any("JANE" in ln.text for ln in read)


# ---- label-free fallback ---------------------------------------------------------------


def test_fields_found_by_shape_when_labels_are_lost():
    found = extract(
        lines(
            "Riverside Member Card",
            "Jerome Griffin",
            "31 DEC 1989",
            "6040 Johnston Dr",
            "Amandaton, RS 54059",
            "Member 663803",
        )
    )
    assert found["name"].value == "Jerome Griffin"
    assert found["date_of_birth"].value == "1989-12-31"
    assert found["address"].value == "6040 Johnston Dr, Amandaton, RS 54059"


def test_shape_fallback_never_guesses_when_ambiguous():
    found = extract(
        lines(
            "Jerome Griffin",
            "31 DEC 1989",
            "Issued 02 JAN 2020",
            "6040 Johnston Dr",
            "12 Oak St",
            "Amandaton, RS 54059",
        )
    )
    assert found["date_of_birth"] is None and found["name"] is None  # two dates
    assert found["address"] is None  # two street lines


def test_shape_fallback_skips_header_as_name():
    found = extract(lines("Riverside Member Card", "31 DEC 1989"))
    assert found["name"] is None and found["date_of_birth"].value == "1989-12-31"


# ISSUE-010 — found by the OCR stress set (low_light_a_01): the "DATE OF BIRTH" label was
# pre-filled as the Client's name.
def test_shape_fallback_never_takes_a_field_label_as_the_name():
    found = extract(
        lines(
            ": NAME",
            "SARA PALMER |",
            "DATE OF BIRTH o",
            "10/19/1999 —",
            "ADDRESS",
            "5907 ELLIOTT WAY",
            "LAKE JACOB, RS 60016",
        )
    )
    assert found["date_of_birth"].value == "1999-10-19"
    assert found["name"] is None  # the only candidate above the date is a label: leave it blank
