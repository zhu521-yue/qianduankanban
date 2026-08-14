BEGIN;

ALTER DATABASE weidian SET timezone TO 'Asia/Shanghai';
SET LOCAL TIME ZONE 'Asia/Shanghai';

CREATE SCHEMA hh AUTHORIZATION root;

COMMENT ON SCHEMA hh IS 'AI客户经营看板数据表';

CREATE FUNCTION hh.set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;

-- 01 原始数据上传表
CREATE TABLE hh.raw_data (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    "订单号" TEXT NOT NULL,
    "订单下单时间" TIMESTAMPTZ NOT NULL,
    "订单发货时间" TIMESTAMPTZ,
    "订单确认收货时间" TIMESTAMPTZ,
    "订单完成结算时间" TIMESTAMPTZ,
    "订单状态" TEXT,
    "发货方式" TEXT,
    "收件人姓名" TEXT,
    "收件人地址" TEXT,
    "省" TEXT,
    "市" TEXT,
    "区" TEXT,
    "收件人手机" TEXT,
    "买家备注" TEXT,
    "商家备注" TEXT,
    "打标颜色" TEXT,
    "商品总价" NUMERIC(18,2),
    "订单实际支付金额" NUMERIC(18,2),
    "订单实际收款金额" NUMERIC(18,2),
    "订单运费" NUMERIC(18,2),
    "商品优惠" NUMERIC(18,2),
    "跨店优惠" NUMERIC(18,2),
    "商品改价" NUMERIC(18,2),
    "积分抵扣" NUMERIC(18,2),
    "支付方式" TEXT,
    "支付时间" TIMESTAMPTZ,
    "交易单号" TEXT,
    "物流公司" TEXT,
    "快递单号" TEXT,
    "技术服务费" NUMERIC(18,2),
    "技术服务费（将以人气卡形式返还）" NUMERIC(18,2),
    "运费险预计投保费用" NUMERIC(18,2),
    "带货方式" TEXT,
    "带货账号类型" TEXT,
    "带货账号昵称" TEXT,
    "带货ID" TEXT,
    "带货费用渠道" TEXT,
    "带货费用类型" TEXT,
    "带货费用" NUMERIC(18,2),
    "带货佣金率" NUMERIC(9,6),
    "企微企业ID" TEXT,
    "企微工号" TEXT,
    "导购最近分享时间" TIMESTAMPTZ,
    "企业微信加密id" TEXT,
    "企微备注" TEXT,
    "礼物单号" TEXT,
    "商品名称" TEXT,
    "商品编码(平台)" TEXT,
    "商品编码(自定义)" TEXT,
    "SKU编码(自定义)" TEXT,
    "商品属性" TEXT,
    "商品价格(单件)" NUMERIC(18,2),
    "商品实际价格(单件)" NUMERIC(18,2),
    "商品实际价格(总共)" NUMERIC(18,2),
    "是否预售" TEXT,
    "商品数量" INTEGER,
    "商品平台券优惠" NUMERIC(18,2),
    "商品平均运费" NUMERIC(18,2),
    "活动商家补贴" NUMERIC(18,2),
    "定制信息" TEXT,
    "定制预览图" TEXT,
    "商品发货" TEXT,
    "商品售后" TEXT,
    "商品已退款金额" NUMERIC(18,2),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 02 客户ID表
CREATE TABLE hh.customer_id_mapping (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id TEXT NOT NULL,
    affiliate_id TEXT,
    affiliate_nickname TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (customer_id)
);

-- 03 日销售额表
CREATE TABLE hh.daily_sales (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    transaction_date DATE NOT NULL,
    transaction_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (transaction_date)
);

-- 04 日商品销售额表
CREATE TABLE hh.daily_product_sales (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    transaction_date DATE NOT NULL,
    product_code TEXT NOT NULL,
    transaction_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    product_quantity BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (transaction_date, product_code)
);

-- 05 日客户销售额表
CREATE TABLE hh.daily_customer_sales (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    transaction_date DATE NOT NULL,
    customer_id TEXT NOT NULL,
    transaction_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (transaction_date, customer_id)
);

-- 06 周销售额表
CREATE TABLE hh.weekly_sales (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    weekly_transaction_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (EXTRACT(ISODOW FROM period_start) = 1 AND period_end = period_start + 6),
    UNIQUE (period_start, period_end)
);

-- 07 周退款额表
CREATE TABLE hh.weekly_refunds (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    weekly_refund_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (EXTRACT(ISODOW FROM period_start) = 1 AND period_end = period_start + 6),
    UNIQUE (period_start, period_end)
);

-- 08 周商品销售额表
CREATE TABLE hh.weekly_product_sales (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    product_code TEXT NOT NULL,
    weekly_transaction_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    weekly_product_quantity BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (EXTRACT(ISODOW FROM period_start) = 1 AND period_end = period_start + 6),
    UNIQUE (period_start, period_end, product_code)
);

-- 09 周客户销售额表
CREATE TABLE hh.weekly_customer_sales (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    customer_id TEXT NOT NULL,
    weekly_transaction_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (EXTRACT(ISODOW FROM period_start) = 1 AND period_end = period_start + 6),
    UNIQUE (period_start, period_end, customer_id)
);

-- 10 月销售额表
CREATE TABLE hh.monthly_sales (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    monthly_transaction_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        period_start = DATE_TRUNC('month', period_start)::DATE
        AND period_end = (period_start + INTERVAL '1 month - 1 day')::DATE
    ),
    UNIQUE (period_start, period_end)
);

