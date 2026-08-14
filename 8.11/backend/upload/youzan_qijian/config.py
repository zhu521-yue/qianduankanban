from upload.config_helpers import STORE_TABLES, aggregate_path, simple_customer
from upload.models import StoreUploadConfig
from upload.youzan_muying.preview import build_preview


CONFIG = StoreUploadConfig(
    store_key="youzan_qijian",
    schema_name="qijian",
    transaction_time_column="订单创建时间",
    customer_resolver=simple_customer("买家昵称", required_values={"销售渠道": "网店"}),
    customer_mapping_columns=("customer_id",),
    downstream_tables=STORE_TABLES,
    aggregate_path=aggregate_path("private", "youzan"),
    business_preview_builder=build_preview,
    commit_enabled=True,
)
