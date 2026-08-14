from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo


ORDER_COLUMN_MARKERS = ("订单号", "订单编号")
_TRAILING_ZERO = re.compile(r"^([+-]?\d+)\.0+$")
_DATE_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y/%m/%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y/%m/%d %H:%M",
    "%Y-%m-%d",
    "%Y/%m/%d",
)


def clean_header(value: Any) -> str:
    return str(value or "").replace("\ufeff", "").strip()


def text_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)
        return value.replace(microsecond=0).isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        normalized = format(value.normalize(), "f")
        return "0" if normalized in {"-0", ""} else normalized
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return format(value, ".15g")
    text = str(value).replace("\r\n", "\n").replace("\r", "\n").strip()
    return text or None


def order_value(value: Any) -> str:
    text = text_value(value) or ""
    if text in {"-", "--"}:
        return ""
    match = _TRAILING_ZERO.fullmatch(text)
    return match.group(1) if match else text


def parse_business_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = text_value(value)
    if not text:
        raise ValueError("交易时间为空")
    normalized = text.replace("T", " ").strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(normalized, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(normalized).date()
    except ValueError as exc:
        raise ValueError(f"无法解析交易时间：{text}") from exc


def normalized_business_date(
    value: Any,
    year_replacements: Sequence[tuple[int, int]] = (),
) -> date:
    parsed = parse_business_date(value)
    replacements = dict(year_replacements)
    replacement = replacements.get(parsed.year)
    return parsed.replace(year=replacement) if replacement is not None else parsed


def find_order_key_columns(headers: Iterable[str]) -> tuple[str, ...]:
    return tuple(
        header
        for header in headers
        if any(marker in header for marker in ORDER_COLUMN_MARKERS)
    )


def make_business_key(row: Mapping[str, Any], columns: Sequence[str]) -> str:
    parts = [f"{column}={order_value(row.get(column))}" for column in columns]
    if not columns or all(not order_value(row.get(column)) for column in columns):
        raise ValueError("所有订单号/订单编号字段均为空")
    return "|".join(parts)


def normalized_values(row: Mapping[str, Any], headers: Sequence[str]) -> dict[str, str | None]:
    return {header: text_value(row.get(header)) for header in headers}


def _comparison_value(value: Any, data_type: str | None) -> str | None:
    text = text_value(value)
    if text is None or text in {"-", "--"}:
        return None
    if data_type in {"numeric", "decimal", "real", "double precision"}:
        try:
            numeric_text = text.replace(",", "").replace("¥", "").replace("￥", "").strip()
            is_percent = numeric_text.endswith("%")
            numeric_text = numeric_text.removesuffix("%").strip()
            number = Decimal(numeric_text)
            if is_percent:
                number /= Decimal("100")
            normalized = format(number.normalize(), "f")
            return "0" if normalized in {"-0", ""} else normalized
        except Exception:
            return text
    if data_type in {"smallint", "integer", "bigint"}:
        try:
            return str(int(Decimal(text.replace(",", ""))))
        except Exception:
            return text
    if data_type in {"timestamp with time zone", "timestamp without time zone", "timestamp"}:
        try:
            return text_value(datetime.fromisoformat(text.replace("T", " ")))
        except ValueError:
            return text
    return text


def database_value(value: Any, data_type: str | None) -> str | None:
    """Return the value shape used by existing raw-data loaders."""
    return _comparison_value(value, data_type)


def row_digest(
    values: Mapping[str, Any],
    headers: Sequence[str],
    column_types: Mapping[str, str] | None = None,
) -> str:
    types = column_types or {}
    payload = [[header, _comparison_value(values.get(header), types.get(header))] for header in headers]
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def normalize_customer_id(value: Any) -> str:
    return order_value(value).strip()
