from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from psycopg import Connection, sql

from upload.models import MixedSalesRules, PreparedRow, StoreUploadConfig
from upload.normalization import make_business_key, normalized_values, order_value, row_digest


class UploadRepository:
    def __init__(self, conn: Connection, config: StoreUploadConfig):
        self.conn = conn
        self.config = config
        self.schema = sql.Identifier(config.schema_name)

    def raw_columns(self) -> tuple[str, ...]:
        return tuple(self.raw_column_types())

    def raw_column_types(self) -> dict[str, str]:
        rows = self.conn.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = 'raw_data'
            ORDER BY ordinal_position
            """,
            (self.config.schema_name,),
        ).fetchall()
        return {
            row["column_name"]: row["data_type"]
            for row in rows
            if row["column_name"] not in {"id", "created_at", "updated_at"}
        }

    def customer_columns(self) -> tuple[str, ...]:
        rows = self.conn.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = 'customer_id_mapping'
            ORDER BY ordinal_position
            """,
            (self.config.schema_name,),
        ).fetchall()
        return tuple(row["column_name"] for row in rows)

    def _business_timestamp_text(self):
        expression = sql.SQL("NULLIF(BTRIM({}::text), '')").format(
            sql.Identifier(self.config.transaction_time_column)
        )
        for source_year, target_year in self.config.date_year_replacements:
            expression = sql.SQL("REGEXP_REPLACE({}, {}, {})").format(
                expression,
                sql.Literal(f"^{source_year}"),
                sql.Literal(str(target_year)),
            )
        return expression

    def _business_date_expression(self):
        timestamp_text = self._business_timestamp_text()
        return sql.SQL(
            "CASE WHEN pg_input_is_valid({0}, 'timestamp') THEN ({0})::timestamp::date END"
        ).format(timestamp_text)

    def existing_dates(self, dates: set[Any]) -> set[Any]:
        if not dates:
            return set()
        date_expression = self._business_date_expression()
        query = sql.SQL(
            "SELECT DISTINCT {date_expression} AS business_date "
            "FROM {schema}.raw_data WHERE {date_expression} = ANY(%s)"
        ).format(date_expression=date_expression, schema=self.schema)
        return {row["business_date"] for row in self.conn.execute(query, (list(dates),)).fetchall()}

    def raw_row_counts_by_date(self, dates: set[Any]) -> dict[Any, int]:
        if not dates:
            return {}
        date_expression = self._business_date_expression()
        query = sql.SQL(
            "SELECT {date_expression} AS business_date, COUNT(*)::bigint AS row_count "
            "FROM {schema}.raw_data WHERE {date_expression} = ANY(%s) "
            "GROUP BY {date_expression}"
        ).format(date_expression=date_expression, schema=self.schema)
        return {
            row["business_date"]: row["row_count"]
            for row in self.conn.execute(query, (list(dates),)).fetchall()
        }

    def daily_sales_amounts(self, dates: set[Any]) -> dict[Any, Any]:
        if not dates:
            return {}
        query = sql.SQL(
            "SELECT transaction_date, transaction_amount "
            "FROM {}.daily_sales WHERE transaction_date = ANY(%s)"
        ).format(self.schema)
        return {
            row["transaction_date"]: row["transaction_amount"]
            for row in self.conn.execute(query, (list(dates),)).fetchall()
        }

    def daily_raw_amounts(
        self,
        dates: set[Any],
        amount_column: str,
        *,
        positive_only: bool = False,
    ) -> dict[Any, Any]:
        """Sum one trusted numeric-like raw column by configured business date."""
        if not dates:
            return {}
        date_expression = self._business_date_expression()
        amount_text = sql.SQL(
            "NULLIF(REGEXP_REPLACE(COALESCE({}::text, ''), '[,￥¥[:space:]]', '', 'g'), '')"
        ).format(sql.Identifier(amount_column))
        valid_amount = sql.SQL("pg_input_is_valid({}, 'numeric')").format(amount_text)
        positive = sql.SQL(" AND ({})::numeric > 0").format(amount_text) if positive_only else sql.SQL("")
        query = sql.SQL(
            "SELECT {date_expression} AS business_date, "
            "SUM(CASE WHEN {valid_amount}{positive} THEN ({amount_text})::numeric ELSE 0 END) AS amount "
            "FROM {schema}.raw_data WHERE {date_expression} = ANY(%s) "
            "GROUP BY {date_expression}"
        ).format(
            date_expression=date_expression,
            valid_amount=valid_amount,
            positive=positive,
            amount_text=amount_text,
            schema=self.schema,
        )
        return {
            row["business_date"]: row["amount"]
            for row in self.conn.execute(query, (list(dates),)).fetchall()
        }

    def alibaba_daily_raw_totals(
        self,
        dates: set[Any] | None = None,
    ) -> dict[Any, dict[str, Any]]:
        """Return trusted Alibaba gross-sales and refund totals from raw_data.

        Preview callers normally need only the affected comparison periods.  A
        bounded date set avoids parsing the complete raw table for every file.
        """
        if self.config.schema_name != "alibaba":
            raise ValueError("该原始汇总查询仅支持alibaba schema")
        date_expression = self._business_date_expression()
        shipped_text = sql.SQL(
            "NULLIF(REGEXP_REPLACE(COALESCE({}::text, ''), '[,￥¥[:space:]]', '', 'g'), '')"
        ).format(sql.Identifier("实发金额"))
        refund_text = sql.SQL(
            "NULLIF(REGEXP_REPLACE(COALESCE({}::text, ''), '[,￥¥[:space:]]', '', 'g'), '')"
        ).format(sql.Identifier("实退金额"))
        date_filter = (
            sql.SQL("WHERE {date_expression} = ANY(%s)").format(
                date_expression=date_expression,
            )
            if dates is not None
            else sql.SQL("WHERE {date_expression} IS NOT NULL").format(
                date_expression=date_expression,
            )
        )
        query = sql.SQL(
            "SELECT {date_expression} AS business_date, "
            "SUM(CASE WHEN BTRIM(COALESCE({status}::text, '')) = '已发货' "
            "THEN ROUND(CASE WHEN pg_input_is_valid({shipped}, 'numeric') THEN ({shipped})::numeric ELSE 0 END, 2) "
            "ELSE 0 END)::numeric(20,2) AS sales_amount, "
            "SUM(CASE WHEN BTRIM(COALESCE({status}::text, '')) = '已发货' "
            "AND pg_input_is_valid({refund}, 'numeric') THEN ROUND(({refund})::numeric, 2) ELSE 0 END)"
            "::numeric(20,2) AS refund_amount "
            "FROM {schema}.raw_data "
            "{date_filter} "
            "GROUP BY {date_expression}"
        ).format(
            date_expression=date_expression,
            status=sql.Identifier("订单状态"),
            shipped=shipped_text,
            refund=refund_text,
            schema=self.schema,
            date_filter=date_filter,
        )
        return {
            row["business_date"]: {
                "sales_amount": row["sales_amount"],
                "refund_amount": row["refund_amount"],
            }
            for row in self.conn.execute(
                query,
                ((list(dates),) if dates is not None else ()),
            ).fetchall()
        }

    def prepared_raw_rows_by_dates(
        self,
        dates: set[Any],
        columns: Sequence[str],
    ) -> list[PreparedRow]:
        """Read selected existing raw rows for a date-replacement preview."""
        if not dates:
            return []
        selected = tuple(dict.fromkeys(columns))
        date_expression = self._business_date_expression()
        query = sql.SQL(
            "SELECT id, {date_expression} AS business_date, {columns} "
            "FROM {schema}.raw_data WHERE {date_expression} = ANY(%s)"
        ).format(
            date_expression=date_expression,
            columns=sql.SQL(", ").join(sql.Identifier(column) for column in selected),
            schema=self.schema,
        )
        result: list[PreparedRow] = []
        for row in self.conn.execute(query, (list(dates),)).fetchall():
            values = {column: row[column] for column in selected}
            result.append(PreparedRow(
                source_row=0,
                values=values,
                business_date=row["business_date"],
                business_key=f"database_id={row['id']}",
                row_hash="",
            ))
        return result

    def daily_refund_amounts(
        self,
        dates: set[Any],
        rules: MixedSalesRules,
    ) -> dict[Any, Any]:
        if not dates:
            return {}
        date_expression = self._business_date_expression()
        amount_text = sql.SQL(
            "NULLIF(REGEXP_REPLACE(COALESCE({}::text, ''), '[,￥¥[:space:]]', '', 'g'), '')"
        ).format(sql.Identifier(rules.amount_column))
        query = sql.SQL(
            "SELECT {date_expression} AS business_date, "
            "SUM(CASE WHEN BTRIM(COALESCE({refund_status}::text, '')) <> ALL(%s) "
            "AND pg_input_is_valid({amount_text}, 'numeric') "
            "THEN ({amount_text})::numeric ELSE 0 END) AS refund_amount "
            "FROM {schema}.raw_data "
            "WHERE {date_expression} = ANY(%s) "
            "GROUP BY {date_expression}"
        ).format(
            date_expression=date_expression,
            refund_status=sql.Identifier(rules.refund_status_column),
            amount_text=amount_text,
            schema=self.schema,
        )
        return {
            row["business_date"]: row["refund_amount"]
            for row in self.conn.execute(
                query,
                (list(rules.non_refund_statuses), list(dates)),
            ).fetchall()
        }

    def period_amounts(
        self,
        schema_name: str,
        table_name: str,
        amount_column: str,
        period_starts: set[Any],
    ) -> dict[Any, Any]:
        if not period_starts:
            return {}
        query = sql.SQL(
            "SELECT period_start, period_end, {amount_column} AS amount "
            "FROM {schema}.{table} WHERE period_start = ANY(%s)"
        ).format(
            amount_column=sql.Identifier(amount_column),
            schema=sql.Identifier(schema_name),
            table=sql.Identifier(table_name),
        )
        return {
            row["period_start"]: {
                "period_end": row["period_end"],
                "amount": row["amount"],
            }
            for row in self.conn.execute(query, (list(period_starts),)).fetchall()
        }

    def rows_by_keys(
        self,
        key_columns: Sequence[str],
        prepared: Sequence[PreparedRow],
        compare_headers: Sequence[str],
        column_types: dict[str, str],
        existing_dates: set[Any] | None,
    ) -> dict[str, dict[str, Any]]:
        if not prepared:
            return {}
        keys_by_column = [
            sorted({order_value(item.values.get(column)) for item in prepared})
            for column in key_columns
        ]
        conditions = [
            sql.SQL(
                "REGEXP_REPLACE(BTRIM(COALESCE({}::text, '')), '\\.0+$', '') = ANY(%s)"
            ).format(sql.Identifier(column))
            for column in key_columns
        ]
        if existing_dates is not None:
            conditions.append(sql.SQL("{} = ANY(%s)").format(self._business_date_expression()))
        query = sql.SQL("SELECT id, {business_date} AS business_date, {columns} FROM {schema}.raw_data WHERE ").format(
            business_date=self._business_date_expression(),
            columns=sql.SQL(", ").join(sql.Identifier(column) for column in compare_headers),
            schema=self.schema,
        ) + sql.SQL(" AND ").join(conditions)
        result: dict[str, dict[str, Any]] = {}
        parameters = [*keys_by_column]
        if existing_dates is not None:
            parameters.append(list(existing_dates))
        for row in self.conn.execute(query, parameters).fetchall():
            key = make_business_key(row, key_columns)
            values = normalized_values(row, compare_headers)
            if key in result:
                raise ValueError(f"数据库原始表存在重复联合订单键：{key}")
            result[key] = {
                "id": row["id"],
                "hash": row_digest(values, compare_headers, column_types),
                "values": values,
                "business_date": row["business_date"],
            }
        return result

    def existing_customer_ids(self, ids: Iterable[str]) -> set[str]:
        values = sorted(set(ids))
        if not values:
            return set()
        query = sql.SQL("SELECT customer_id FROM {}.customer_id_mapping WHERE customer_id = ANY(%s)").format(self.schema)
        return {row["customer_id"] for row in self.conn.execute(query, (values,)).fetchall()}

    def lock_store_upload(self) -> None:
        self.conn.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"upload:{self.config.schema_name}",),
        )

    def write_raw_changes(self, analysis) -> tuple[int, int, int]:
        if analysis.existing_date_policy == "upsert":
            return self._write_keyed_upserts(analysis)
        inserts = [item for item in analysis.compared_rows if item.action == "insert"]
        columns = analysis.headers
        deleted = 0
        if analysis.existing_date_policy == "replace" and analysis.existing_dates:
            query = sql.SQL(
                "DELETE FROM {}.raw_data WHERE {} = ANY(%s)"
            ).format(self.schema, self._business_date_expression())
            cursor = self.conn.execute(query, (list(analysis.existing_dates),))
            deleted = cursor.rowcount
        if inserts:
            query = sql.SQL("INSERT INTO {}.raw_data ({}) VALUES ({})").format(
                self.schema,
                sql.SQL(", ").join(sql.Identifier(column) for column in columns),
                sql.SQL(", ").join(sql.Placeholder() for _ in columns),
            )
            with self.conn.cursor() as cursor:
                cursor.executemany(
                    query,
                    [tuple(item.prepared.values.get(column) for column in columns) for item in inserts],
                )
        return deleted, len(inserts), 0

    def _write_keyed_upserts(self, analysis) -> tuple[int, int, int]:
        key_columns = self.config.row_key_columns
        if not key_columns:
            raise ValueError("明细增量上传未配置业务键")
        columns = analysis.headers
        changed = analysis.changed_rows
        if not changed:
            return 0, 0, 0
        raw_types = self.raw_column_types()
        # Recheck all changed business keys once after the advisory lock has
        # been acquired.  This keeps concurrent uploads safe without issuing
        # one unindexed full-table lookup for every source row.
        existing_by_key = self.rows_by_keys(
            key_columns,
            [item.prepared for item in changed],
            columns,
            raw_types,
            None,
        )
        update_existing = sql.SQL("UPDATE {}.raw_data SET {}, updated_at = CURRENT_TIMESTAMP WHERE id = %s").format(
            self.schema,
            sql.SQL(", ").join(
                sql.SQL("{} = %s").format(sql.Identifier(column)) for column in columns
            ),
        )
        insert_new = sql.SQL("INSERT INTO {}.raw_data ({}) VALUES ({})").format(
            self.schema,
            sql.SQL(", ").join(sql.Identifier(column) for column in columns),
            sql.SQL(", ").join(sql.Placeholder() for _ in columns),
        )
        insert_values: list[tuple[Any, ...]] = []
        update_values: list[tuple[Any, ...]] = []
        for item in changed:
            existing = existing_by_key.get(item.prepared.business_key)
            values = tuple(item.prepared.values.get(column) for column in columns)
            if existing:
                if existing["hash"] != item.prepared.row_hash:
                    update_values.append((*values, existing["id"]))
            else:
                insert_values.append(values)
        with self.conn.cursor() as cursor:
            if insert_values:
                cursor.executemany(insert_new, insert_values)
            if update_values:
                cursor.executemany(update_existing, update_values)
        return 0, len(insert_values), len(update_values)

    def insert_missing_customers(self, customers: Sequence[dict[str, str]]) -> int:
        if not customers:
            return 0
        available = set(self.customer_columns())
        configured = self.config.customer_mapping_columns
        missing_columns = [column for column in configured if column not in available]
        if missing_columns:
            raise ValueError(
                f"{self.config.schema_name}.customer_id_mapping缺少配置字段：{', '.join(missing_columns)}"
            )
        query = sql.SQL("INSERT INTO {}.customer_id_mapping ({}) VALUES ({})").format(
            self.schema,
            sql.SQL(", ").join(sql.Identifier(column) for column in configured),
            sql.SQL(", ").join(sql.Placeholder() for _ in configured),
        )
        with self.conn.cursor() as cursor:
            cursor.executemany(
                query,
                [tuple(customer.get(column) or None for column in configured) for customer in customers],
            )
        return len(customers)