-- 11 月退款额表
CREATE TABLE hh.monthly_refunds (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    monthly_refund_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        period_start = DATE_TRUNC('month', period_start)::DATE
        AND period_end = (period_start + INTERVAL '1 month - 1 day')::DATE
    ),
    UNIQUE (period_start, period_end)
);

-- 12 月商品销售额表
CREATE TABLE hh.monthly_product_sales (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    product_code TEXT NOT NULL,
    monthly_transaction_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    monthly_product_quantity BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        period_start = DATE_TRUNC('month', period_start)::DATE
        AND period_end = (period_start + INTERVAL '1 month - 1 day')::DATE
    ),
    UNIQUE (period_start, period_end, product_code)
);

-- 13 月客户销售额表
CREATE TABLE hh.monthly_customer_sales (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    customer_id TEXT NOT NULL,
    monthly_transaction_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        period_start = DATE_TRUNC('month', period_start)::DATE
        AND period_end = (period_start + INTERVAL '1 month - 1 day')::DATE
    ),
    UNIQUE (period_start, period_end, customer_id)
);

-- 14 月商品预售表
CREATE TABLE hh.monthly_product_presales (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    product_code TEXT NOT NULL,
    is_presale BOOLEAN NOT NULL,
    monthly_presale_quantity BIGINT NOT NULL DEFAULT 0,
    monthly_presale_transaction_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        period_start = DATE_TRUNC('month', period_start)::DATE
        AND period_end = (period_start + INTERVAL '1 month - 1 day')::DATE
    ),
    UNIQUE (period_start, period_end, product_code, is_presale)
);

-- 15 季度销售额表
CREATE TABLE hh.quarterly_sales (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    quarterly_transaction_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        period_start = DATE_TRUNC('month', period_start)::DATE
        AND EXTRACT(MONTH FROM period_start) IN (2, 5, 8, 11)
        AND period_end = (period_start + INTERVAL '3 months - 1 day')::DATE
    ),
    UNIQUE (period_start, period_end)
);

-- 16 季度退款额表
CREATE TABLE hh.quarterly_refunds (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    quarterly_refund_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        period_start = DATE_TRUNC('month', period_start)::DATE
        AND EXTRACT(MONTH FROM period_start) IN (2, 5, 8, 11)
        AND period_end = (period_start + INTERVAL '3 months - 1 day')::DATE
    ),
    UNIQUE (period_start, period_end)
);

-- 17 季度商品销售额表
CREATE TABLE hh.quarterly_product_sales (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    product_code TEXT NOT NULL,
    quarterly_transaction_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    quarterly_product_quantity BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        period_start = DATE_TRUNC('month', period_start)::DATE
        AND EXTRACT(MONTH FROM period_start) IN (2, 5, 8, 11)
        AND period_end = (period_start + INTERVAL '3 months - 1 day')::DATE
    ),
    UNIQUE (period_start, period_end, product_code)
);

-- 18 季度客户销售额表
CREATE TABLE hh.quarterly_customer_sales (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    customer_id TEXT NOT NULL,
    quarterly_transaction_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        period_start = DATE_TRUNC('month', period_start)::DATE
        AND EXTRACT(MONTH FROM period_start) IN (2, 5, 8, 11)
        AND period_end = (period_start + INTERVAL '3 months - 1 day')::DATE
    ),
    UNIQUE (period_start, period_end, customer_id)
);

-- 19 季度商品预售表
CREATE TABLE hh.quarterly_product_presales (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    product_code TEXT NOT NULL,
    is_presale BOOLEAN NOT NULL,
    quarterly_presale_quantity BIGINT NOT NULL DEFAULT 0,
    quarterly_presale_transaction_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        period_start = DATE_TRUNC('month', period_start)::DATE
        AND EXTRACT(MONTH FROM period_start) IN (2, 5, 8, 11)
        AND period_end = (period_start + INTERVAL '3 months - 1 day')::DATE
    ),
    UNIQUE (period_start, period_end, product_code, is_presale)
);

