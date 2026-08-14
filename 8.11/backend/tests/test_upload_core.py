from datetime import date
from decimal import Decimal

import pytest

from app.responses import ApiError
from upload.business_preview import _classify_file_rows, aggregate_refresh_tables
from upload.weidian.preview import classify_rows as classify_weidian_rows
from upload.alibaba.preview import build_preview as build_alibaba_preview
from upload.alibaba.preview import classify_rows as classify_alibaba_rows
from upload.config_helpers import (
    DOUDIAN_MIXED_SALES_RULES,
    first_available_customer,
    jushuitan_customer,
    simple_customer,
)
from upload.models import ComparedRow, ParsedFile, PreparedRow, StoreUploadConfig, UploadAnalysis
from upload.normalization import (
    database_value,
    find_order_key_columns,
    make_business_key,
    normalized_business_date,
    text_value,
)
from upload.pipeline import _deduplicate, analyse_upload, analysis_payload
from upload.periods import half_year_bounds, quarter_bounds, week_bounds
from upload.repository import UploadRepository
from upload.kuaituantuan.config import CONFIG as KUAITUANTUAN_CONFIG


def test_joint_order_key_uses_every_matching_header_in_order():
    headers = ("商品", "主订单编号", "订单号", "活动订单编号")
    columns = find_order_key_columns(headers)
    assert columns == ("主订单编号", "订单号", "活动订单编号")
    assert make_business_key(
        {"主订单编号": "A", "订单号": 12.0, "活动订单编号": None}, columns
    ) == "主订单编号=A|订单号=12|活动订单编号="


def test_joint_order_key_rejects_all_blank_values():
    with pytest.raises(ValueError, match="均为空"):
        make_business_key({"订单号": "-"}, ("订单号",))


def test_database_value_matches_existing_loader_formats():
    assert database_value("¥1,299.00", "numeric") == "1299"
    assert database_value("20.0%", "numeric") == "0.2"
    assert database_value("-", "text") is None
    assert text_value("第一行\r\n第二行") == "第一行\n第二行"


def test_jushuitan_year_correction_only_changes_business_date():
    assert normalized_business_date("2525-02-03 12:00:00", ((2525, 2025), (2024, 2026))) == date(2025, 2, 3)
    assert normalized_business_date("2024-07-28 12:00:00", ((2525, 2025), (2024, 2026))) == date(2026, 7, 28)


def test_custom_period_boundaries():
    assert week_bounds(date(2026, 8, 13)) == (date(2026, 8, 10), date(2026, 8, 16))
    assert quarter_bounds(date(2026, 1, 1)) == (date(2025, 11, 1), date(2026, 1, 31))
    assert half_year_bounds(date(2026, 1, 1)) == (date(2025, 8, 1), date(2026, 1, 31))


def test_customer_resolution_rules():
    doudian = simple_customer("达人ID", "达人昵称", required_values={"流量来源": "精选联盟"})
    assert doudian({"流量来源": "商城", "达人ID": "1", "达人昵称": "A"}) is None
    assert doudian({"流量来源": "精选联盟", "达人ID": 1.0, "达人昵称": "A"}) == {
        "customer_id": "1",
        "customer_nickname": "A",
    }

    kuaishou = first_available_customer(
        (("CPS达人ID", "CPS达人昵称"), ("团长ID", "团长昵称"), ("快赚客ID", "快赚客昵称")),
        required_values={"渠道": "分销"},
    )
    assert kuaishou({"渠道": "分销", "CPS达人ID": "0", "团长ID": "-", "快赚客ID": "3", "快赚客昵称": "K"}) == {
        "customer_id": "3",
        "customer_nickname": "K",
    }

    assert jushuitan_customer({"分销商": "", "店铺": "京东商城旗舰店"}) == {"customer_id": "戎井"}


def test_file_dedup_ignores_identical_rows_and_uses_last_changed_row():
    analysis = UploadAnalysis(
        store_key="test",
        schema_name="test",
        headers=("订单号", "金额"),
        order_key_columns=("订单号",),
    )
    prepared = [
        PreparedRow(2, {"订单号": "A", "金额": "10"}, date(2026, 8, 13), "订单号=A", "hash-10"),
        PreparedRow(3, {"订单号": "A", "金额": "10"}, date(2026, 8, 13), "订单号=A", "hash-10"),
        PreparedRow(4, {"订单号": "A", "金额": "20"}, date(2026, 8, 13), "订单号=A", "hash-20"),
    ]

    result = _deduplicate(prepared, analysis)

    assert result == [prepared[-1]]
    assert analysis.duplicate_identical_rows == 1
    assert analysis.same_key_updated_rows == 1


