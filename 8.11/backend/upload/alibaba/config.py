from upload.config_helpers import STORE_TABLES, aggregate_path, value
from upload.models import StoreUploadConfig
from upload.normalization import normalize_customer_id
from upload.alibaba.preview import build_preview


def resolve_customer(row):
    customer_id = normalize_customer_id(row.get("买家ID"))
    if customer_id in {"", "-", "0", "0.0"}:
        return None
    return {"customer_id": customer_id, "buyer_id": customer_id, "buyer_nickname": value(row, "买家账号")}


CONFIG = StoreUploadConfig(
    store_key="alibaba",
    schema_name="alibaba",
    transaction_time_column="付款日期",
    customer_resolver=resolve_customer,
    customer_mapping_columns=("customer_id", "buyer_id", "buyer_nickname"),
    downstream_tables=STORE_TABLES,
    aggregate_path=aggregate_path("distribution", "alibaba"),
    required_upload_columns=(
        "订单状态",
        "销售金额",
        "退货金额",
        "实发数量",
        "实退数量",
        "商品编码",
        "买家ID",
        "买家账号",
    ),
    business_preview_builder=build_preview,
    commit_enabled=True,
    existing_date_policy="skip",
    ignored_upload_columns=("虚拟分类",),
)
