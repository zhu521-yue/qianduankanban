from upload.config_helpers import (
    DOUDIAN_MIXED_SALES_RULES,
    STORE_TABLES,
    aggregate_path,
    simple_customer,
)
from upload.models import StoreUploadConfig


CONFIG = StoreUploadConfig(
    store_key="doudian_children",
    schema_name="doudianChildren",
    transaction_time_column="支付完成时间",
    customer_resolver=simple_customer("达人ID", "达人昵称", required_values={"流量来源": "精选联盟"}),
    customer_mapping_columns=("customer_id", "customer_nickname"),
    downstream_tables=STORE_TABLES,
    aggregate_path=aggregate_path("talent", "doudian"),
    required_upload_columns=(
        "订单应付金额",
        "订单状态",
        "售后状态",
        "商品数量",
        "商家编码",
        "达人ID",
        "达人昵称",
        "流量来源",
    ),
    mixed_sales_rules=DOUDIAN_MIXED_SALES_RULES,
    commit_enabled=True,
    existing_date_policy="replace",
)
