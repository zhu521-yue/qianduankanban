from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping

from upload.models import PreparedRow


ZERO = Decimal("0.00")
_SYSTEM_PAYMENT = re.compile(r"小额打款金额\s*[¥￥]?\s*(\d+(?:\.\d+)?)")
_ARABIC_AMOUNT = re.compile(r"(?:差价|运费|补偿)[^/\d]{0,8}(\d+(?:\.\d+)?)")
_CHINESE_AMOUNT = re.compile(r"(?:差价|运费|补偿)[^/零一二两三四五六七八九十百]{0,8}([零一二两三四五六七八九十百]+)元?")
_PENDING_WORDS = ("待回复", "待确认", "协商", "可以退", "申请", "未退")
_COMPLETED_WORDS = ("已退", "已打款", "已补偿", "瑕疵补偿", "运费补偿")


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _money(value: Any) -> Decimal | None:
    text = _text(value).replace(",", "").replace("¥", "").replace("￥", "")
    if not text or text in {"-", "--", "65"}:
        return None
    try:
        return Decimal(text).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def _chinese_integer(value: str) -> int | None:
    digits = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    if not value:
        return None
    if "百" in value:
        left, _, right = value.partition("百")
        hundreds = digits.get(left, 1) if left else 1
        tail = _chinese_integer(right) if right else 0
        return None if tail is None else hundreds * 100 + tail
    if "十" in value:
        left, _, right = value.partition("十")
        tens = digits.get(left, 1) if left else 1
        ones = digits.get(right, 0) if right else 0
        return tens * 10 + ones
    total = 0
    for character in value:
        if character not in digits:
            return None
        total = total * 10 + digits[character]
    return total


def _system_payments(note: str) -> list[Decimal]:
    amounts: list[Decimal] = []
    seen: set[tuple[str, str]] = set()
    for segment in note.split("/"):
        match = _SYSTEM_PAYMENT.search(segment)
        if not match:
            continue
        timestamp_match = re.search(r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}", segment)
        event_key = (timestamp_match.group(0) if timestamp_match else segment, match.group(1))
        if event_key in seen:
            continue
        seen.add(event_key)
        amounts.append(Decimal(match.group(1)).quantize(Decimal("0.01")))
    return amounts


def _explicit_completed_amounts(note: str) -> list[Decimal]:
    result: list[Decimal] = []
    for segment in note.split("/"):
        if any(word in segment for word in _PENDING_WORDS):
            continue
        if not any(word in segment for word in _COMPLETED_WORDS):
            continue
        match = _ARABIC_AMOUNT.search(segment)
        if match:
            result.append(Decimal(match.group(1)).quantize(Decimal("0.01")))
            continue
        chinese = _CHINESE_AMOUNT.search(segment)
        if chinese and (amount := _chinese_integer(chinese.group(1))) is not None:
            result.append(Decimal(amount).quantize(Decimal("0.01")))
    return result


def classify_refund(values: Mapping[str, Any]) -> tuple[Decimal, str]:
    """Return the trusted refund amount represented by one Kuaishou row."""
    note = _text(values.get("订单备注"))
    system = _system_payments(note)
    if system:
        return sum(system, ZERO), "系统小额打款"

    explicit = sorted(set(_explicit_completed_amounts(note)))
    if len(explicit) == 1:
        return explicit[0], "明确部分退款"

    refund_status = _text(values.get("售后状态"))
    paid = _money(values.get("实付款"))
    if refund_status == "退款成功" and paid is not None and paid > ZERO:
        return paid, "退款成功按实付款"
    return ZERO, "非退款"


def classify_rows(
    rows: Iterable[PreparedRow],
) -> tuple[dict[date, Decimal], dict[date, Decimal], dict[str, Any]]:
    sales: dict[date, Decimal] = defaultdict(lambda: ZERO)
    refunds: dict[date, Decimal] = defaultdict(lambda: ZERO)
    sources: Counter[str] = Counter()
    summary: dict[str, Any] = {
        "dated_rows": 0,
        "valid_sales_rows": 0,
        "refund_rows": 0,
        "sales_with_refund_rows": 0,
        "refund_only_rows": 0,
        "invalid_sales_amount_rows": 0,
    }
    gross_sales = ZERO
    refund_total = ZERO

    for item in rows:
        if item.business_date is None:
            continue
        summary["dated_rows"] += 1
        values = item.values
        status = _text(values.get("订单状态"))
        amount = _money(values.get("实付款"))
        is_sale = status in {"交易成功", "已发货", "已收货"}
        refund, source = classify_refund(values)
        is_refund = refund > ZERO

        if is_sale:
            if amount is None:
                summary["invalid_sales_amount_rows"] += 1
            else:
                summary["valid_sales_rows"] += 1
                sales[item.business_date] += amount
                gross_sales += amount
        if is_refund:
            summary["refund_rows"] += 1
            refunds[item.business_date] += refund
            refund_total += refund
            sources[source] += 1
        if is_sale and is_refund:
            summary["sales_with_refund_rows"] += 1
        elif is_refund:
            summary["refund_only_rows"] += 1

    summary.update({
        "gross_sales_amount": f"{gross_sales:.2f}",
        "refund_amount": f"{refund_total:.2f}",
        "net_amount_for_reference_only": f"{gross_sales - refund_total:.2f}",
        "refund_sources": dict(sources),
        "sales_amount_is_gross": True,
        "refund_is_recorded_separately": True,
    })
    return dict(sales), dict(refunds), summary

