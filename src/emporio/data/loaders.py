"""CSV loaders: read raw files, clean values and build validated domain models."""

import csv
import json
import logging
from pathlib import Path
from typing import Any

from emporio.data.cleaning import blank_to_none, detect_brand
from emporio.domain.models import (
    Category,
    Customer,
    Order,
    OrderItem,
    Product,
    Promotion,
)

logger = logging.getLogger(__name__)


def find_table_file(data_dir: Path, table: str) -> Path:
    """Locate a table CSV by name.

    Files are named like 'desafio_tecnico_ai_eng - products.csv', so match either
    'products.csv' or '<anything> - products.csv'.
    """
    matches = [
        p for p in data_dir.glob("*.csv") if p.stem == table or p.stem.endswith(f" - {table}")
    ]
    if len(matches) != 1:
        raise FileNotFoundError(f"Expected exactly one CSV for table '{table}' in {data_dir}")
    return matches[0]


def _read_rows(data_dir: Path, table: str) -> list[dict[str, Any]]:
    path = find_table_file(data_dir, table)
    # utf-8-sig tolerates a BOM; csv handles the CRLF line endings.
    with path.open(newline="", encoding="utf-8-sig") as fh:
        rows = [{k.strip(): blank_to_none(v) for k, v in row.items()} for row in csv.DictReader(fh)]
    logger.debug("Read %d rows from %s", len(rows), path.name)
    return rows


def _parse_specs(raw: str | None) -> dict[str, str]:
    """Parse the JSON 'specs' column. Values become strings for a uniform shape."""
    if not raw:
        return {}
    return {str(k): str(v) for k, v in json.loads(raw).items()}


def load_categories(data_dir: Path) -> list[Category]:
    return [Category(**row) for row in _read_rows(data_dir, "categories")]


def load_products(data_dir: Path) -> list[Product]:
    products = []
    for row in _read_rows(data_dir, "products"):
        row["specs"] = _parse_specs(row.get("specs"))
        row["brand"] = detect_brand(row["name"])
        products.append(Product(**row))
    return products


def load_customers(data_dir: Path) -> list[Customer]:
    return [Customer(**row) for row in _read_rows(data_dir, "customers")]


def load_orders(data_dir: Path) -> list[Order]:
    return [Order(**row) for row in _read_rows(data_dir, "orders")]


def load_order_items(data_dir: Path) -> list[OrderItem]:
    return [OrderItem(**row) for row in _read_rows(data_dir, "order_items")]


def load_promotions(data_dir: Path) -> list[Promotion]:
    return [Promotion(**row) for row in _read_rows(data_dir, "promotions")]