def test_upload_rejects_missing_required_business_columns(monkeypatch):
    class FakeRepository:
        def __init__(self, conn, config):
            self.config = config

        def raw_column_types(self):
            return {
                "交易日期": "text",
                "订单状态": "text",
                "金额": "numeric",
            }

    parsed = ParsedFile(
        headers=("交易日期", "订单状态"),
        rows=({"交易日期": "2026-08-13", "订单状态": "已完成"},),
    )
    config = StoreUploadConfig(
        store_key="test",
        schema_name="test",
        transaction_time_column="交易日期",
        customer_resolver=lambda row: None,
        customer_mapping_columns=(),
        downstream_tables=(),
        aggregate_path=(),
        required_upload_columns=("订单状态", "金额"),
    )
    monkeypatch.setattr("upload.pipeline.read_file", lambda *args: parsed)
    monkeypatch.setattr("upload.pipeline.UploadRepository", FakeRepository)

    with pytest.raises(ApiError) as captured:
        analyse_upload(None, config, "sales.csv", b"unused")

    assert captured.value.code == "UPLOAD_REQUIRED_COLUMN_MISSING"
    assert "金额" in captured.value.message


def test_every_store_declares_required_upload_columns():
    from upload.registry import CONFIGS

    assert set(CONFIGS) == {
        "weidian",
        "doudian_children",
        "doudian_kocotree",
        "kuaishou",
        "youzan_qijian",
        "youzan_muying",
        "kuaituantuan",
        "alibaba",
        "jushuitan",
    }
    assert all(config.required_upload_columns for config in CONFIGS.values())


def test_sales_upload_replaces_existing_dates_without_order_key_dedup(monkeypatch):
    class FakeRepository:
        def __init__(self, conn, config):
            self.config = config

        def raw_column_types(self):
            return {
                "交易日期": "text",
                "订单号": "text",
                "商品": "text",
                "客户": "text",
            }

        def existing_dates(self, dates):
            assert dates == {date(2026, 8, 12), date(2026, 8, 13)}
            return {date(2026, 8, 12)}

        def raw_row_counts_by_date(self, dates):
            assert dates == {date(2026, 8, 12)}
            return {date(2026, 8, 12): 7}

        def existing_customer_ids(self, customer_ids):
            return set()

        def rows_by_keys(self, *args, **kwargs):
            raise AssertionError("date replacement must not query ambiguous order keys")

    parsed = ParsedFile(
        headers=("交易日期", "订单号", "商品", "客户"),
        rows=(
            {"交易日期": "2026-08-12", "订单号": "A", "商品": "SKU-1", "客户": "C1"},
            {"交易日期": "2026-08-12", "订单号": "A", "商品": "SKU-2", "客户": "C1"},
            {"交易日期": "2026-08-13", "订单号": "B", "商品": "SKU-3", "客户": "C2"},
            {"交易日期": "", "订单号": "C", "商品": "SKU-4", "客户": "C3"},
        ),
    )
    config = StoreUploadConfig(
        store_key="test",
        schema_name="test",
        transaction_time_column="交易日期",
        customer_resolver=lambda row: {"customer_id": row["客户"]} if row.get("客户") else None,
        customer_mapping_columns=("customer_id",),
        downstream_tables=("daily_sales",),
        aggregate_path=(),
        existing_date_policy="replace",
    )
    monkeypatch.setattr("upload.pipeline.read_file", lambda *args: parsed)
    monkeypatch.setattr("upload.pipeline.UploadRepository", FakeRepository)

    analysis = analyse_upload(None, config, "sales.csv", b"unused")
    payload = analysis_payload(analysis)

    assert len(analysis.compared_rows) == 3
    assert [item.prepared.values["商品"] for item in analysis.compared_rows] == [
        "SKU-1",
        "SKU-2",
        "SKU-3",
    ]
    assert analysis.excluded_undated_rows == 1
    assert payload["upload_strategy"] == "replace_existing_dates"
    assert payload["dates"]["replacement"] == ["2026-08-12"]
    assert payload["dates"]["new"] == ["2026-08-13"]
    assert payload["replacement_date_rows"] == 2
    assert payload["new_date_rows"] == 1
    assert payload["rows_to_delete"] == 7
    assert payload["rows_to_insert"] == 3
    assert payload["update_rows"] == 0
    assert payload["unchanged_rows"] == 0


