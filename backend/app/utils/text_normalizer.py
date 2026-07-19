import re
import unicodedata
from difflib import SequenceMatcher


def normalize_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_plate(value: object) -> str:
    text = normalize_text(value).upper().replace(" ", "")
    return re.sub(r"[^A-Z0-9]", "", text)


def compact_key(value: object) -> str:
    return normalize_text(value).replace(" ", "")


def similarity(a: object, b: object) -> float:
    left = normalize_text(a)
    right = normalize_text(b)
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    if left in right or right in left:
        return 0.92
    return SequenceMatcher(None, left, right).ratio()
