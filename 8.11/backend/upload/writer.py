from __future__ import annotations

from app.responses import ApiError
from upload.models import StoreUploadConfig, UploadAnalysis
from upload.repository import UploadRepository


def apply_base_changes(conn, config: StoreUploadConfig, analysis: UploadAnalysis) -> dict[str, int]:
    """Write raw rows and customer mappings inside the caller-owned transaction.

    This function deliberately never commits.  The caller must run every store,
    platform, group and channel refresher plus validations before committing the
    same transaction.
    """
    repo = UploadRepository(conn, config)
    repo.lock_store_upload()
    try:
        deleted, inserted, updated = repo.write_raw_changes(analysis)
        customers = repo.insert_missing_customers(analysis.missing_customers)
    except ValueError as exc:
        raise ApiError(409, "UPLOAD_WRITE_CONFLICT", str(exc)) from exc
    return {
        "raw_deleted": deleted,
        "raw_inserted": inserted,
        "raw_updated": updated,
        "customers_inserted": customers,
    }
