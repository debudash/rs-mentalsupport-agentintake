"""Image cleanup before OCR: find the card and flatten it, straighten skew, even out light."""

import cv2
import numpy as np
from PIL import Image

TARGET_WIDTH = 1600


def to_cv(image: Image.Image) -> np.ndarray:
    return cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)


def _order(points: np.ndarray) -> np.ndarray:
    points = points.reshape(4, 2).astype("float32")
    s = points.sum(axis=1)
    d = np.diff(points, axis=1).ravel()
    return np.array(
        [points[np.argmin(s)], points[np.argmin(d)], points[np.argmax(s)], points[np.argmax(d)]],
        dtype="float32",
    )


def find_card(bgr: np.ndarray) -> np.ndarray | None:
    """Warp the largest card-shaped quadrilateral to a flat rectangle, if one is visible."""
    h, w = bgr.shape[:2]
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 40, 120)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=2)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:5]:
        area = cv2.contourArea(contour)
        if area < 0.25 * w * h or area > 0.98 * w * h:
            continue
        approx = cv2.approxPolyDP(contour, 0.02 * cv2.arcLength(contour, True), True)
        if len(approx) != 4:
            continue
        tl, tr, br, bl = _order(approx)
        width = int(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl)))
        height = int(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl)))
        if width < 200 or height < 120:
            continue
        if height > width:  # card photographed in portrait: keep the long side horizontal
            tl, tr, br, bl = tr, br, bl, tl
            width, height = height, width
        dst = np.array(
            [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], dtype="float32"
        )
        matrix = cv2.getPerspectiveTransform(np.array([tl, tr, br, bl]), dst)
        return cv2.warpPerspective(bgr, matrix, (width, height))
    return None


def deskew(gray: np.ndarray) -> np.ndarray:
    """Rotate so text lines are horizontal (handles mild skew when no card edge is found)."""
    inverted = cv2.bitwise_not(gray)
    thresh = cv2.threshold(inverted, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
    coords = np.column_stack(np.where(thresh > 0))
    if len(coords) < 50:
        return gray
    angle = cv2.minAreaRect(coords[:, ::-1].astype("float32"))[-1]
    if angle > 45:
        angle -= 90
    if abs(angle) < 0.5 or abs(angle) > 20:
        return gray
    h, w = gray.shape
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(
        gray, matrix, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
    )


def prepare(image: Image.Image) -> list[np.ndarray]:
    """Candidate images for OCR, best first: flattened card, then the whole photo."""
    bgr = to_cv(image)
    candidates = []
    card = find_card(bgr)
    for source in ([card] if card is not None else []) + [bgr]:
        h, w = source.shape[:2]
        scale = TARGET_WIDTH / w
        resized = cv2.resize(
            source,
            (TARGET_WIDTH, int(h * scale)),
            interpolation=cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA,
        )
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
        if source is not card:
            gray = deskew(gray)
        candidates.append(gray)
    return candidates
