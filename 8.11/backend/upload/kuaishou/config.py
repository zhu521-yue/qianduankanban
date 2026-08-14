from upload.config_helpers import STORE_TABLES, aggregate_path, first_available_customer
from upload.kuaishou.preview import build_preview
from upload.models import StoreUploadConfig


CONFIG = StoreUploadConfig(
    store_key="kuaishou",
    schema_name="kuaishouxiaodian",
    transaction_time_column="订单创建时间",
    customer_resolver=first_available_customer(
        (("CPS达人ID", "CPS达人昵称"), ("团长ID", "团长昵称"), ("快赚客ID", "快赚客昵称")),
        required_values={"渠道": "分销"},
    ),
    customer_mapping_columns=("customer_id", "customer_nickname"),
    downstream_tables=STORE_TABLES,
    aggregate_path=aggregate_path("talent", "kuaishou"),
    business_preview_builder=build_preview,
    commit_enabled=True,
    existing_date_policy="replace",
)