def test_kuaituantuan_uses_created_time_and_product_detail_upsert(monkeypatch):
    class FakeRepository:
        def __init__(self, conn, config):
            self.config = config

        def raw_column_types(self):
            return {
                "创单时间": "text",
                "子订单号": "text",
                "商品编码": "text",
                "团长": "text",
                "数量": "text",
                "商品金额": "text",
                "已退款+退款中": "text",
            }

        def existing_dates(self, dates):
            return {date(2026, 7, 27)}

        def raw_row_counts_by_date(self, dates):
            return {date(2026, 7, 27): 100}

        def rows_by_keys(self, key_columns, prepared, *args):
            assert key_columns == ("子订单号", "商品编码")
            return {
                prepared[0].business_key: {
                    "id": 1,
                    "hash": prepared[0].row_hash,
                    "values": prepared[0].values,
                    "business_date": date(2026, 7, 27),
                },
                prepared[1].business_key: {
                    "id": 2,
                    "hash": "old-hash",
                    "values": {**prepared[1].values, "已退款+退款中": "0"},
                    "business_date": date(2026, 7, 27),
                },
            }

        def existing_customer_ids(self, customer_ids):
            return {"团长A"}

    parsed = ParsedFile(
        headers=("创单时间", "子订单号", "商品编码", "团长", "数量", "商品金额", "已退款+退款中"),
        rows=(
            {"创单时间": "2026-07-27 10:00:00", "子订单号": "A", "商品编码": "SKU-1", "团长": "团长A", "数量": "1", "商品金额": "10", "已退款+退款中": "0"},
            {"创单时间": "2026-07-27 10:00:00", "子订单号": "B", "商品编码": "SKU-2", "团长": "团长A", "数量": "1", "商品金额": "20", "已退款+退款中": "5"},
            {"创单时间": "2026-07-27 10:00:00", "子订单号": "C", "商品编码": "SKU-3", "团长": "团长B", "数量": "2", "商品金额": "30", "已退款+退款中": "0"},
        ),
    )
    config = StoreUploadConfig(
        store_key="kuaituantuan",
        schema_name="kuaituantuan",
        transaction_time_column="创单时间",
        customer_resolver=simple_customer("团长"),
        customer_mapping_columns=("customer_id",),
        downstream_tables=("daily_sales",),
        aggregate_path=(),
        existing_date_policy="upsert",
        row_key_columns=("子订单号", "商品编码"),
    )
    monkeypatch.setattr("upload.pipeline.read_file", lambda *args: parsed)
    monkeypatch.setattr("upload.pipeline.UploadRepository", FakeRepository)

    analysis = analyse_upload(None, config, "7.27.xlsx", b"unused")
    payload = analysis_payload(analysis)

    assert [item.action for item in analysis.compared_rows] == ["unchanged", "update", "insert"]
    assert payload["upload_strategy"] == "upsert_business_keys"
    assert payload["order_key_columns"] == ["子订单号", "商品编码"]
    assert payload["insert_rows"] == 1
    assert payload["update_rows"] == 1
    assert payload["unchanged_rows"] == 1
    assert payload["rows_to_delete"] == 0
    assert payload["dates"]["file"] == ["2026-07-27"]
    assert payload["new_customer_rows"] == 1


def test_kuaituantuan_registered_config_matches_confirmed_business_date():
    assert KUAITUANTUAN_CONFIG.transaction_time_column == "创单时间"
    assert KUAITUANTUAN_CONFIG.existing_date_policy == "upsert"
    assert KUAITUANTUAN_CONFIG.row_key_columns == ("子订单号", "商品编码")
    assert KUAITUANTUAN_CONFIG.aggregate_path == ("siyu", "qudao")
    assert KUAITUANTUAN_CONFIG.commit_enabled is True


