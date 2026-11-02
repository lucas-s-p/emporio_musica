"""Text normalization and small cleaning helpers."""

import re
import unicodedata

# Brand is not a column in the CSV, so it is derived from the product name.
# "Music Man" comes first so a longer name wins over any shorter overlap.
KNOWN_BRANDS: tuple[str, ...] = (
    "Music Man", "Yamaha", "Tagima", "Giannini", "Rozini", "Shelby", "Crafter",
    "Martin", "Taylor", "Takamine", "Kala", "Kalani", "Ohana", "Fender", "Gibson",
    "Ibanez", "PRS", "Pearl", "Korg", "Nord", "Roland",
)  # fmt: skip

_BRAND_PATTERNS = [(b, re.compile(rf"\b{re.escape(b)}\b", re.IGNORECASE)) for b in KNOWN_BRANDS]


def normalize_text(text: str) -> str:
    """Lowercase, strip accents and collapse whitespace, for accent-insensitive matching."""
    decomposed = unicodedata.normalize("NFKD", text)
    no_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", no_accents).strip().lower()


def detect_brand(product_name: str) -> str | None:
    """Return the canonical brand found in the product name, or None."""
    for brand, pattern in _BRAND_PATTERNS:
        if pattern.search(product_name):
            return brand
    return None


def blank_to_none(value: str | None) -> str | None:
    """Convert empty or whitespace-only strings to None."""
    if value is None:
        return None
    value = value.strip()
    return value or None