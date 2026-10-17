"""Document reader: an ID photo in, name / DOB / address out — each either confidently
read or left blank. The image exists only in memory for the duration of the call."""

from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache

from app.config import get_settings
from app.ocr import parse, preprocess
from app.ocr.engines import FakeEngine, OCREngine, TesseractEngine
from app.ocr.validation import UploadRejected, load_image

__all__ = ["DocumentReader", "FieldRead", "ReadResult", "UploadRejected", "get_reader"]


@dataclass(frozen=True)
class FieldRead:
    value: str | None
    confidence: float | None


@dataclass
class ReadResult:
    fields: dict[str, FieldRead] = field(default_factory=dict)
    failure_reason: str | None = None  # no_text | unreadable | engine_error

    @property
    def any_read(self) -> bool:
        return any(f.value for f in self.fields.values())


class DocumentReader:
    def __init__(self, engine: OCREngine, threshold: float, max_bytes: int):
        self._engine = engine
        self._threshold = threshold
        self._max_bytes = max_bytes

    @property
    def engine_name(self) -> str:
        return self._engine.name

    def available(self) -> bool:
        return self._engine.available()

    def read_identity(self, data: bytes, today: date | None = None) -> ReadResult:
        """Raises UploadRejected for bad uploads; OCR problems come back as a result."""
        image = load_image(data, self._max_bytes)
        best: dict[str, parse.Candidate] = {}
        saw_text = False
        try:
            for gray in preprocess.prepare(image):
                lines = self._engine.read(gray)
                saw_text = saw_text or any(ln.text.strip() for ln in lines)
                for name, candidate in parse.extract(lines, today).items():
                    if candidate and (
                        name not in best or candidate.confidence > best[name].confidence
                    ):
                        best[name] = candidate
                if all(n in best and best[n].confidence >= self._threshold for n in parse.FIELDS):
                    break
        except Exception:  # noqa: BLE001 - any engine failure degrades to manual entry
            return ReadResult(
                {n: FieldRead(None, None) for n in parse.FIELDS}, failure_reason="engine_error"
            )
        finally:
            del image

        fields = {}
        for name in parse.FIELDS:
            candidate = best.get(name)
            if candidate and candidate.confidence >= self._threshold:
                fields[name] = FieldRead(candidate.value, round(candidate.confidence, 1))
            else:
                fields[name] = FieldRead(
                    None, round(candidate.confidence, 1) if candidate else None
                )
        result = ReadResult(fields)
        if not result.any_read:
            result.failure_reason = "unreadable" if saw_text else "no_text"
        return result


@lru_cache
def get_reader() -> DocumentReader:
    settings = get_settings()
    engine: OCREngine = TesseractEngine() if settings.ocr_engine == "tesseract" else FakeEngine()
    return DocumentReader(engine, settings.ocr_confidence_threshold, settings.upload_max_bytes)