def test_sales_writer_deletes_existing_date_before_inserting_snapshot():
    class Cursor:
        rowcount = 7

    class FakeConnection:
        def __init__(self):
            self.calls = []

        def execute(self, query, params):
            self.calls.append(("execute", params))
            return Cursor()

        def cursor(self):
            connection = self

            class FakeCursor:
                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return None

                def executemany(self, query, params):
                    connection.calls.append(("executemany", list(params)))

            return FakeCursor()

    config = StoreUploadConfig(
        store_key="test",
        schema_name="test",
        transaction_time_column="交易日期",
        customer_resolver=lambda row: None,
        customer_mapping_columns=("customer_id",),
        downstream_tables=(),
        aggregate_path=(),
        existing_date_policy="replace",
    )
    prepared = PreparedRow(
        source_row=2,
        values={"交易日期": "2026-08-12", "订单号": "A"},
        business_date=date(2026, 8, 12),
        business_key="source_row=2",
        row_hash="hash",
    )
    analysis = UploadAnalysis(
        store_key="test",
        schema_name="test",
        headers=("交易日期", "订单号"),
        order_key_columns=("订单号",),
        existing_dates={date(2026, 8, 12)},
        compared_rows=[ComparedRow(prepared, "insert")],
        existing_date_policy="replace",
    )
    conn = FakeConnection()

    result = UploadRepository(conn, config).write_raw_changes(analysis)

    assert result == (7, 1, 0)
    assert [call[0] for call in conn.calls] == ["execute", "executemany"]
    assert conn.calls[0][1] == ([date(2026, 8, 12)],)
    assert conn.calls[1][1] == [("2026-08-12", "A")]


def test_keyed_upsert_rechecks_once_and_writes_in_batches(monkeypatch):
    class FakeConnection:
        def __init__(self):
            self.batches = []

        def cursor(self):
            connection = self

            class FakeCursor:
                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return None

                def executemany(self, query, params):
                    connection.batches.append(list(params))

            return FakeCursor()

    config = StoreUploadConfig(
        store_key="kuaituantuan",
        schema_name="kuaituantuan",
        transaction_time_column="创单时间",
        customer_resolver=lambda row: None,
        customer_mapping_columns=("customer_id",),
        downstream_tables=(),
        aggregate_path=(),
        existing_date_policy="upsert",
        row_key_columns=("子订单号", "商品编码"),
    )
    insert = PreparedRow(
        2,
        {"子订单号": "A", "商品编码": "SKU-1", "数量": "1"},
        date(2026, 7, 28),
        "子订单号=A|商品编码=SKU-1",
        "insert-hash",
    )
    update = PreparedRow(
        3,
        {"子订单号": "B", "商品编码": "SKU-2", "数量": "2"},
        date(2026, 7, 28),
        "子订单号=B|商品编码=SKU-2",
        "update-hash",
    )
    analysis = UploadAnalysis(
        store_key="kuaituantuan",
        schema_name="kuaituantuan",
        headers=("子订单号", "商品编码", "数量"),
        order_key_columns=("子订单号", "商品编码"),
        compared_rows=[ComparedRow(insert, "insert"), ComparedRow(update, "update")],
        existing_date_policy="upsert",
    )
    conn = FakeConnection()
    repo = UploadRepository(conn, config)
    calls = []

    monkeypatch.setattr(repo, "raw_column_types", lambda: {
        "子订单号": "text", "商品编码": "text", "数量": "text",
    })

    def rows_by_keys(key_columns, prepared, compare_headers, column_types, existing_dates):
        calls.append((key_columns, list(prepared), compare_headers, column_types, existing_dates))
        return {
            update.business_key: {
                "id": 99,
                "hash": "old-hash",
                "values": {"子订单号": "B", "商品编码": "SKU-2", "数量": "1"},
                "business_date": date(2026, 7, 28),
            }
        }

    monkeypatch.setattr(repo, "rows_by_keys", rows_by_keys)

    assert repo.write_raw_changes(analysis) == (0, 1, 1)
    assert len(calls) == 1
    assert calls[0][1] == [insert, update]
    assert conn.batches == [
        [("A", "SKU-1", "1")],
        [("B", "SKU-2", "2", 99)],
    ]


def test_doudian_sales_snapshot_classifies_sales_and_refunds_independently():
    rows = [
        PreparedRow(
            2,
            {"订单状态": "已完成", "售后状态": "退款成功", "订单应付金额": "100"},
            date(2026, 7, 1),
            "source_row=2",
            "a",
        ),
        PreparedRow(
            3,
            {"订单状态": "已关闭", "售后状态": "退款成功", "订单应付金额": "50"},
            date(2026, 7, 1),
            "source_row=3",
            "b",
        ),
        PreparedRow(
            4,
            {"订单状态": "已完成", "售后状态": "换货成功", "订单应付金额": "20"},
            date(2026, 7, 1),
            "source_row=4",
            "c",
        ),
        PreparedRow(
            5,
            {"订单状态": "已完成", "售后状态": "换货待收货", "订单应付金额": "30"},
            date(2026, 7, 1),
            "source_row=5",
            "d",
        ),
    ]

    sales, refunds, summary = _classify_file_rows(rows, DOUDIAN_MIXED_SALES_RULES)

    assert sales[date(2026, 7, 1)] == 150
    assert refunds[date(2026, 7, 1)] == 150
    assert summary["valid_sales_rows"] == 3
    assert summary["refund_rows"] == 2
    assert summary["sales_with_refund_rows"] == 1
    assert summary["refund_only_rows"] == 1
    assert summary["gross_sales_amount"] == "150.00"
    assert summary["refund_amount"] == "150.00"


