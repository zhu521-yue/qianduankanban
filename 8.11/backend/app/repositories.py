from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any, Iterable

from psycopg import Connection, sql

from app.catalog import CUSTOMER_HEALTH_STATUSES, HEALTH_RULE_GROUPS, STORES, Store
from app.periods import Grain, PeriodWindow


def _changed_health_rules(current_rules: list[dict[str, Any]], submitted_rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    current_by_status = {rule["customer_health_status"]: rule for rule in current_rules}
    return [
        rule
        for rule in submitted_rules
        if rule["customer_health_status"] not in current_by_status
        or current_by_status[rule["customer_health_status"]]["state_instructions"] != rule["state_instructions"]
        or current_by_status[rule["customer_health_status"]]["follow_up_action"] != rule["follow_up_action"]
    ]


SALES_SPECS = {
    Grain.DAY: ("daily_sales", "transaction_date", None, "transaction_amount"),
    Grain.WEEK: ("weekly_sales", "period_start", "period_end", "weekly_transaction_amount"),
    Grain.MONTH: ("monthly_sales", "period_start", "period_end", "monthly_transaction_amount"),
    Grain.QUARTER: ("quarterly_sales", "period_start", "period_end", "quarterly_transaction_amount"),
    Grain.HALF: ("half_year_sales", "period_start", "period_end", "half_year_transaction_amount"),
}
CUSTOMER_SPECS = {
    Grain.DAY: ("customer_daily_sales", "transaction_date", None, "transaction_amount", None),
    Grain.WEEK: ("customer_weekly_sales", "period_start", "period_end", "weekly_transaction_amount", "weekly_purchase_count"),
    Grain.MONTH: ("customer_monthly_sales", "period_start", "period_end", "monthly_transaction_amount", "monthly_purchase_count"),
    Grain.QUARTER: ("customer_quarterly_sales", "period_start", "period_end", "quarterly_transaction_amount", "quarterly_purchase_count"),
    Grain.HALF: ("customer_half_year_sales", "period_start", "period_end", "half_year_transaction_amount", "half_year_purchase_count"),
}
PRODUCT_SPECS = {
    Grain.DAY: ("daily_product_sales", "transaction_date", None, "transaction_amount", "product_quantity"),
    Grain.WEEK: ("weekly_product_sales", "period_start", "period_end", "weekly_transaction_amount", "weekly_product_quantity"),
    Grain.MONTH: ("monthly_product_sales", "period_start", "period_end", "monthly_transaction_amount", "monthly_product_quantity"),
    Grain.QUARTER: ("quarterly_product_sales", "period_start", "period_end", "quarterly_transaction_amount", "quarterly_product_quantity"),
    Grain.HALF: ("half_year_product_sales", "period_start", "period_end", "half_year_transaction_amount", "half_year_product_quantity"),
}
CUSTOMER_PRODUCT_SPECS = {
    Grain.DAY: ("customer_daily_product_sales", "transaction_date", None, "transaction_amount", "product_quantity"),
    Grain.MONTH: ("customer_monthly_product_sales", "period_start", "period_end", "monthly_transaction_amount", "monthly_product_quantity"),
    Grain.QUARTER: ("customer_quarterly_product_sales", "period_start", "period_end", "quarterly_transaction_amount", "quarterly_product_quantity"),
    Grain.HALF: ("customer_half_year_product_sales", "period_start", "period_end", "half_year_transaction_amount", "half_year_product_quantity"),
}
REFUND_SPECS = {
    Grain.WEEK: ("weekly_refunds", "weekly_refund_amount"),
    Grain.MONTH: ("monthly_refunds", "monthly_refund_amount"),
    Grain.QUARTER: ("quarterly_refunds", "quarterly_refund_amount"),
    Grain.HALF: ("half_year_refunds", "half_year_refund_amount"),
}
PRESALE_SPECS = {
    Grain.MONTH: ("monthly_product_presales", "monthly_presale_transaction_amount", "monthly_presale_quantity"),
    Grain.QUARTER: ("quarterly_product_presales", "quarterly_presale_transaction_amount", "quarterly_presale_quantity"),
    Grain.HALF: ("half_year_product_presales", "half_year_presale_transaction_amount", "half_year_presale_quantity"),
}


def amount_text(value: Decimal | int | float | None) -> str:
    return f"{Decimal(value or 0):.2f}"


def _period_predicate(start_column: str, end_column: str | None) -> sql.Composed:
    if end_column is None:
        return sql.SQL("{} = %s").format(sql.Identifier(start_column))
    return sql.SQL("{} = %s AND {} = %s").format(sql.Identifier(start_column), sql.Identifier(end_column))


def _period_params(window: PeriodWindow, end_column: str | None) -> tuple[date, ...]:
    return (window.start,) if end_column is None else (window.start, window.end)


class DashboardRepository:
    def __init__(self, conn: Connection):
        self.conn = conn

    def _sum_for_store(self, store: Store, grain: Grain, window: PeriodWindow) -> Decimal:
        table, start_col, end_col, amount_col = SALES_SPECS[grain]
        query = sql.SQL("SELECT COALESCE(SUM({}), 0) AS amount FROM {}.{} WHERE ").format(
            sql.Identifier(amount_col), sql.Identifier(store.schema_name), sql.Identifier(table)
        ) + _period_predicate(start_col, end_col)
        row = self.conn.execute(query, _period_params(window, end_col)).fetchone()
        return Decimal(row["amount"])

    def sales_amount(self, stores: Iterable[str], grain: Grain, window: PeriodWindow) -> Decimal:
        return sum((self._sum_for_store(STORES[key], grain, window) for key in stores), Decimal(0))

    def sales_amount_by_store(self, stores: Iterable[str], grain: Grain, window: PeriodWindow) -> list[dict[str, Any]]:
        table = SALES_SPECS[grain][0]
        return [
            {
                "store_key": key,
                "store_name": STORES[key].name,
                "amount": self._sum_for_store(STORES[key], grain, window),
                "source": f"{STORES[key].schema_name}.{table}",
            }
            for key in stores
        ]

    def active_customer_count(self, stores: Iterable[str], grain: Grain, window: PeriodWindow) -> int:
        total = 0
        table, start_col, end_col, amount_col, _ = CUSTOMER_SPECS[grain]
        for key in stores:
            store = STORES[key]
            query = sql.SQL("SELECT COUNT(DISTINCT customer_id) AS value FROM {}.{} WHERE ").format(
                sql.Identifier(store.schema_name), sql.Identifier(table)
            ) + _period_predicate(start_col, end_col) + sql.SQL(" AND {} > 0").format(sql.Identifier(amount_col))
            total += int(self.conn.execute(query, _period_params(window, end_col)).fetchone()["value"])
        return total

    def product_count(self, stores: Iterable[str], grain: Grain, window: PeriodWindow) -> int:
        products: set[str] = set()
        table, start_col, end_col, _, quantity_col = PRODUCT_SPECS[grain]
        for key in stores:
            store = STORES[key]
            query = sql.SQL("SELECT DISTINCT product_code FROM {}.{} WHERE ").format(
                sql.Identifier(store.schema_name), sql.Identifier(table)
            ) + _period_predicate(start_col, end_col) + sql.SQL(" AND {} > 0").format(sql.Identifier(quantity_col))
            products.update(str(row["product_code"]) for row in self.conn.execute(query, _period_params(window, end_col)).fetchall())
        return len(products)

    def health_distribution(self, stores: Iterable[str], week: PeriodWindow, as_of: date) -> list[dict[str, Any]]:
        totals: dict[str, int] = defaultdict(int)
        for key in stores:
            store = STORES[key]
            query = sql.SQL("""
                WITH cohort AS (
                    SELECT DISTINCT customer_id
                    FROM {}.customer_weekly_sales
                    WHERE period_start = %s AND period_end = %s
                ),
                latest AS (
                    SELECT DISTINCT ON (h.customer_id) h.customer_id, h.customer_health_status
                    FROM {}.customer_health_detail h
                    JOIN cohort c ON c.customer_id = h.customer_id
                    WHERE h.period_start <= %s
                    ORDER BY h.customer_id, h.period_end DESC NULLS LAST, h.updated_at DESC NULLS LAST
                )
                SELECT COALESCE(latest.customer_health_status, '未评分') AS status, COUNT(*)::bigint AS count
                FROM cohort
                LEFT JOIN latest USING (customer_id)
                GROUP BY COALESCE(latest.customer_health_status, '未评分')
            """).format(sql.Identifier(store.schema_name), sql.Identifier(store.schema_name))
            for row in self.conn.execute(query, (week.start, week.end, as_of)).fetchall():
                totals[row["status"] or "未评分"] += int(row["count"])
        return [{"status": status, "count": count} for status, count in totals.items()]

    def top_products(self, stores: Iterable[str], grain: Grain, window: PeriodWindow, order_by: str, limit: int = 5) -> list[dict[str, Any]]:
        totals: dict[str, dict[str, Decimal]] = defaultdict(lambda: {"quantity": Decimal(0), "amount": Decimal(0)})
        table, start_col, end_col, amount_col, quantity_col = PRODUCT_SPECS[grain]
        for key in stores:
            store = STORES[key]
            query = sql.SQL("SELECT product_code, COALESCE(SUM({}), 0) AS amount, COALESCE(SUM({}), 0) AS quantity FROM {}.{} WHERE ").format(
                sql.Identifier(amount_col), sql.Identifier(quantity_col), sql.Identifier(store.schema_name), sql.Identifier(table)
            ) + _period_predicate(start_col, end_col) + sql.SQL(" GROUP BY product_code")
            for row in self.conn.execute(query, _period_params(window, end_col)).fetchall():
                item = totals[str(row["product_code"])]
                item["amount"] += Decimal(row["amount"])
                item["quantity"] += Decimal(row["quantity"])
        ranked = sorted(totals.items(), key=lambda item: (item[1][order_by], item[0]), reverse=True)[:limit]
        return [{"product_code": code, **values} for code, values in ranked]

    def refund_amount(self, stores: Iterable[str], grain: Grain, window: PeriodWindow) -> Decimal:
        if grain not in REFUND_SPECS:
            return Decimal(0)
        table, amount_col = REFUND_SPECS[grain]
        total = Decimal(0)
        for key in stores:
            store = STORES[key]
            query = sql.SQL("SELECT COALESCE(SUM({}), 0) AS amount FROM {}.{} WHERE period_start = %s AND period_end = %s").format(
                sql.Identifier(amount_col), sql.Identifier(store.schema_name), sql.Identifier(table)
            )
            total += Decimal(self.conn.execute(query, (window.start, window.end)).fetchone()["amount"])
        return total

    def refund_amount_by_store(self, stores: Iterable[str], grain: Grain, window: PeriodWindow) -> list[dict[str, Any]]:
        if grain not in REFUND_SPECS:
            return []
        table, amount_col = REFUND_SPECS[grain]
        rows: list[dict[str, Any]] = []
        for key in stores:
            store = STORES[key]
            query = sql.SQL("SELECT COALESCE(SUM({}), 0) AS amount FROM {}.{} WHERE period_start = %s AND period_end = %s").format(
                sql.Identifier(amount_col), sql.Identifier(store.schema_name), sql.Identifier(table)
            )
            amount = Decimal(self.conn.execute(query, (window.start, window.end)).fetchone()["amount"])
            rows.append({"store_key": key, "store_name": store.name, "amount": amount, "source": f"{store.schema_name}.{table}"})
        return rows

    def presale_summary(self, stores: Iterable[str], grain: Grain, window: PeriodWindow, limit: int = 5) -> dict[str, Any]:
        totals: dict[str, dict[str, Decimal]] = defaultdict(lambda: {"quantity": Decimal(0), "amount": Decimal(0)})
        if grain not in PRESALE_SPECS:
            return {"product_count": 0, "quantity": Decimal(0), "amount": Decimal(0), "products": []}
        table, amount_col, quantity_col = PRESALE_SPECS[grain]
        for key in stores:
            store = STORES[key]
            if store.schema_name != "weidian":
                continue
            query = sql.SQL("SELECT product_code, COALESCE(SUM({}), 0) AS amount, COALESCE(SUM({}), 0) AS quantity FROM {}.{} WHERE period_start = %s AND period_end = %s AND is_presale = true GROUP BY product_code").format(
                sql.Identifier(amount_col), sql.Identifier(quantity_col), sql.Identifier(store.schema_name), sql.Identifier(table)
            )
            for row in self.conn.execute(query, (window.start, window.end)).fetchall():
                item = totals[str(row["product_code"])]
                item["amount"] += Decimal(row["amount"])
                item["quantity"] += Decimal(row["quantity"])
        products = [{"product_code": code, **values} for code, values in sorted(totals.items(), key=lambda item: item[1]["amount"], reverse=True)[:limit]]
        return {
            "product_count": len(totals),
            "quantity": sum((item["quantity"] for item in totals.values()), Decimal(0)),
            "amount": sum((item["amount"] for item in totals.values()), Decimal(0)),
            "products": products,
        }

    def latest_data_date(self, stores: Iterable[str]) -> date | None:
        values = [row["latest_data_date"] for row in self.latest_data_dates(stores) if row["latest_data_date"]]
        return max(values) if values else None

    def latest_data_dates(self, stores: Iterable[str]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for key in stores:
            store = STORES[key]
            query = sql.SQL("SELECT MAX(transaction_date) AS value FROM {}.daily_sales").format(sql.Identifier(store.schema_name))
            value = self.conn.execute(query).fetchone()["value"]
            rows.append(
                {
                    "store_key": key,
                    "store_name": store.name,
                    "latest_data_date": value,
                    "source": f"{store.schema_name}.daily_sales",
                }
            )
        return rows


class CustomerRepository:
    def __init__(self, conn: Connection):
        self.conn = conn

    def _nickname_expression(self, store: Store) -> sql.Composed:
        if store.nickname_column:
            return sql.SQL("COALESCE((SELECT {} FROM {}.customer_id_mapping m WHERE m.customer_id = s.customer_id LIMIT 1), s.customer_id)").format(
                sql.Identifier(store.nickname_column), sql.Identifier(store.schema_name)
            )
        return sql.SQL("s.customer_id")

    def _health_columns(self, store: Store) -> sql.Composed:
        return sql.SQL("""
            (SELECT {} FROM {}.customer_health_detail h WHERE h.customer_id = s.customer_id AND h.period_start <= %s ORDER BY h.period_end DESC, h.updated_at DESC LIMIT 1) AS score,
            (SELECT customer_health_status FROM {}.customer_health_detail h WHERE h.customer_id = s.customer_id AND h.period_start <= %s ORDER BY h.period_end DESC, h.updated_at DESC LIMIT 1) AS status,
            (SELECT state_instructions FROM {}.customer_health_detail h WHERE h.customer_id = s.customer_id AND h.period_start <= %s ORDER BY h.period_end DESC, h.updated_at DESC LIMIT 1) AS risk_reason,
            (SELECT follow_up_action FROM {}.customer_health_detail h WHERE h.customer_id = s.customer_id AND h.period_start <= %s ORDER BY h.period_end DESC, h.updated_at DESC LIMIT 1) AS suggested_action
        """).format(
            sql.Identifier(store.health_score_column), sql.Identifier(store.schema_name),
            sql.Identifier(store.schema_name), sql.Identifier(store.schema_name), sql.Identifier(store.schema_name),
        )

    def _period_rows(self, store: Store, grain: Grain, window: PeriodWindow, as_of: date) -> list[dict[str, Any]]:
        table, start_col, end_col, amount_col, count_col = CUSTOMER_SPECS[grain]
        count_expression = sql.SQL("1") if count_col is None else sql.Identifier(count_col)
        query = sql.SQL("SELECT %s AS store_key, s.customer_id, {} AS display_name, s.{} AS period_amount, {} AS purchase_count, {} FROM {}.{} s WHERE ").format(
            self._nickname_expression(store), sql.Identifier(amount_col), count_expression,
            self._health_columns(store), sql.Identifier(store.schema_name), sql.Identifier(table)
        ) + _period_predicate(start_col, end_col)
        params: list[Any] = [store.key, as_of, as_of, as_of, as_of, *_period_params(window, end_col)]
        return list(self.conn.execute(query, params).fetchall())

    def list_page(
        self,
        stores: Iterable[str],
        grain: Grain,
        window: PeriodWindow,
        as_of: date,
        search: str | None,
        status: str | None,
        sort_by: str,
        sort_order: str,
        page: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = [row for key in stores for row in self._period_rows(STORES[key], grain, window, as_of)]
        if search:
            needle = search.strip().casefold()
            rows = [row for row in rows if needle in str(row["customer_id"]).casefold() or needle in str(row["display_name"] or "").casefold()]
        if status:
            rows = [row for row in rows if (row["status"] or "未评分") == status]
        sort_key = {
            "amount": "period_amount",
            "purchase_count": "purchase_count",
            "score": "score",
            "customer_id": "customer_id",
        }.get(sort_by, "period_amount")
        reverse = sort_order.lower() != "asc"
        rows.sort(key=lambda row: (row[sort_key] is not None, row[sort_key] or 0), reverse=reverse)
        total = len(rows)
        offset = (page - 1) * page_size
        return rows[offset:offset + page_size], total

    def get_customer(self, store_key: str, customer_id: str, as_of: date) -> dict[str, Any] | None:
        store = STORES[store_key]
        display_expr = sql.Identifier(store.nickname_column) if store.nickname_column else sql.SQL("customer_id")
        query = sql.SQL("SELECT customer_id, {} AS display_name FROM {}.customer_id_mapping WHERE customer_id = %s LIMIT 1").format(
            display_expr, sql.Identifier(store.schema_name)
        )
        base = self.conn.execute(query, (customer_id,)).fetchone()
        if not base:
            query = sql.SQL("SELECT customer_id, customer_id AS display_name FROM {}.customer_daily_sales WHERE customer_id = %s LIMIT 1").format(sql.Identifier(store.schema_name))
            base = self.conn.execute(query, (customer_id,)).fetchone()
        if not base:
            return None
        health_query = sql.SQL("""
            SELECT {} AS score, customer_health_status AS status, state_instructions AS risk_reason,
                   follow_up_action AS suggested_action, period_start, period_end
            FROM {}.customer_health_detail
            WHERE customer_id = %s AND period_start <= %s
            ORDER BY period_end DESC, updated_at DESC LIMIT 1
        """).format(sql.Identifier(store.health_score_column), sql.Identifier(store.schema_name))
        health = self.conn.execute(health_query, (customer_id, as_of)).fetchone() or {}
        return {"store_key": store_key, **base, **health}

    def customer_sales(self, store_key: str, customer_id: str, grain: Grain, window: PeriodWindow) -> dict[str, Any]:
        store = STORES[store_key]
        table, start_col, end_col, amount_col, count_col = CUSTOMER_SPECS[grain]
        count_expression = sql.SQL("COUNT(*)") if count_col is None else sql.SQL("COALESCE(SUM({}), 0)").format(sql.Identifier(count_col))
        query = sql.SQL("SELECT COALESCE(SUM({}), 0) AS amount, {}::bigint AS purchase_count FROM {}.{} WHERE customer_id = %s AND ").format(
            sql.Identifier(amount_col), count_expression, sql.Identifier(store.schema_name), sql.Identifier(table)
        ) + _period_predicate(start_col, end_col)
        return self.conn.execute(query, (customer_id, *_period_params(window, end_col))).fetchone()

    def customer_products(self, store_key: str, customer_id: str, grain: Grain, window: PeriodWindow, limit: int = 5) -> list[dict[str, Any]]:
        if grain not in CUSTOMER_PRODUCT_SPECS:
            return []
        store = STORES[store_key]
        table, start_col, end_col, amount_col, quantity_col = CUSTOMER_PRODUCT_SPECS[grain]
        query = sql.SQL("SELECT product_code, COALESCE(SUM({}), 0) AS amount, COALESCE(SUM({}), 0) AS quantity FROM {}.{} WHERE customer_id = %s AND ").format(
            sql.Identifier(amount_col), sql.Identifier(quantity_col), sql.Identifier(store.schema_name), sql.Identifier(table)
        ) + _period_predicate(start_col, end_col) + sql.SQL(" GROUP BY product_code ORDER BY SUM({}) DESC LIMIT %s").format(sql.Identifier(amount_col))
        return list(self.conn.execute(query, (customer_id, *_period_params(window, end_col), limit)).fetchall())


class SettingsRepository:
    def __init__(self, conn: Connection):
        self.conn = conn

    def health_rules(self, group_key: str) -> list[dict[str, Any]]:
        group = HEALTH_RULE_GROUPS[group_key]
        query = sql.SQL("""
            SELECT id, customer_health_status, state_instructions, follow_up_action,
                   created_time, updated_time
            FROM public.{}
        """).format(sql.Identifier(group.table_name))
        rows = list(self.conn.execute(query).fetchall())
        order = {status: index for index, status in enumerate(CUSTOMER_HEALTH_STATUSES)}
        rows.sort(key=lambda row: order.get(row["customer_health_status"], len(order)))
        return rows

    def update_health_rules(
        self,
        group_key: str,
        rules: list[dict[str, Any]],
        *,
        force_sync: bool = False,
    ) -> dict[str, Any]:
        group = HEALTH_RULE_GROUPS[group_key]
        current_rules = list(
            self.conn.execute(
                sql.SQL("""
                    SELECT customer_health_status, state_instructions, follow_up_action
                    FROM public.{}
                    FOR UPDATE
                """).format(sql.Identifier(group.table_name))
            ).fetchall()
        )
        changed_rules = rules if force_sync else _changed_health_rules(current_rules, rules)
        affected_rows = {
            f"{schema_name}.{table_name}": 0
            for schema_name, table_name in group.health_tables
        }
        if not changed_rules:
            return {
                "group_key": group.key,
                "group_name": group.name,
                "updated_rule_count": len(rules),
                "changed_rule_count": 0,
                "changed_statuses": [],
                "updated_health_rows": affected_rows,
            }

        upsert = sql.SQL("""
            INSERT INTO public.{} (customer_health_status, state_instructions, follow_up_action)
            VALUES (%s, %s, %s)
            ON CONFLICT (customer_health_status) DO UPDATE
            SET state_instructions = EXCLUDED.state_instructions,
                follow_up_action = EXCLUDED.follow_up_action,
                updated_time = CURRENT_TIMESTAMP
        """).format(sql.Identifier(group.table_name))
        for rule in changed_rules:
            self.conn.execute(
                upsert,
                (rule["customer_health_status"], rule["state_instructions"], rule["follow_up_action"]),
            )

        non_loss_rules = [rule for rule in changed_rules if rule["customer_health_status"] != "流失"]
        loss_rule = next((rule for rule in changed_rules if rule["customer_health_status"] == "流失"), None)
        for schema_name, table_name in group.health_tables:
            target = f"{schema_name}.{table_name}"
            if non_loss_rules:
                values = sql.SQL(", ").join(
                    sql.SQL("(%s::text, %s::text, %s::text)")
                    for _ in non_loss_rules
                )
                params = tuple(
                    value
                    for rule in non_loss_rules
                    for value in (
                        rule["customer_health_status"],
                        rule["state_instructions"],
                        rule["follow_up_action"],
                    )
                )
                update_non_loss = sql.SQL("""
                    UPDATE {}.{} AS health
                    SET state_instructions = rules.state_instructions,
                        follow_up_action = rules.follow_up_action,
                        updated_at = CURRENT_TIMESTAMP
                    FROM (VALUES {}) AS rules(customer_health_status, state_instructions, follow_up_action)
                    WHERE health.customer_health_status = rules.customer_health_status
                      AND health.customer_health_status <> '流失'
                      AND (
                          health.state_instructions IS DISTINCT FROM rules.state_instructions
                          OR health.follow_up_action IS DISTINCT FROM rules.follow_up_action
                      )
                """).format(sql.Identifier(schema_name), sql.Identifier(table_name), values)
                affected_rows[target] += self.conn.execute(update_non_loss, params).rowcount
            if loss_rule:
                update_loss = sql.SQL("""
                    UPDATE {}.{} AS health
                    SET state_instructions = %s,
                        follow_up_action = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE health.customer_health_status = '流失'
                      AND (
                          health.state_instructions IS DISTINCT FROM %s
                          OR health.follow_up_action IS DISTINCT FROM %s
                      )
                """).format(sql.Identifier(schema_name), sql.Identifier(table_name))
                loss_params = (
                    loss_rule["state_instructions"],
                    loss_rule["follow_up_action"],
                    loss_rule["state_instructions"],
                    loss_rule["follow_up_action"],
                )
                affected_rows[target] += self.conn.execute(update_loss, loss_params).rowcount
        return {
            "group_key": group.key,
            "group_name": group.name,
            "updated_rule_count": len(rules),
            "changed_rule_count": len(changed_rules),
            "changed_statuses": [rule["customer_health_status"] for rule in changed_rules],
            "updated_health_rows": affected_rows,
        }