-- 20 半年销售额表
CREATE TABLE hh.half_year_sales (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    half_year_transaction_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        period_start = DATE_TRUNC('month', period_start)::DATE
        AND EXTRACT(MONTH FROM period_start) IN (2, 8)
        AND period_end = (period_start + INTERVAL '6 months - 1 day')::DATE
    ),
    UNIQUE (period_start, period_end)
);

-- 21 半年退款额表
CREATE TABLE hh.half_year_refunds (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    half_year_refund_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        period_start = DATE_TRUNC('month', period_start)::DATE
        AND EXTRACT(MONTH FROM period_start) IN (2, 8)
        AND period_end = (period_start + INTERVAL '6 months - 1 day')::DATE
    ),
    UNIQUE (period_start, period_end)
);

-- 22 半年商品销售额表
CREATE TABLE hh.half_year_product_sales (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    product_code TEXT NOT NULL,
    half_year_transaction_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    half_year_product_quantity BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        period_start = DATE_TRUNC('month', period_start)::DATE
        AND EXTRACT(MONTH FROM period_start) IN (2, 8)
        AND period_end = (period_start + INTERVAL '6 months - 1 day')::DATE
    ),
    UNIQUE (period_start, period_end, product_code)
);

-- 23 半年客户销售额表
CREATE TABLE hh.half_year_customer_sales (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    customer_id TEXT NOT NULL,
    half_year_transaction_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        period_start = DATE_TRUNC('month', period_start)::DATE
        AND EXTRACT(MONTH FROM period_start) IN (2, 8)
        AND period_end = (period_start + INTERVAL '6 months - 1 day')::DATE
    ),
    UNIQUE (period_start, period_end, customer_id)
);

-- 24 半年商品预售表
CREATE TABLE hh.half_year_product_presales (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    product_code TEXT NOT NULL,
    is_presale BOOLEAN NOT NULL,
    half_year_presale_quantity BIGINT NOT NULL DEFAULT 0,
    half_year_presale_transaction_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        period_start = DATE_TRUNC('month', period_start)::DATE
        AND EXTRACT(MONTH FROM period_start) IN (2, 8)
        AND period_end = (period_start + INTERVAL '6 months - 1 day')::DATE
    ),
    UNIQUE (period_start, period_end, product_code, is_presale)
);

-- 25 日销售额维度表
CREATE TABLE hh.daily_sales_metrics (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    transaction_date DATE NOT NULL,
    transaction_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    year_over_year_rate NUMERIC(12,6),
    rolling_7_day_transaction_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    rolling_30_day_transaction_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (transaction_date)
);

-- 26 周销售额维度表
CREATE TABLE hh.weekly_sales_metrics (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    weekly_transaction_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    week_over_week_rate NUMERIC(12,6),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (EXTRACT(ISODOW FROM period_start) = 1 AND period_end = period_start + 6),
    UNIQUE (period_start, period_end)
);

-- 27 月销售额维度表
CREATE TABLE hh.monthly_sales_metrics (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    monthly_transaction_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    month_over_month_rate NUMERIC(12,6),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        period_start = DATE_TRUNC('month', period_start)::DATE
        AND period_end = (period_start + INTERVAL '1 month - 1 day')::DATE
    ),
    UNIQUE (period_start, period_end)
);

-- 28 客户日销售额表
CREATE TABLE hh.customer_daily_sales (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    transaction_date DATE NOT NULL,
    customer_id TEXT NOT NULL,
    transaction_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (customer_id, transaction_date)
);

-- 29 客户日销售额维度表
CREATE TABLE hh.customer_daily_sales_metrics (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    transaction_date DATE NOT NULL,
    customer_id TEXT NOT NULL,
    transaction_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    rolling_7_day_transaction_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    rolling_30_day_transaction_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (customer_id, transaction_date)
);

-- 30 客户周销售额表
CREATE TABLE hh.customer_weekly_sales (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    customer_id TEXT NOT NULL,
    weekly_transaction_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    weekly_purchase_count BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (EXTRACT(ISODOW FROM period_start) = 1 AND period_end = period_start + 6),
    UNIQUE (customer_id, period_start, period_end)
);

-- 31 客户月销售额表
CREATE TABLE hh.customer_monthly_sales (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    customer_id TEXT NOT NULL,
    monthly_transaction_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    monthly_purchase_count BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        period_start = DATE_TRUNC('month', period_start)::DATE
        AND period_end = (period_start + INTERVAL '1 month - 1 day')::DATE
    ),
    UNIQUE (customer_id, period_start, period_end)
);

