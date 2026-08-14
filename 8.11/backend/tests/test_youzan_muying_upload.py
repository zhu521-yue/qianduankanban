from datetime import date
from decimal import Decimal

from upload.business_preview import aggregate_refresh_tables
from upload.models import PreparedRow
from upload.youzan_muying.config import CONFIG
from upload.youzan_muying.preview import classify_rows


def test_muying_upload_uses_confirmed_file_rules_and_atomic_refresh():
    assert CONFIG.transaction_time_column == "订单创建时间"
    assert CONFIG.ignored_upload_columns == ("分销商商品推广补差",)
    assert CONFIG.existing_date_policy == "skip"
    assert CONFIG.commit_enabled is True
    assert CONFIG.aggregate_path == ("youzan", "siyu", "qudao")
    assert len(CONFIG.downstream_tables) == 33


def test_muying_preview_uses_confirmed_status_gross_sales_and_refund_rules():
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
            date(2026, 7, 28),
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
            date(2026, 7, 28),
            "source_row=3",
            "closed",
        ),
        PreparedRow(
            4,
            {
                "订单状态": "已发货",
                "商品单价": "30",
                "商品数量": "3",
                "商品已退款金额": "0",
                "销售渠道": "网店",
                "买家昵称": "客户丙",
                "规格编码": "SKU-3",
            },
            date(2026, 7, 28),
            "source_row=4",
            "shipped",
        ),
        PreparedRow(
            5,
            {
                "订单状态": "待付款",
                "商品单价": "999",
                "商品数量": "1",
                "商品已退款金额": "5",
                "销售渠道": "网店",
                "买家昵称": "客户丁",
                "规格编码": "SKU-4",
            },
            date(2026, 7, 28),
            "source_row=5",
            "excluded",
        ),
    ]

    sales, refunds, summary = classify_rows(rows)

    assert sales[date(2026, 7, 28)] == Decimal("149.99")
    assert refunds[date(2026, 7, 28)] == Decimal("35.00")
    assert summary["valid_sales_rows"] == 3
    assert summary["excluded_sales_status_rows"] == 1
    assert summary["refund_rows"] == 3
    assert summary["sales_with_refund_rows"] == 2
    assert summary["refund_only_rows"] == 1
    assert summary["gross_sales_amount"] == "149.99"
    assert summary["refund_amount"] == "35.00"
    assert summary["valid_customer_rows"] == 3
    assert summary["valid_product_rows"] == 3


def test_muying_upload_lists_every_upper_refresh_table():
    refresh = aggregate_refresh_tables(CONFIG.aggregate_path)

    assert len(refresh["youzan"]) == 11
    assert "half_year_product_frequency" in refresh["youzan"]
    assert len(refresh["siyu"]) == 11
    assert "half_year_high_frequency_products" in refresh["siyu"]
    assert len(refresh["qudao"]) == 9
