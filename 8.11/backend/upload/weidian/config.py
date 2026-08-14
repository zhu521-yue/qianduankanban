from upload.config_helpers import STORE_TABLES, aggregate_path, value
from upload.models import StoreUploadConfig
from upload.normalization import normalize_customer_id
from upload.weidian.preview import build_preview


def resolve_customer(row):
    customer_id = normalize_customer_id(row.get("带货ID"))
    if customer_id in {"", "-", "0", "0.0"}:
        return None
    return {
        "customer_id": customer_id,
        "affiliate_id": customer_id,
        "affiliate_nickname": value(row, "带货账号昵称"),
    }


CONFIG = StoreUploadConfig(
    store_key="weidian",
    schema_name="weidian",
    transaction_time_column="支付时间",
    customer_resolver=resolve_customer,
    customer_mapping_columns=("customer_id", "affiliate_id", "affiliate_nickname"),
    downstream_tables=STORE_TABLES + ("monthly_product_presales", "quarterly_product_presales", "half_year_product_presales"),
    aggregate_path=aggregate_path("talent", "weidian"),
    business_preview_builder=build_preview,
    commit_enabled=True,
)
