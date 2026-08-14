from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Mapping, Sequence


CustomerResolver = Callable[[Mapping[str, Any]], Mapping[str, str] | None]


@dataclass(frozen=True)
class MixedSalesRules:
    """How to classify gross sales and refunds inside one sales export."""

    amount_column: str
    order_status_column: str
    valid_sales_statuses: tuple[str, ...]
    refund_status_column: str
    non_refund_statuses: tuple[str, ...]


@dataclass(frozen=True)
class StoreUploadConfig:
    store_key: str
    schema_name: str
    transaction_time_column: str
    customer_resolver: CustomerResolver
    customer_mapping_columns: tuple[str, ...]
    downstream_tables: tuple[str, ...]
    aggregate_path: tuple[str, ...]
    required_upload_columns: tuple[str, ...] = ()
    date_year_replacements: tuple[tuple[int, int], ...] = ()
    mixed_sales_rules: MixedSalesRules | None = None
    business_preview_builder: Callable[..., dict[str, Any]] | None = None
    commit_enabled: bool = False
    existing_date_policy: str = "skip"
    ignored_upload_columns: tuple[str, ...] = ()
    row_key_columns: tuple[str, ...] = ()
    analysis_preview_builder: Callable[..., dict[str, Any]] | None = None


@dataclass(frozen=True)
class ParsedFile:
    headers: tuple[str, ...]
    rows: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class PreparedRow:
    source_row: int
    values: Mapping[str, str | None]
    business_date: date | None
    business_key: str
    row_hash: str


@dataclass(frozen=True)
class ComparedRow:
    prepared: PreparedRow
    action: str
    existing_id: int | None = None
    previous_values: Mapping[str, str | None] | None = None
    previous_business_date: date | None = None


@dataclass
class UploadAnalysis:
    store_key: str
    schema_name: str
    headers: tuple[str, ...]
    order_key_columns: tuple[str, ...]
    file_dates: set[date] = field(default_factory=set)
    existing_dates: set[date] = field(default_factory=set)
    compared_rows: list[ComparedRow] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    duplicate_identical_rows: int = 0
    same_key_updated_rows: int = 0
    customer_candidates: list[dict[str, str]] = field(default_factory=list)
    missing_customers: list[dict[str, str]] = field(default_factory=list)
    customer_mapping_affected_dates: set[date] = field(default_factory=set)
    refresh_tables: tuple[str, ...] = ()
    aggregate_path: tuple[str, ...] = ()
    raw_columns_missing_from_file: tuple[str, ...] = ()
    ignored_upload_columns: tuple[str, ...] = ()
    excluded_undated_rows: int = 0
    skipped_existing_rows: int = 0
    existing_date_policy: str = "skip"
    database_rows_by_date: dict[date, int] = field(default_factory=dict)
    business_preview: dict[str, Any] = field(default_factory=dict)

    @property
    def counts(self) -> dict[str, int]:
        result = {"insert": 0, "update": 0, "unchanged": 0}
        for item in self.compared_rows:
            result[item.action] += 1
        return result

    @property
    def changed_rows(self) -> list[ComparedRow]:
        return [item for item in self.compared_rows if item.action in {"insert", "update"}]

    @property
    def affected_dates(self) -> set[date]:
        dates = {
            item.prepared.business_date
            for item in self.changed_rows
            if item.prepared.business_date is not None
        }
        dates.update(
            item.previous_business_date
            for item in self.changed_rows
            if item.previous_business_date is not None
        )
        dates.update(self.customer_mapping_affected_dates)
        return dates

    @property
    def rows_to_delete(self) -> int:
        if self.existing_date_policy != "replace":
            return 0
        return sum(self.database_rows_by_date.get(value, 0) for value in self.existing_dates)
