from upload.config_helpers import STORE_TABLES, aggregate_path, simple_customer
from upload.models import StoreUploadConfig
from upload.kuaituantuan.preview import build_preview


CONFIG = StoreUploadConfig(
    store_key="kuaituantuan",
    schema_name="kuaituantuan",
    transaction_time_column="创单时间",
    customer_resolver=simple_customer("团长"),
    customer_mapping_columns=("customer_id",),
    downstream_tables=STORE_TABLES,
    aggregate_path=aggregate_path("private", "kuaituantuan"),
    required_upload_columns=(
        "子订单号",
        "商品编码",
        "数量",
        "商品金额",
        "已退款+退款中",
        "团长",
    ),
    commit_enabled=True,
    existing_date_policy="upsert",
    row_key_columns=("子订单号", "商品编码"),
    analysis_preview_builder=build_preview,
)
