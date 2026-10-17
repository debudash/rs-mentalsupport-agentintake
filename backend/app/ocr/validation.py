"""Upload validation: type detected from the bytes (never the filename or browser header),
size limit, and the image must actually decode."""

import io

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:  # pragma: no cover - HEIC support is optional in dev environments
    pass

ACCEPTED = "a JPG, PNG or HEIC photo"
MAX_PIXELS = 40_000_000  # decompression-bomb guard


class UploadRejected(Exception):
    def __init__(self, reason: str, message: str):
        super().__init__(reason)
        self.reason = reason
        self.message = message


def sniff(data: bytes) -> str | None:
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[4:8] == b"ftyp" and data[8:12] in (
        b"heic",
        b"heix",
        b"mif1",
        b"msf1",
        b"hevc",
        b"heim",
    ):
        return "heic"
    return None


def load_image(data: bytes, max_bytes: int) -> Image.Image:
    if not data:
        raise UploadRejected("empty", f"That file is empty. Please choose {ACCEPTED}.")
    if len(data) > max_bytes:
        limit = max_bytes // (1024 * 1024)
        raise UploadRejected(
            "too_large", f"That file is over {limit} MB. Please choose a smaller photo."
        )
    if sniff(data) is None:
        raise UploadRejected(
            "wrong_type", f"That file isn't a photo we can read. Please choose {ACCEPTED}."
        )
    try:
        image = Image.open(io.BytesIO(data))
        if image.width * image.height > MAX_PIXELS:
            raise UploadRejected(
                "too_large", "That photo is too large. Please choose a smaller one."
            )
        image.load()
    except UploadRejected:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise UploadRejected(
            "corrupt", "That photo seems to be damaged. Please try another one."
        ) from exc
    # Apply the camera's orientation flag, then keep pixels only: EXIF (including GPS) and
    # every other metadata block are dropped.
    oriented = ImageOps.exif_transpose(image).convert("RGB")
    return Image.fromarray(np.asarray(oriented))