-- 32 客户季度销售额表
CREATE TABLE hh.customer_quarterly_sales (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    customer_id TEXT NOT NULL,
    quarterly_transaction_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    quarterly_purchase_count BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        period_start = DATE_TRUNC('month', period_start)::DATE
        AND EXTRACT(MONTH FROM period_start) IN (2, 5, 8, 11)
        AND period_end = (period_start + INTERVAL '3 months - 1 day')::DATE
    ),
    UNIQUE (customer_id, period_start, period_end)
);

-- 33 客户半年销售额表
CREATE TABLE hh.customer_half_year_sales (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    customer_id TEXT NOT NULL,
    half_year_transaction_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    half_year_purchase_count BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        period_start = DATE_TRUNC('month', period_start)::DATE
        AND EXTRACT(MONTH FROM period_start) IN (2, 8)
        AND period_end = (period_start + INTERVAL '6 months - 1 day')::DATE
    ),
    UNIQUE (customer_id, period_start, period_end)
);

-- 34 客户日商品销售额表
CREATE TABLE hh.customer_daily_product_sales (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    transaction_date DATE NOT NULL,
    customer_id TEXT NOT NULL,
    product_code TEXT NOT NULL,
    transaction_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    product_quantity BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (customer_id, transaction_date, product_code)
);

-- 35 客户月商品销售额表
CREATE TABLE hh.customer_monthly_product_sales (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    customer_id TEXT NOT NULL,
    product_code TEXT NOT NULL,
    monthly_transaction_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    monthly_product_quantity BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        period_start = DATE_TRUNC('month', period_start)::DATE
        AND period_end = (period_start + INTERVAL '1 month - 1 day')::DATE
    ),
    UNIQUE (customer_id, period_start, period_end, product_code)
);

-- 36 客户季度商品销售额表
CREATE TABLE hh.customer_quarterly_product_sales (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    customer_id TEXT NOT NULL,
    product_code TEXT NOT NULL,
    quarterly_transaction_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    quarterly_product_quantity BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        period_start = DATE_TRUNC('month', period_start)::DATE
        AND EXTRACT(MONTH FROM period_start) IN (2, 5, 8, 11)
        AND period_end = (period_start + INTERVAL '3 months - 1 day')::DATE
    ),
    UNIQUE (customer_id, period_start, period_end, product_code)
);

-- 37 客户半年商品销售额表
CREATE TABLE hh.customer_half_year_product_sales (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    customer_id TEXT NOT NULL,
    product_code TEXT NOT NULL,
    half_year_transaction_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    half_year_product_quantity BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        period_start = DATE_TRUNC('month', period_start)::DATE
        AND EXTRACT(MONTH FROM period_start) IN (2, 8)
        AND period_end = (period_start + INTERVAL '6 months - 1 day')::DATE
    ),
    UNIQUE (customer_id, period_start, period_end, product_code)
);

-- 38 客户健康度明细表
CREATE TABLE hh.customer_health_detail (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    customer_id TEXT NOT NULL,
    half_year_purchase_count BIGINT NOT NULL DEFAULT 0,
    half_year_purchase_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    customer_health_score NUMERIC(5,2) NOT NULL,
    customer_health_status TEXT NOT NULL,
    risk_reason TEXT,
    follow_up_action TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        period_start = DATE_TRUNC('month', period_start)::DATE
        AND EXTRACT(MONTH FROM period_start) IN (2, 8)
        AND period_end = (period_start + INTERVAL '6 months - 1 day')::DATE
    ),
    CHECK (customer_health_score BETWEEN 0 AND 100),
    UNIQUE (customer_id, period_start, period_end)
);

-- 原始数据常用筛选索引
CREATE INDEX raw_data_order_number_idx ON hh.raw_data ("订单号");
CREATE INDEX raw_data_order_time_idx ON hh.raw_data ("订单下单时间");
CREATE INDEX raw_data_affiliate_id_idx ON hh.raw_data ("带货ID");
CREATE INDEX raw_data_product_code_idx ON hh.raw_data ("商品编码(自定义)");
CREATE INDEX raw_data_sales_filter_idx ON hh.raw_data ("订单状态", "商品发货");

-- 所有表统一维护 updated_at
DO $$
DECLARE
    target_table RECORD;
BEGIN
    FOR target_table IN
        SELECT tablename
        FROM pg_tables
        WHERE schemaname = 'hh'
    LOOP
        EXECUTE FORMAT(
            'CREATE TRIGGER set_updated_at_before_update
             BEFORE UPDATE ON hh.%I
             FOR EACH ROW
             EXECUTE FUNCTION hh.set_updated_at()',
            target_table.tablename
        );
    END LOOP;
END;
$$;

COMMIT;
