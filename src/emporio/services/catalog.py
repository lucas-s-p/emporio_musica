"""Product search with synonyms, availability and similar-product suggestions."""

import re
from dataclasses import dataclass, field
from decimal import Decimal

from emporio.data import Store
from emporio.data.cleaning import normalize_text
from emporio.domain.models import Product, ProductStatus
from emporio.services.pricing import PriceQuote, build_quote

# Product names do not contain the instrument type ("Yamaha C40 Nylon Natural"), so type words
# map to categories instead of text. Keys are normalized and singular.
CATEGORY_TERMS: dict[str, tuple[int, ...]] = {
    "guitarra": (1,), "guitar": (1,),
    "baixo": (2,), "bass": (2,),
    "bateria": (3,), "percussao": (3,),
    "teclado": (4,), "piano": (4,), "sintetizador": (4,), "synth": (4,), "arranjador": (4,),
    "violao": (5,),
    "flauta": (6,), "clarinete": (6,), "saxofone": (6,), "sax": (6,), "oboe": (6,),
    "trompete": (7,), "trombone": (7,), "tuba": (7,), "trompa": (7,),
    "sopro": (6, 7),
    "violino": (8,), "viola": (8,), "violoncelo": (8,), "cello": (8,), "contrabaixo": (8,),
    "ukulele": (9,), "ukelele": (9,), "ukule": (9,),
}  # fmt: skip

# Soft modifiers: alternative spellings matched against name, brand, category and specs.
# They are dropped (and reported) when they would leave no result, e.g. "guitarra elétrica",
# since no guitar name says "elétrica".
MODIFIER_TERMS: dict[str, tuple[str, ...]] = {
    "aco": ("aco", "steel", "folk"), "steel": ("aco", "steel", "folk"), "folk": ("aco", "folk"),
    "nylon": ("nylon", "classic"), "nailon": ("nylon", "classic"),
    "classico": ("nylon", "classic"), "classica": ("nylon", "classic"),
    "eletrico": ("eletrico", "electric"), "eletrica": ("eletrico", "electric"),
    "eletroacustico": ("eletrico", "electric"), "eletroacustica": ("eletrico", "electric"),
    "amplificado": ("eletrico", "electric"),
}  # fmt: skip

STOPWORDS = frozenset(
    "de do da dos das um uma uns umas para pra com sem ate por em no na nos nas o a os as e ou "
    "que qual quais quero queria quer tem tenho voces voce preco precos custa custando valor "
    "opcao opcoes disponivel disponiveis modelo modelos mais menos barato barata".split()
)  # fmt: skip


# The store sells only instruments (policy 7.1). "corda" alone is ambiguous: "7 cordas" is a
# guitar model, "cordas de nylon" is an accessory.
ACCESSORY_TERMS = frozenset(
    "cabo palheta pedal amplificador case capa afinador baqueta estante".split()
)


class Availability:
    IN_STOCK = "in_stock"
    OUT_OF_STOCK = "out_of_stock"
    DISCONTINUED = "discontinued"
    COMING_SOON = "coming_soon"


def availability_of(product: Product) -> str:
    if product.status is ProductStatus.DISCONTINUED:
        return Availability.DISCONTINUED
    if product.status is ProductStatus.COMING_SOON:
        return Availability.COMING_SOON
    return Availability.IN_STOCK if product.stock_quantity > 0 else Availability.OUT_OF_STOCK


def quote_for(store: Store, product: Product) -> PriceQuote:
    return build_quote(product, store.promotions.active_for(product.product_id))


def _singular(word: str) -> str:
    if word.endswith("oes") and len(word) > 4:
        return word[:-3] + "ao"
    if word.endswith("s") and len(word) > 3:
        return word[:-1]
    return word


def _words(text: str) -> list[str]:
    """Normalized singular words. Hyphenated codes yield the joined code and its parts."""
    out: list[str] = []
    for raw in normalize_text(text).split():
        cleaned = re.sub(r"[^a-z0-9-]", "", raw).strip("-")
        if not cleaned:
            continue
        out.append(_singular(cleaned.replace("-", "")))
        if "-" in cleaned:
            out.extend(_singular(part) for part in cleaned.split("-") if part)
    return out


