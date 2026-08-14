from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from upload.business_preview import aggregate_refresh_tables
from upload.models import PreparedRow
from upload.youzan_qijian.config import CONFIG
from upload.youzan_qijian import committer
from upload.youzan_muying.preview import classify_rows


def test_qijian_upload_uses_confirmed_file_rules_and_atomic_refresh():
    assert CONFIG.store_key == "youzan_qijian"
    assert CONFIG.schema_name == "qijian"
    assert CONFIG.transaction_time_column == "订单创建时间"
    assert CONFIG.ignored_upload_columns == ()
    assert CONFIG.existing_date_policy == "skip"
    assert CONFIG.commit_enabled is True
    assert CONFIG.aggregate_path == ("youzan", "siyu", "qudao")
    assert len(CONFIG.downstream_tables) == 33


def test_qijian_preview_uses_youzan_sales_and_refund_rules():
    rows = [
        PreparedRow(
            2,
            {
                "订单状态": "已完成",
                "商品单价": "19.995",
                "商品数量": "2",
                "商品已退款金额": "10",
                "销售渠道": "网店",
                "买家昵称": "客户甲",
                "规格编码": "SKU-1",
            },
            date(2026, 7, 27),
            "source_row=2",
            "completed",
        ),
        PreparedRow(
            3,
            {
                "订单状态": "已关闭",
                "商品单价": "20",
                "商品数量": "1",
                "商品已退款金额": "20",
                "销售渠道": "网店",
                "买家昵称": "客户乙",
                "规格编码": "SKU-2",
            },
            date(2026, 7, 27),
            "source_row=3",
            "closed",
        ),
    ]

    sales, refunds, summary = classify_rows(rows)

    assert sales[date(2026, 7, 27)] == Decimal("59.99")
    assert refunds[date(2026, 7, 27)] == Decimal("30.00")
    assert summary["valid_sales_rows"] == 2
    assert summary["refund_rows"] == 2
    assert summary["valid_customer_rows"] == 2
    assert summary["valid_product_rows"] == 2


def test_qijian_upload_lists_every_upper_refresh_table():
    refresh = aggregate_refresh_tables(CONFIG.aggregate_path)

    assert len(refresh["youzan"]) == 11
    assert len(refresh["siyu"]) == 11
    assert len(refresh["qudao"]) == 9


def test_qijian_existing_date_upload_does_not_refresh_64_tables(monkeypatch):
    monkeypatch.setattr(
        committer,
        "apply_base_changes",
        lambda conn, config, analysis: {
            "raw_deleted": 0,
            "raw_inserted": 0,
            "raw_updated": 0,
            "customers_inserted": 0,
        },
    )

    result = committer.commit_upload(
        None,
        CONFIG,
        SimpleNamespace(affected_dates=set()),
    )

    assert result["store_tables_refreshed"] == 0
    assert result["aggregate_tables_refreshed"] == 0
    assert result["table_changes"] == []
