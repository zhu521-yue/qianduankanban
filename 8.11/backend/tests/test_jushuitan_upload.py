from datetime import date
from decimal import Decimal

from upload.config_helpers import jushuitan_customer
from upload.jushuitan.config import CONFIG
from upload.jushuitan.preview import classify_rows
from upload.models import PreparedRow


def test_jushuitan_config_uses_payment_date_skip_and_ignores_virtual_category():
    assert CONFIG.transaction_time_column == "付款日期"
    assert CONFIG.existing_date_policy == "skip"
    assert CONFIG.commit_enabled is True
    assert CONFIG.ignored_upload_columns == ("虚拟分类",)


def test_jushuitan_customer_conversion_priority():
    assert jushuitan_customer({"分销商": " 甲分销商 ", "店铺": "拼多多童鞋店"}) == {
        "customer_id": "甲分销商"
    }
    assert jushuitan_customer({"分销商": "", "店铺": "拼多多童鞋店"}) == {
        "customer_id": "童鞋"
    }
    assert jushuitan_customer({"分销商": "", "店铺": "晨秋小店"}) == {
        "customer_id": "晨秋"
    }
    assert jushuitan_customer({"分销商": "", "店铺": "老爸评测旗舰店"}) == {
        "customer_id": "老爸评测"
    }
    assert jushuitan_customer({"分销商": "", "店铺": "京东商城旗舰店"}) == {
        "customer_id": "戎井"
    }
    assert jushuitan_customer({"分销商": "", "店铺": "自营店"}) == {
        "customer_id": "自营店"
    }


def test_jushuitan_preview_uses_confirmed_sales_and_refund_formulas():
    rows = [
        PreparedRow(
            2,
            {
                "订单状态": "已发货",
                "销售数量": "2",
                "销售金额": "19.995",
                "实退数量": "1",
                "实退金额": "9.995",
                "分销商": "",
                "店铺": "拼多多童鞋店",
                "商品编码": "SKU-1",
            },
            date(2026, 7, 28),
            "source_row=2",
            "hash",
        ),
        PreparedRow(
            3,
            {
                "订单状态": "已取消",
                "销售数量": "9",
                "销售金额": "99.00",
                "实退数量": "9",
                "实退金额": "99.00",
                "分销商": "取消订单客户",
                "店铺": "取消订单店铺",
                "商品编码": "SKU-CANCELLED",
            },
            date(2026, 7, 28),
            "source_row=3",
            "cancelled-hash",
        ),
    ]

    sales, refunds, summary = classify_rows(rows)

    assert sales[date(2026, 7, 28)] == Decimal("39.99")
    assert refunds[date(2026, 7, 28)] == Decimal("10.00")
    assert summary["valid_sales_rows"] == 1
    assert summary["refund_rows"] == 1
    assert summary["valid_customer_rows"] == 1
    assert summary["valid_product_rows"] == 1
    assert summary["gross_sales_amount"] == "39.99"
    assert summary["refund_amount"] == "10.00"
    assert summary["gross_product_quantity"] == "2"
