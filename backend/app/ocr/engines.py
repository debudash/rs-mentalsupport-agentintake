"""OCR engine seam: Tesseract adapter and a Fake for tests."""

import shutil
from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass(frozen=True)
class Line:
    text: str
    confidence: float  # 0-100
    words: tuple[tuple[str, float], ...] = ()


class OCREngine(Protocol):
    name: str

    def read(self, gray: np.ndarray) -> list[Line]: ...

    def available(self) -> bool: ...


class TesseractEngine:
    name = "tesseract"

    def __init__(self, psm: int = 4):
        self._config = f"--oem 1 --psm {psm}"

    def available(self) -> bool:
        return shutil.which("tesseract") is not None

    def version(self) -> str:
        import pytesseract

        return str(pytesseract.get_tesseract_version())

    def read(self, gray: np.ndarray) -> list[Line]:
        import pytesseract

        data = pytesseract.image_to_data(
            gray, lang="eng", config=self._config, output_type=pytesseract.Output.DICT
        )
        lines: dict[tuple[int, int, int], list[tuple[str, float]]] = {}
        for i, word in enumerate(data["text"]):
            word = word.strip()
            conf = float(data["conf"][i])
            if not word or conf < 0:
                continue
            key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            lines.setdefault(key, []).append((word, conf))
        result = []
        for key in sorted(lines):
            words = lines[key]
            text = " ".join(w for w, _ in words)
            result.append(Line(text, sum(c for _, c in words) / len(words), tuple(words)))
        return result


class FakeEngine:
    name = "fake"

    def __init__(self, lines: list[Line] | None = None, error: Exception | None = None):
        self._lines = lines or []
        self._error = error

    def available(self) -> bool:
        return True

    def read(self, gray: np.ndarray) -> list[Line]:
        if self._error:
            raise self._error
        return list(self._lines)
