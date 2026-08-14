from upload.config_helpers import STORE_TABLES, aggregate_path, jushuitan_customer
from upload.jushuitan.preview import build_preview
from upload.models import StoreUploadConfig


CONFIG = StoreUploadConfig(
    store_key="jushuitan",
    schema_name="jushuitan",
    transaction_time_column="付款日期",
    customer_resolver=jushuitan_customer,
    customer_mapping_columns=("customer_id",),
    downstream_tables=STORE_TABLES,
    aggregate_path=aggregate_path("distribution", "jushuitan"),
    required_upload_columns=(
        "订单状态",
        "销售数量",
        "销售金额",
        "实退数量",
        "退货金额",
        "商品编码",
        "分销商",
        "店铺",
    ),
    date_year_replacements=((2525, 2025), (2024, 2026)),
    business_preview_builder=build_preview,
    commit_enabled=True,
    ignored_upload_columns=("虚拟分类",),
)