def test_doudian_children_upload_is_enabled_after_atomic_refresher_is_connected():
    from upload.doudian_children.config import CONFIG

    assert CONFIG.commit_enabled is True
    assert "换货待收货" in CONFIG.mixed_sales_rules.non_refund_statuses


def test_weidian_sales_snapshot_uses_separate_sales_refund_and_presale_fields():
    rows = [
        PreparedRow(
            2,
            {
                "订单状态": "已完成",
                "商品发货": "已发货",
                "订单实际收款金额": "100",
                "商品已退款金额": "30",
                "商品数量": "2",
                "是否预售": "预售",
            },
            date(2026, 8, 3),
            "source_row=2",
            "a",
        ),
        PreparedRow(
            3,
            {
                "订单状态": "已取消",
                "商品发货": "未发货",
                "订单实际收款金额": "50",
                "商品已退款金额": "50",
                "商品数量": "1",
                "是否预售": "现货",
            },
            date(2026, 8, 3),
            "source_row=3",
            "b",
        ),
    ]

    sales, refunds, summary = classify_weidian_rows(rows)

    assert sales[date(2026, 8, 3)] == 100
    assert refunds[date(2026, 8, 3)] == 80
    assert summary["valid_sales_rows"] == 1
    assert summary["refund_rows"] == 2
    assert summary["sales_with_refund_rows"] == 1
    assert summary["refund_only_rows"] == 1
    assert summary["presale_rows"] == 1
    assert summary["presale_quantity"] == 2
    assert summary["presale_transaction_amount"] == "100.00"


def test_weidian_upload_is_enabled_with_all_presale_tables():
    from upload.weidian.config import CONFIG

    assert CONFIG.commit_enabled is True
    assert CONFIG.business_preview_builder is not None
    assert CONFIG.downstream_tables[-3:] == (
        "monthly_product_presales",
        "quarterly_product_presales",
        "half_year_product_presales",
    )


def test_kuaishou_uses_order_created_date_and_whole_date_replacement():
    from upload.kuaishou.config import CONFIG

    assert CONFIG.transaction_time_column == "订单创建时间"
    assert CONFIG.existing_date_policy == "replace"
    assert CONFIG.commit_enabled is True
    assert CONFIG.business_preview_builder is not None


def test_kuaishou_refund_rules_keep_sales_and_refunds_separate():
    from upload.kuaishou.refunds import classify_rows

    rows = [
        PreparedRow(
            2,
            {"订单状态": "交易成功", "实付款": "19.9", "售后状态": "退款成功", "订单备注": "差价十元已退"},
            date(2026, 7, 29),
            "source_row=2",
            "a",
        ),
        PreparedRow(
            3,
            {"订单状态": "已收货", "实付款": "9.9", "售后状态": "退款成功", "订单备注": "瑕疵补偿5/瑕疵补偿（3）元待回复"},
            date(2026, 7, 29),
            "source_row=3",
            "b",
        ),
        PreparedRow(
            4,
            {"订单状态": "交易关闭", "实付款": "175.9", "售后状态": "退款成功", "订单备注": "2026-08-03 16:43:21 小额打款金额¥ 3/超重3元已打款"},
            date(2026, 7, 29),
            "source_row=4",
            "c",
        ),
        PreparedRow(
            5,
            {"订单状态": "已收货", "实付款": "29.9", "售后状态": "待买家退货", "订单备注": ""},
            date(2026, 7, 29),
            "source_row=5",
            "d",
        ),
    ]

    sales, refunds, summary = classify_rows(rows)

    assert sales[date(2026, 7, 29)] == Decimal("59.70")
    assert refunds[date(2026, 7, 29)] == Decimal("18.00")
    assert summary["refund_sources"] == {"明确部分退款": 2, "系统小额打款": 1}
    assert summary["sales_with_refund_rows"] == 2
    assert summary["refund_only_rows"] == 1


