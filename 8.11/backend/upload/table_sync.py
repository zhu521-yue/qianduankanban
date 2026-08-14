from __future__ import annotations

from dataclasses import dataclass
from itertools import count
from typing import Sequence

from psycopg import Connection, sql


_TEMP_COUNTER = count(1)


@dataclass(frozen=True)
class TableChange:
    schema_name: str
    table_name: str
    before_rows: int
    after_rows: int
    inserted_rows: int
    updated_rows: int
    deleted_rows: int

    def as_dict(self) -> dict[str, int | str]:
        return {
            "schema_name": self.schema_name,
            "table_name": self.table_name,
            "before_rows": self.before_rows,
            "after_rows": self.after_rows,
            "inserted_rows": self.inserted_rows,
            "updated_rows": self.updated_rows,
            "deleted_rows": self.deleted_rows,
        }


def sync_table(
    conn: Connection,
    *,
    schema_name: str,
    table_name: str,
    key_columns: Sequence[str],
    value_columns: Sequence[str],
    expected_select: str,
    delete_scope_sql: str | None = None,
) -> TableChange:
    """Synchronize a derived table to a trusted internal SELECT.

    Existing ids and created_at values are preserved. updated_at changes only
    when at least one business value actually changes.
    """
    target = sql.Identifier(schema_name, table_name)
    temp_name = f"upload_expected_{next(_TEMP_COUNTER)}"
    temp = sql.Identifier(temp_name)
    keys = tuple(key_columns)
    values = tuple(value_columns)
    all_columns = (*keys, *values)
    key_join = sql.SQL(" AND ").join(
        sql.SQL("target.{0} = expected.{0}").format(sql.Identifier(column))
        for column in keys
    )
    key_is_null = sql.SQL(" OR ").join(
        sql.SQL("{} IS NULL").format(sql.Identifier(column)) for column in keys
    )
    distinct_values = sql.SQL("ROW({}) IS DISTINCT FROM ROW({})").format(
        sql.SQL(", ").join(
            sql.SQL("target.{}").format(sql.Identifier(column)) for column in values
        ),
        sql.SQL(", ").join(
            sql.SQL("expected.{}").format(sql.Identifier(column)) for column in values
        ),
    )
    before_rows = conn.execute(
        sql.SQL("SELECT COUNT(*)::bigint AS count FROM {}").format(target)
    ).fetchone()["count"]
    conn.execute(
        sql.SQL("CREATE TEMP TABLE {} ON COMMIT DROP AS ").format(temp)
        + sql.SQL(expected_select)
    )

    invalid_keys = conn.execute(
        sql.SQL("SELECT COUNT(*)::bigint AS count FROM {} WHERE ").format(temp)
        + key_is_null
    ).fetchone()["count"]
    if invalid_keys:
        raise ValueError(
            f"{schema_name}.{table_name}期望结果存在{invalid_keys}条空业务键"
        )

    duplicate_keys = conn.execute(
        sql.SQL(
            "SELECT COALESCE(SUM(count - 1), 0)::bigint AS count FROM ("
            "SELECT COUNT(*)::bigint AS count FROM {} GROUP BY {} HAVING COUNT(*) > 1"
            ") duplicate_groups"
        ).format(
            temp,
            sql.SQL(", ").join(sql.Identifier(column) for column in keys),
        )
    ).fetchone()["count"]
    if duplicate_keys:
        raise ValueError(
            f"{schema_name}.{table_name}期望结果存在{duplicate_keys}条重复业务键"
        )
    conn.execute(
        sql.SQL("CREATE UNIQUE INDEX ON {} ({})").format(
            temp,
            sql.SQL(", ").join(sql.Identifier(column) for column in keys),
        )
    )
    conn.execute(sql.SQL("ANALYZE {}").format(temp))

    delete_scope = (
        sql.SQL("({}) AND ").format(sql.SQL(delete_scope_sql))
        if delete_scope_sql
        else sql.SQL("")
    )
    deleted_rows = conn.execute(
        sql.SQL(
            "DELETE FROM {} target WHERE {}NOT EXISTS "
            "(SELECT 1 FROM {} expected WHERE {})"
        ).format(target, delete_scope, temp, key_join)
    ).rowcount

    assignments = [
        sql.SQL("{0} = EXCLUDED.{0}").format(sql.Identifier(column))
        for column in values
    ]
    assignments.append(sql.SQL("updated_at = CURRENT_TIMESTAMP"))
    excluded_distinct = sql.SQL("ROW({}) IS DISTINCT FROM ROW({})").format(
        sql.SQL(", ").join(
            sql.SQL("target.{}").format(sql.Identifier(column)) for column in values
        ),
        sql.SQL(", ").join(
            sql.SQL("EXCLUDED.{}").format(sql.Identifier(column)) for column in values
        ),
    )
    upsert_counts = conn.execute(
        sql.SQL(
            "WITH changed AS ("
            "INSERT INTO {} AS target ({}) SELECT {} FROM {} "
            "ON CONFLICT ({}) DO UPDATE SET {} WHERE {} "
            "RETURNING xmax = 0 AS inserted"
            ") SELECT COUNT(*) FILTER (WHERE inserted)::bigint AS inserted_rows, "
            "COUNT(*) FILTER (WHERE NOT inserted)::bigint AS updated_rows FROM changed"
        ).format(
            target,
            sql.SQL(", ").join(sql.Identifier(column) for column in all_columns),
            sql.SQL(", ").join(sql.Identifier(column) for column in all_columns),
            temp,
            sql.SQL(", ").join(sql.Identifier(column) for column in keys),
            sql.SQL(", ").join(assignments),
            excluded_distinct,
        )
    ).fetchone()
    inserted_rows = upsert_counts["inserted_rows"]
    updated_rows = upsert_counts["updated_rows"]
    after_rows = before_rows + inserted_rows - deleted_rows
    return TableChange(
        schema_name=schema_name,
        table_name=table_name,
        before_rows=before_rows,
        after_rows=after_rows,
        inserted_rows=inserted_rows,
        updated_rows=updated_rows,
        deleted_rows=deleted_rows,
    )