def _query_terms(query: str) -> list[str]:
    terms = []
    for word in _words(query):
        if word in STOPWORDS or (word.isdigit() and len(word) < 3):
            continue
        terms.append(word)
    return list(dict.fromkeys(terms))


def mentions_accessory(text: str) -> bool:
    """True when the text asks for an accessory the store does not sell."""
    words = _words(text)
    if any(word in ACCESSORY_TERMS for word in words):
        return True
    return "corda" in words and not any(word.isdigit() for word in words)


def resolve_category(text: str, store: Store) -> tuple[int, ...] | None:
    """Category ids for free text like "violões" or "Teclados e Pianos", None if unknown."""
    words = _words(text)
    for word in words:
        if word in CATEGORY_TERMS:
            return CATEGORY_TERMS[word]
    wanted = set(words) - STOPWORDS
    for category in store.categories.all():
        if wanted and wanted <= set(_words(category.name)):
            return (category.category_id,)
    return None


def _haystack(store: Store, product: Product) -> set[str]:
    category = store.categories.get(product.category_id)
    parts = [product.name, product.brand or "", category.name if category else ""]
    parts.extend(product.specs.values())
    return set(_words(" ".join(parts)))


@dataclass(frozen=True)
class SearchOutcome:
    products: list[Product]
    hidden_unavailable: int = 0
    relaxed_terms: list[str] = field(default_factory=list)


def search_products(
    store: Store,
    *,
    query: str | None = None,
    category_ids: tuple[int, ...] | None = None,
    brand: str | None = None,
    min_price: Decimal | None = None,
    max_price: Decimal | None = None,
    only_available: bool = True,
) -> SearchOutcome:
    """Search the catalog.

    Category words and unknown words (brand, model) are strict: every one must match.
    Modifier words (aço, nylon, elétrico) narrow the result only when something matches.
    Price bounds apply to the card price (promotion applied, if any). Results are sorted by
    price, cheapest first.
    """
    candidates = store.products.all()
    if category_ids:
        candidates = [p for p in candidates if p.category_id in category_ids]

    soft: list[tuple[str, tuple[str, ...]]] = []
    for term in _query_terms(query or ""):
        if term in CATEGORY_TERMS:
            ids = CATEGORY_TERMS[term]
            candidates = [p for p in candidates if p.category_id in ids]
        elif term in MODIFIER_TERMS:
            soft.append((term, MODIFIER_TERMS[term]))
        else:
            candidates = [p for p in candidates if term in _haystack(store, p)]

    relaxed: list[str] = []
    for term, alternatives in soft:
        narrowed = [
            p for p in candidates if any(alt in _haystack(store, p) for alt in alternatives)
        ]
        if narrowed:
            candidates = narrowed
        else:
            relaxed.append(term)

    if brand:
        wanted = normalize_text(brand)
        candidates = [p for p in candidates if p.brand and normalize_text(p.brand) == wanted]
    if min_price is not None:
        candidates = [p for p in candidates if quote_for(store, p).price >= min_price]
    if max_price is not None:
        candidates = [p for p in candidates if quote_for(store, p).price <= max_price]

    hidden = 0
    if only_available:
        available = [p for p in candidates if availability_of(p) == Availability.IN_STOCK]
        hidden = len(candidates) - len(available)
        candidates = available

    ordered = sorted(candidates, key=lambda p: (quote_for(store, p).price, p.name))
    return SearchOutcome(ordered, hidden, relaxed)


def similar_products(store: Store, product: Product, limit: int = 3) -> list[Product]:
    """Available products of the same category, closest in list price first."""
    pool = [
        p
        for p in store.products.by_category(product.category_id)
        if p.product_id != product.product_id and availability_of(p) == Availability.IN_STOCK
    ]
    pool.sort(key=lambda p: (abs(p.price_brl - product.price_brl), p.product_id))
    return pool[:limit]
