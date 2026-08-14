from __future__ import annotations

from psycopg import Connection

from upload.doudian_kocotree.refresh import refresh_store_for_schema
from upload.table_sync import TableChange


SCHEMA = "doudianChildren"


def refresh_store(conn: Connection) -> list[TableChange]:
    """Refresh all 33 derived tables for the Doudian children store."""
    return refresh_store_for_schema(conn, SCHEMA)