def test_kuaishou_accepts_legitimate_65_yuan_sales_amount():
    from upload.kuaishou.refunds import classify_rows

    rows = [
        PreparedRow(
            2,
            {"订单状态": "交易成功", "实付款": "65", "售后状态": "", "订单备注": ""},
            date(2026, 8, 13),
            "source_row=2",
            "a",
        )
    ]

    sales, refunds, summary = classify_rows(rows)

    assert sales[date(2026, 8, 13)] == Decimal("65.00")
    assert refunds == {}
    assert summary["invalid_sales_amount_rows"] == 0


def test_alibaba_uses_payment_date_and_sales_amount_directly():
    from upload.alibaba.config import CONFIG

    assert CONFIG.transaction_time_column == "付款日期"
    assert CONFIG.existing_date_policy == "skip"
    assert CONFIG.commit_enabled is True
    assert CONFIG.ignored_upload_columns == ("虚拟分类",)

    rows = [
        PreparedRow(
            2,
            {
                "订单状态": "已发货",
                "销售金额": "100.00",
                "实发金额": "999.00",
                "退货金额": "20.50",
                "实退金额": "999.00",
                "实发数量": "3",
                "实退数量": "2",
                "买家ID": "1001",
                "商品编码": "SKU-1",
            },
            date(2026, 7, 28),
            "source_row=2",
            "a",
        ),
        PreparedRow(
            3,
            {
                "订单状态": "已取消",
                "销售金额": "999.00",
                "实发金额": "1.00",
                "退货金额": "0",
                "实发数量": "9",
                "实退数量": "0",
                "买家ID": "1002",
                "商品编码": "SKU-2",
            },
            date(2026, 7, 28),
            "source_row=3",
            "b",
        ),
    ]

    sales, refunds, summary = classify_alibaba_rows(rows)

    assert sales[date(2026, 7, 28)] == Decimal("100.00")
    assert refunds[date(2026, 7, 28)] == Decimal("20.50")
    assert summary["net_product_quantity"] == "1.00"
    assert summary["shipped_rows"] == 1


def test_alibaba_preview_adds_new_date_to_current_period_values(monkeypatch):
    from upload.alibaba.config import CONFIG

    class FakeRepository:
        def __init__(self, conn, config):
            self.config = config

        def period_amounts(self, schema, table, amount, starts):
            current = {
                "alibaba": Decimal("1000.00"),
                "fenxiao": Decimal("2000.00"),
                "qudao": Decimal("3000.00"),
            }[schema]
            return {
                start: {"amount": current if start == date(2026, 7, 27) else Decimal("500.00")}
                for start in starts
            }

    monkeypatch.setattr("upload.alibaba.preview.UploadRepository", FakeRepository)
    rows = [PreparedRow(
        2,
        {
            "订单状态": "已发货", "销售金额": "100", "退货金额": "20",
            "实发数量": "2", "实退数量": "1", "买家ID": "C1", "商品编码": "P1",
        },
        date(2026, 7, 28),
        "source_row=2",
        "hash",
    )]

    preview = build_alibaba_preview(None, CONFIG, rows, set())
    source = preview["source_classification"]
    store_week = preview["store_period_changes"]["weeks"][0]
    fenxiao_week = preview["aggregate_period_changes"]["fenxiao"]["weeks"][0]
    qudao_week = preview["aggregate_period_changes"]["qudao"]["weeks"][0]

    assert source["valid_sales_rows"] == 1
    assert source["gross_sales_amount"] == "100.00"
    assert source["sales_with_refund_rows"] == 1
    assert store_week["file_sales_amount"] == "100.00"
    assert store_week["projected_store_sales_amount"] == "1100.00"
    assert store_week["projected_store_refund_amount"] == "1020.00"
    assert fenxiao_week["projected_sales_amount"] == "2100.00"
    assert qudao_week["projected_sales_amount"] == "3100.00"


def test_distribution_refresh_plan_lists_store_group_and_channel_tables():
    result = aggregate_refresh_tables(("fenxiao", "qudao"))

    assert "customer_health_detail" in result["fenxiao"]
    assert "half_year_high_frequency_products" in result["fenxiao"]
    assert "weekly_refunds" in result["qudao"]


def test_aggregate_refresh_plan_lists_real_tables_not_only_schema_names():
    result = aggregate_refresh_tables(("doudian", "daren", "qudao"))

    assert "weekly_sales_summary" in result["doudian"]
    assert "weekly_refunds" in result["daren"]
    assert "monthly_sales" in result["qudao"]
