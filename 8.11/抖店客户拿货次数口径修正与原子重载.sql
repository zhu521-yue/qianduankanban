\set ON_ERROR_STOP on

BEGIN;
SET LOCAL TIME ZONE 'Asia/Shanghai';

-- 本次修正范围：
-- 1. 两家抖店的客户周/月/季度/半年销售表；
-- 2. 两家抖店依赖半年拿货次数的客户健康度表；
-- 3. 抖店总体依赖两家店数据的半年客户健康度表。
--
-- 新口径：拿货次数 = 指定周期内，客户ID在 customer_daily_sales 中出现的次数。
-- customer_daily_sales 的业务唯一粒度为“交易日期 + 客户ID”，因此该次数等于有效拿货天数。

LOCK TABLE
    "doudianChildren".customer_daily_sales,
    "doudianKocotree".customer_daily_sales
IN SHARE MODE;

TRUNCATE TABLE
    "doudianChildren".customer_weekly_sales,
    "doudianChildren".customer_monthly_sales,
    "doudianChildren".customer_quarterly_sales,
    "doudianChildren".customer_half_year_sales,
    "doudianChildren".customer_health_detail,
    "doudianKocotree".customer_weekly_sales,
    "doudianKocotree".customer_monthly_sales,
    "doudianKocotree".customer_quarterly_sales,
    "doudianKocotree".customer_half_year_sales,
    "doudianKocotree".customer_health_detail,
    doudian.half_year_customer_health
RESTART IDENTITY;

-- ============================================================
-- 一、抖店儿童服饰旗舰店
-- ============================================================

INSERT INTO "doudianChildren".customer_weekly_sales (
    period_start,
    period_end,
    customer_id,
    weekly_transaction_amount,
    weekly_purchase_count
)
SELECT
    period_start,
    period_start + 6,
    customer_id,
    SUM(transaction_amount)::NUMERIC(18,2),
    COUNT(*)::BIGINT
FROM (
    SELECT
        transaction_date - (EXTRACT(ISODOW FROM transaction_date)::INTEGER - 1) AS period_start,
        customer_id,
        transaction_amount
    FROM "doudianChildren".customer_daily_sales
) source_data
GROUP BY period_start, customer_id
ORDER BY customer_id, period_start;

INSERT INTO "doudianChildren".customer_monthly_sales (
    period_start,
    period_end,
    customer_id,
    monthly_transaction_amount,
    monthly_purchase_count
)
SELECT
    period_start,
    (period_start + INTERVAL '1 month - 1 day')::DATE,
    customer_id,
    SUM(transaction_amount)::NUMERIC(18,2),
    COUNT(*)::BIGINT
FROM (
    SELECT
        DATE_TRUNC('month', transaction_date)::DATE AS period_start,
        customer_id,
        transaction_amount
    FROM "doudianChildren".customer_daily_sales
) source_data
GROUP BY period_start, customer_id
ORDER BY customer_id, period_start;

INSERT INTO "doudianChildren".customer_quarterly_sales (
    period_start,
    period_end,
    customer_id,
    quarterly_transaction_amount,
    quarterly_purchase_count
)
SELECT
    period_start,
    (period_start + INTERVAL '3 months - 1 day')::DATE,
    customer_id,
    SUM(transaction_amount)::NUMERIC(18,2),
    COUNT(*)::BIGINT
FROM (
    SELECT
        CASE
            WHEN EXTRACT(MONTH FROM transaction_date)::INTEGER BETWEEN 2 AND 4
                THEN MAKE_DATE(EXTRACT(YEAR FROM transaction_date)::INTEGER, 2, 1)
            WHEN EXTRACT(MONTH FROM transaction_date)::INTEGER BETWEEN 5 AND 7
                THEN MAKE_DATE(EXTRACT(YEAR FROM transaction_date)::INTEGER, 5, 1)
            WHEN EXTRACT(MONTH FROM transaction_date)::INTEGER BETWEEN 8 AND 10
                THEN MAKE_DATE(EXTRACT(YEAR FROM transaction_date)::INTEGER, 8, 1)
            WHEN EXTRACT(MONTH FROM transaction_date)::INTEGER IN (11, 12)
                THEN MAKE_DATE(EXTRACT(YEAR FROM transaction_date)::INTEGER, 11, 1)
            ELSE MAKE_DATE(EXTRACT(YEAR FROM transaction_date)::INTEGER - 1, 11, 1)
        END AS period_start,
        customer_id,
        transaction_amount
    FROM "doudianChildren".customer_daily_sales
) source_data
GROUP BY period_start, customer_id
ORDER BY customer_id, period_start;

INSERT INTO "doudianChildren".customer_half_year_sales (
    period_start,
    period_end,
    customer_id,
    half_year_transaction_amount,
    half_year_purchase_count
)
SELECT
    period_start,
    (period_start + INTERVAL '6 months - 1 day')::DATE,
    customer_id,
    SUM(transaction_amount)::NUMERIC(18,2),
    COUNT(*)::BIGINT
FROM (
    SELECT
        CASE
            WHEN EXTRACT(MONTH FROM transaction_date)::INTEGER BETWEEN 2 AND 7
                THEN MAKE_DATE(EXTRACT(YEAR FROM transaction_date)::INTEGER, 2, 1)
            WHEN EXTRACT(MONTH FROM transaction_date)::INTEGER BETWEEN 8 AND 12
                THEN MAKE_DATE(EXTRACT(YEAR FROM transaction_date)::INTEGER, 8, 1)
            ELSE MAKE_DATE(EXTRACT(YEAR FROM transaction_date)::INTEGER - 1, 8, 1)
        END AS period_start,
        customer_id,
        transaction_amount
    FROM "doudianChildren".customer_daily_sales
) source_data
GROUP BY period_start, customer_id
ORDER BY customer_id, period_start;

WITH component_scores AS (
    SELECT
        period_start,
        period_end,
        customer_id,
        half_year_purchase_count,
        half_year_transaction_amount AS half_year_purchase_amount,
        CASE
            WHEN half_year_purchase_count >= 4 THEN 100.00
            WHEN half_year_purchase_count = 3 THEN 80.00
            WHEN half_year_purchase_count BETWEEN 1 AND 2 THEN 60.00
            ELSE 20.00
        END::NUMERIC(5,2) AS count_score,
        CASE
            WHEN half_year_transaction_amount >= 550000 THEN 100.00
            WHEN half_year_transaction_amount >= 400000 THEN 80.00
            WHEN half_year_transaction_amount >= 200000 THEN 70.00
            WHEN half_year_transaction_amount >= 100000 THEN 60.00
            WHEN half_year_transaction_amount >= 50000 THEN 40.00
            WHEN half_year_transaction_amount >= 10000 THEN 20.00
            ELSE 10.00
        END::NUMERIC(5,2) AS amount_score
    FROM "doudianChildren".customer_half_year_sales
), scored AS (
    SELECT *, ROUND(count_score * 0.40 + amount_score * 0.60, 2)::NUMERIC(5,2) AS score
    FROM component_scores
)
INSERT INTO "doudianChildren".customer_health_detail (
    period_start,
    period_end,
    customer_id,
    half_year_purchase_count,
    half_year_purchase_amount,
    customer_health_score,
    customer_health_status,
    state_instructions,
    follow_up_action
)
SELECT
    period_start,
    period_end,
    customer_id,
    half_year_purchase_count,
    half_year_purchase_amount,
    score,
    CASE
        WHEN score >= 90 THEN '高活跃'
        WHEN score >= 80 THEN '活跃'
        WHEN score >= 70 THEN '稳定'
        WHEN score >= 50 THEN '观察'
        WHEN score >= 40 THEN '风险'
        WHEN score >= 20 THEN '流失预警'
        ELSE '流失'
    END,
    NULL::TEXT,
    NULL::TEXT
FROM scored
ORDER BY customer_id, period_start;

-- ============================================================
-- 二、抖店Kocotree服饰配件店
-- ============================================================

INSERT INTO "doudianKocotree".customer_weekly_sales (
    period_start,
    period_end,
    customer_id,
    weekly_transaction_amount,
    weekly_purchase_count
)
SELECT
    period_start,
    period_start + 6,
    customer_id,
    SUM(transaction_amount)::NUMERIC(18,2),
    COUNT(*)::BIGINT
FROM (
    SELECT
        transaction_date - (EXTRACT(ISODOW FROM transaction_date)::INTEGER - 1) AS period_start,
        customer_id,
        transaction_amount
    FROM "doudianKocotree".customer_daily_sales
) source_data
GROUP BY period_start, customer_id
ORDER BY customer_id, period_start;

INSERT INTO "doudianKocotree".customer_monthly_sales (
    period_start,
    period_end,
    customer_id,
    monthly_transaction_amount,
    monthly_purchase_count
)
SELECT
    period_start,
    (period_start + INTERVAL '1 month - 1 day')::DATE,
    customer_id,
    SUM(transaction_amount)::NUMERIC(18,2),
    COUNT(*)::BIGINT
FROM (
    SELECT
        DATE_TRUNC('month', transaction_date)::DATE AS period_start,
        customer_id,
        transaction_amount
    FROM "doudianKocotree".customer_daily_sales
) source_data
GROUP BY period_start, customer_id
ORDER BY customer_id, period_start;

INSERT INTO "doudianKocotree".customer_quarterly_sales (
    period_start,
    period_end,
    customer_id,
    quarterly_transaction_amount,
    quarterly_purchase_count
)
SELECT
    period_start,
    (period_start + INTERVAL '3 months - 1 day')::DATE,
    customer_id,
    SUM(transaction_amount)::NUMERIC(18,2),
    COUNT(*)::BIGINT
FROM (
    SELECT
        CASE
            WHEN EXTRACT(MONTH FROM transaction_date)::INTEGER BETWEEN 2 AND 4
                THEN MAKE_DATE(EXTRACT(YEAR FROM transaction_date)::INTEGER, 2, 1)
            WHEN EXTRACT(MONTH FROM transaction_date)::INTEGER BETWEEN 5 AND 7
                THEN MAKE_DATE(EXTRACT(YEAR FROM transaction_date)::INTEGER, 5, 1)
            WHEN EXTRACT(MONTH FROM transaction_date)::INTEGER BETWEEN 8 AND 10
                THEN MAKE_DATE(EXTRACT(YEAR FROM transaction_date)::INTEGER, 8, 1)
            WHEN EXTRACT(MONTH FROM transaction_date)::INTEGER IN (11, 12)
                THEN MAKE_DATE(EXTRACT(YEAR FROM transaction_date)::INTEGER, 11, 1)
            ELSE MAKE_DATE(EXTRACT(YEAR FROM transaction_date)::INTEGER - 1, 11, 1)
        END AS period_start,
        customer_id,
        transaction_amount
    FROM "doudianKocotree".customer_daily_sales
) source_data
GROUP BY period_start, customer_id
ORDER BY customer_id, period_start;

INSERT INTO "doudianKocotree".customer_half_year_sales (
    period_start,
    period_end,
    customer_id,
    half_year_transaction_amount,
    half_year_purchase_count
)
SELECT
    period_start,
    (period_start + INTERVAL '6 months - 1 day')::DATE,
    customer_id,
    SUM(transaction_amount)::NUMERIC(18,2),
    COUNT(*)::BIGINT
FROM (
    SELECT
        CASE
            WHEN EXTRACT(MONTH FROM transaction_date)::INTEGER BETWEEN 2 AND 7
                THEN MAKE_DATE(EXTRACT(YEAR FROM transaction_date)::INTEGER, 2, 1)
            WHEN EXTRACT(MONTH FROM transaction_date)::INTEGER BETWEEN 8 AND 12
                THEN MAKE_DATE(EXTRACT(YEAR FROM transaction_date)::INTEGER, 8, 1)
            ELSE MAKE_DATE(EXTRACT(YEAR FROM transaction_date)::INTEGER - 1, 8, 1)
        END AS period_start,
        customer_id,
        transaction_amount
    FROM "doudianKocotree".customer_daily_sales
) source_data
GROUP BY period_start, customer_id
ORDER BY customer_id, period_start;

WITH component_scores AS (
    SELECT
        period_start,
        period_end,
        customer_id,
        half_year_purchase_count,
        half_year_transaction_amount AS half_year_purchase_amount,
        CASE
            WHEN half_year_purchase_count >= 4 THEN 100.00
            WHEN half_year_purchase_count = 3 THEN 80.00
            WHEN half_year_purchase_count BETWEEN 1 AND 2 THEN 60.00
            ELSE 20.00
        END::NUMERIC(5,2) AS count_score,
        CASE
            WHEN half_year_transaction_amount >= 550000 THEN 100.00
            WHEN half_year_transaction_amount >= 400000 THEN 80.00
            WHEN half_year_transaction_amount >= 200000 THEN 70.00
            WHEN half_year_transaction_amount >= 100000 THEN 60.00
            WHEN half_year_transaction_amount >= 50000 THEN 40.00
            WHEN half_year_transaction_amount >= 10000 THEN 20.00
            ELSE 10.00
        END::NUMERIC(5,2) AS amount_score
    FROM "doudianKocotree".customer_half_year_sales
), scored AS (
    SELECT *, ROUND(count_score * 0.40 + amount_score * 0.60, 2)::NUMERIC(5,2) AS score
    FROM component_scores
)
INSERT INTO "doudianKocotree".customer_health_detail (
    period_start,
    period_end,
    customer_id,
    half_year_purchase_count,
    half_year_purchase_amount,
    customer_health_score,
    customer_health_status,
    state_instructions,
    follow_up_action
)
SELECT
    period_start,
    period_end,
    customer_id,
    half_year_purchase_count,
    half_year_purchase_amount,
    score,
    CASE
        WHEN score >= 90 THEN '高活跃'
        WHEN score >= 80 THEN '活跃'
        WHEN score >= 70 THEN '稳定'
        WHEN score >= 50 THEN '观察'
        WHEN score >= 40 THEN '风险'
        WHEN score >= 20 THEN '流失预警'
        ELSE '流失'
    END,
    NULL::TEXT,
    NULL::TEXT
FROM scored
ORDER BY customer_id, period_start;

-- ============================================================
-- 三、抖店总体半年客户健康度
-- 同一客户同一天同时出现在两家店时，总体拿货次数只计1次。
-- ============================================================

WITH daily_union AS (
    SELECT transaction_date, customer_id
    FROM "doudianChildren".customer_daily_sales
    UNION
    SELECT transaction_date, customer_id
    FROM "doudianKocotree".customer_daily_sales
), periodized_days AS (
    SELECT
        CASE
            WHEN EXTRACT(MONTH FROM transaction_date)::INTEGER BETWEEN 2 AND 7
                THEN MAKE_DATE(EXTRACT(YEAR FROM transaction_date)::INTEGER, 2, 1)
            WHEN EXTRACT(MONTH FROM transaction_date)::INTEGER BETWEEN 8 AND 12
                THEN MAKE_DATE(EXTRACT(YEAR FROM transaction_date)::INTEGER, 8, 1)
            ELSE MAKE_DATE(EXTRACT(YEAR FROM transaction_date)::INTEGER - 1, 8, 1)
        END AS period_start,
        customer_id,
        transaction_date
    FROM daily_union
), purchase_counts AS (
    SELECT
        period_start,
        (period_start + INTERVAL '6 months - 1 day')::DATE AS period_end,
        customer_id,
        COUNT(*)::BIGINT AS half_year_purchase_count
    FROM periodized_days
    GROUP BY period_start, customer_id
), purchase_amounts AS (
    SELECT
        period_start,
        period_end,
        customer_id,
        SUM(half_year_transaction_amount)::NUMERIC(18,2) AS half_year_purchase_amount
    FROM (
        SELECT period_start, period_end, customer_id, half_year_transaction_amount
        FROM "doudianChildren".customer_half_year_sales
        UNION ALL
        SELECT period_start, period_end, customer_id, half_year_transaction_amount
        FROM "doudianKocotree".customer_half_year_sales
    ) store_data
    GROUP BY period_start, period_end, customer_id
), component_scores AS (
    SELECT
        counts.period_start,
        counts.period_end,
        counts.customer_id,
        counts.half_year_purchase_count,
        amounts.half_year_purchase_amount,
        CASE
            WHEN counts.half_year_purchase_count >= 4 THEN 100.00
            WHEN counts.half_year_purchase_count = 3 THEN 80.00
            WHEN counts.half_year_purchase_count BETWEEN 1 AND 2 THEN 60.00
            ELSE 20.00
        END::NUMERIC(5,2) AS count_score,
        CASE
            WHEN amounts.half_year_purchase_amount >= 550000 THEN 100.00
            WHEN amounts.half_year_purchase_amount >= 400000 THEN 80.00
            WHEN amounts.half_year_purchase_amount >= 200000 THEN 70.00
            WHEN amounts.half_year_purchase_amount >= 100000 THEN 60.00
            WHEN amounts.half_year_purchase_amount >= 50000 THEN 40.00
            WHEN amounts.half_year_purchase_amount >= 10000 THEN 20.00
            ELSE 10.00
        END::NUMERIC(5,2) AS amount_score
    FROM purchase_counts counts
    INNER JOIN purchase_amounts amounts
        USING (period_start, period_end, customer_id)
), scored AS (
    SELECT *, ROUND(count_score * 0.40 + amount_score * 0.60, 2)::NUMERIC(5,2) AS score
    FROM component_scores
)
INSERT INTO doudian.half_year_customer_health (
    period_start,
    period_end,
    customer_id,
    half_year_purchase_count,
    half_year_purchase_amount,
    customer_health_score,
    customer_health_status
)
SELECT
    period_start,
    period_end,
    customer_id,
    half_year_purchase_count,
    half_year_purchase_amount,
    score,
    CASE
        WHEN score >= 90 THEN '高活跃'
        WHEN score >= 80 THEN '活跃'
        WHEN score >= 70 THEN '稳定'
        WHEN score >= 50 THEN '观察'
        WHEN score >= 40 THEN '风险'
        WHEN score >= 20 THEN '流失预警'
        ELSE '流失'
    END
FROM scored
ORDER BY customer_id, period_start;

-- ============================================================
-- 四、强制校验：任何一项不一致都会抛错并回滚整个事务
-- ============================================================

DO $validation$
DECLARE
    v_schema TEXT;
    v_diff BIGINT;
    v_violation BIGINT;
BEGIN
    FOREACH v_schema IN ARRAY ARRAY['doudianChildren', 'doudianKocotree']
    LOOP
        -- 日表必须保持“日期 + 客户ID”唯一，否则COUNT(*)不再等于拿货天数。
        EXECUTE FORMAT(
            'SELECT COUNT(*) - COUNT(DISTINCT (transaction_date, customer_id)) FROM %I.customer_daily_sales',
            v_schema
        ) INTO v_violation;
        IF v_violation <> 0 THEN
            RAISE EXCEPTION '% customer_daily_sales存在%条重复业务键', v_schema, v_violation;
        END IF;

        -- 周表逐业务键双向重算。
        EXECUTE FORMAT($sql$
            WITH expected AS (
                SELECT
                    transaction_date - (EXTRACT(ISODOW FROM transaction_date)::INTEGER - 1) AS period_start,
                    transaction_date - (EXTRACT(ISODOW FROM transaction_date)::INTEGER - 1) + 6 AS period_end,
                    customer_id,
                    SUM(transaction_amount)::NUMERIC(18,2) AS transaction_amount,
                    COUNT(*)::BIGINT AS purchase_count
                FROM %1$I.customer_daily_sales
                GROUP BY period_start, period_end, customer_id
            ), differences AS (
                (SELECT period_start, period_end, customer_id, transaction_amount, purchase_count FROM expected
                 EXCEPT
                 SELECT period_start, period_end, customer_id, weekly_transaction_amount, weekly_purchase_count FROM %1$I.customer_weekly_sales)
                UNION ALL
                (SELECT period_start, period_end, customer_id, weekly_transaction_amount, weekly_purchase_count FROM %1$I.customer_weekly_sales
                 EXCEPT
                 SELECT period_start, period_end, customer_id, transaction_amount, purchase_count FROM expected)
            )
            SELECT COUNT(*) FROM differences
        $sql$, v_schema) INTO v_diff;
        IF v_diff <> 0 THEN
            RAISE EXCEPTION '% customer_weekly_sales逐键重算差异=%', v_schema, v_diff;
        END IF;

        EXECUTE FORMAT(
            'SELECT COUNT(*) FROM %I.customer_weekly_sales WHERE weekly_purchase_count > period_end - period_start + 1',
            v_schema
        ) INTO v_violation;
        IF v_violation <> 0 THEN
            RAISE EXCEPTION '% 周拿货次数超过自然周天数，异常行=%', v_schema, v_violation;
        END IF;

        -- 月表逐业务键双向重算。
        EXECUTE FORMAT($sql$
            WITH expected AS (
                SELECT
                    DATE_TRUNC('month', transaction_date)::DATE AS period_start,
                    (DATE_TRUNC('month', transaction_date) + INTERVAL '1 month - 1 day')::DATE AS period_end,
                    customer_id,
                    SUM(transaction_amount)::NUMERIC(18,2) AS transaction_amount,
                    COUNT(*)::BIGINT AS purchase_count
                FROM %1$I.customer_daily_sales
                GROUP BY period_start, period_end, customer_id
            ), differences AS (
                (SELECT period_start, period_end, customer_id, transaction_amount, purchase_count FROM expected
                 EXCEPT
                 SELECT period_start, period_end, customer_id, monthly_transaction_amount, monthly_purchase_count FROM %1$I.customer_monthly_sales)
                UNION ALL
                (SELECT period_start, period_end, customer_id, monthly_transaction_amount, monthly_purchase_count FROM %1$I.customer_monthly_sales
                 EXCEPT
                 SELECT period_start, period_end, customer_id, transaction_amount, purchase_count FROM expected)
            )
            SELECT COUNT(*) FROM differences
        $sql$, v_schema) INTO v_diff;
        IF v_diff <> 0 THEN
            RAISE EXCEPTION '% customer_monthly_sales逐键重算差异=%', v_schema, v_diff;
        END IF;

        EXECUTE FORMAT(
            'SELECT COUNT(*) FROM %I.customer_monthly_sales WHERE monthly_purchase_count > period_end - period_start + 1',
            v_schema
        ) INTO v_violation;
        IF v_violation <> 0 THEN
            RAISE EXCEPTION '% 月拿货次数超过自然月天数，异常行=%', v_schema, v_violation;
        END IF;

        -- 季度、半年表验证次数不会超过周期自然日数，金额与次数从日表全量对账。
        EXECUTE FORMAT(
            'SELECT COUNT(*) FROM %I.customer_quarterly_sales WHERE quarterly_purchase_count > period_end - period_start + 1',
            v_schema
        ) INTO v_violation;
        IF v_violation <> 0 THEN
            RAISE EXCEPTION '% 季度拿货次数超过周期天数，异常行=%', v_schema, v_violation;
        END IF;

        EXECUTE FORMAT(
            'SELECT COUNT(*) FROM %I.customer_half_year_sales WHERE half_year_purchase_count > period_end - period_start + 1',
            v_schema
        ) INTO v_violation;
        IF v_violation <> 0 THEN
            RAISE EXCEPTION '% 半年拿货次数超过周期天数，异常行=%', v_schema, v_violation;
        END IF;

        EXECUTE FORMAT($sql$
            WITH expected AS (
                SELECT
                    period_start,
                    (period_start + INTERVAL '3 months - 1 day')::DATE AS period_end,
                    customer_id,
                    SUM(transaction_amount)::NUMERIC(18,2) AS transaction_amount,
                    COUNT(*)::BIGINT AS purchase_count
                FROM (
                    SELECT
                        CASE
                            WHEN EXTRACT(MONTH FROM transaction_date)::INTEGER BETWEEN 2 AND 4 THEN MAKE_DATE(EXTRACT(YEAR FROM transaction_date)::INTEGER, 2, 1)
                            WHEN EXTRACT(MONTH FROM transaction_date)::INTEGER BETWEEN 5 AND 7 THEN MAKE_DATE(EXTRACT(YEAR FROM transaction_date)::INTEGER, 5, 1)
                            WHEN EXTRACT(MONTH FROM transaction_date)::INTEGER BETWEEN 8 AND 10 THEN MAKE_DATE(EXTRACT(YEAR FROM transaction_date)::INTEGER, 8, 1)
                            WHEN EXTRACT(MONTH FROM transaction_date)::INTEGER IN (11,12) THEN MAKE_DATE(EXTRACT(YEAR FROM transaction_date)::INTEGER, 11, 1)
                            ELSE MAKE_DATE(EXTRACT(YEAR FROM transaction_date)::INTEGER - 1, 11, 1)
                        END AS period_start,
                        customer_id,
                        transaction_amount
                    FROM %1$I.customer_daily_sales
                ) source_data
                GROUP BY period_start, customer_id
            ), differences AS (
                (SELECT period_start, period_end, customer_id, transaction_amount, purchase_count FROM expected
                 EXCEPT
                 SELECT period_start, period_end, customer_id, quarterly_transaction_amount, quarterly_purchase_count FROM %1$I.customer_quarterly_sales)
                UNION ALL
                (SELECT period_start, period_end, customer_id, quarterly_transaction_amount, quarterly_purchase_count FROM %1$I.customer_quarterly_sales
                 EXCEPT
                 SELECT period_start, period_end, customer_id, transaction_amount, purchase_count FROM expected)
            )
            SELECT COUNT(*) FROM differences
        $sql$, v_schema) INTO v_diff;
        IF v_diff <> 0 THEN
            RAISE EXCEPTION '% customer_quarterly_sales逐键重算差异=%', v_schema, v_diff;
        END IF;

        EXECUTE FORMAT($sql$
            WITH expected AS (
                SELECT
                    period_start,
                    (period_start + INTERVAL '6 months - 1 day')::DATE AS period_end,
                    customer_id,
                    SUM(transaction_amount)::NUMERIC(18,2) AS transaction_amount,
                    COUNT(*)::BIGINT AS purchase_count
                FROM (
                    SELECT
                        CASE
                            WHEN EXTRACT(MONTH FROM transaction_date)::INTEGER BETWEEN 2 AND 7 THEN MAKE_DATE(EXTRACT(YEAR FROM transaction_date)::INTEGER, 2, 1)
                            WHEN EXTRACT(MONTH FROM transaction_date)::INTEGER BETWEEN 8 AND 12 THEN MAKE_DATE(EXTRACT(YEAR FROM transaction_date)::INTEGER, 8, 1)
                            ELSE MAKE_DATE(EXTRACT(YEAR FROM transaction_date)::INTEGER - 1, 8, 1)
                        END AS period_start,
                        customer_id,
                        transaction_amount
                    FROM %1$I.customer_daily_sales
                ) source_data
                GROUP BY period_start, customer_id
            ), differences AS (
                (SELECT period_start, period_end, customer_id, transaction_amount, purchase_count FROM expected
                 EXCEPT
                 SELECT period_start, period_end, customer_id, half_year_transaction_amount, half_year_purchase_count FROM %1$I.customer_half_year_sales)
                UNION ALL
                (SELECT period_start, period_end, customer_id, half_year_transaction_amount, half_year_purchase_count FROM %1$I.customer_half_year_sales
                 EXCEPT
                 SELECT period_start, period_end, customer_id, transaction_amount, purchase_count FROM expected)
            )
            SELECT COUNT(*) FROM differences
        $sql$, v_schema) INTO v_diff;
        IF v_diff <> 0 THEN
            RAISE EXCEPTION '% customer_half_year_sales逐键重算差异=%', v_schema, v_diff;
        END IF;

        -- 店铺健康度必须与修正后的半年表逐行一致，且评分仍使用当前抖店规则。
        EXECUTE FORMAT($sql$
            WITH expected AS (
                SELECT
                    period_start,
                    period_end,
                    customer_id,
                    half_year_purchase_count,
                    half_year_transaction_amount AS half_year_purchase_amount,
                    ROUND(
                        (CASE WHEN half_year_purchase_count >= 4 THEN 100 WHEN half_year_purchase_count = 3 THEN 80 WHEN half_year_purchase_count BETWEEN 1 AND 2 THEN 60 ELSE 20 END) * 0.40
                      + (CASE WHEN half_year_transaction_amount >= 550000 THEN 100 WHEN half_year_transaction_amount >= 400000 THEN 80 WHEN half_year_transaction_amount >= 200000 THEN 70 WHEN half_year_transaction_amount >= 100000 THEN 60 WHEN half_year_transaction_amount >= 50000 THEN 40 WHEN half_year_transaction_amount >= 10000 THEN 20 ELSE 10 END) * 0.60,
                        2
                    )::NUMERIC(5,2) AS score
                FROM %1$I.customer_half_year_sales
            ), expected_status AS (
                SELECT *, CASE WHEN score >= 90 THEN '高活跃' WHEN score >= 80 THEN '活跃' WHEN score >= 70 THEN '稳定' WHEN score >= 50 THEN '观察' WHEN score >= 40 THEN '风险' WHEN score >= 20 THEN '流失预警' ELSE '流失' END AS status
                FROM expected
            ), differences AS (
                (SELECT period_start, period_end, customer_id, half_year_purchase_count, half_year_purchase_amount, score, status FROM expected_status
                 EXCEPT
                 SELECT period_start, period_end, customer_id, half_year_purchase_count, half_year_purchase_amount, customer_health_score, customer_health_status FROM %1$I.customer_health_detail)
                UNION ALL
                (SELECT period_start, period_end, customer_id, half_year_purchase_count, half_year_purchase_amount, customer_health_score, customer_health_status FROM %1$I.customer_health_detail
                 EXCEPT
                 SELECT period_start, period_end, customer_id, half_year_purchase_count, half_year_purchase_amount, score, status FROM expected_status)
            )
            SELECT COUNT(*) FROM differences
        $sql$, v_schema) INTO v_diff;
        IF v_diff <> 0 THEN
            RAISE EXCEPTION '% customer_health_detail逐键评分差异=%', v_schema, v_diff;
        END IF;

        EXECUTE FORMAT(
            'SELECT COUNT(*) FROM %I.customer_health_detail WHERE state_instructions IS NOT NULL OR follow_up_action IS NOT NULL',
            v_schema
        ) INTO v_violation;
        IF v_violation <> 0 THEN
            RAISE EXCEPTION '% customer_health_detail说明字段非空，异常行=%', v_schema, v_violation;
        END IF;
    END LOOP;

    -- 总体健康度的拿货次数按两家店合并后的“客户 + 日期”去重。
    WITH expected_counts AS (
        SELECT
            period_start,
            (period_start + INTERVAL '6 months - 1 day')::DATE AS period_end,
            customer_id,
            COUNT(*)::BIGINT AS purchase_count
        FROM (
            SELECT
                CASE
                    WHEN EXTRACT(MONTH FROM transaction_date)::INTEGER BETWEEN 2 AND 7 THEN MAKE_DATE(EXTRACT(YEAR FROM transaction_date)::INTEGER, 2, 1)
                    WHEN EXTRACT(MONTH FROM transaction_date)::INTEGER BETWEEN 8 AND 12 THEN MAKE_DATE(EXTRACT(YEAR FROM transaction_date)::INTEGER, 8, 1)
                    ELSE MAKE_DATE(EXTRACT(YEAR FROM transaction_date)::INTEGER - 1, 8, 1)
                END AS period_start,
                customer_id,
                transaction_date
            FROM (
                SELECT transaction_date, customer_id FROM "doudianChildren".customer_daily_sales
                UNION
                SELECT transaction_date, customer_id FROM "doudianKocotree".customer_daily_sales
            ) daily_union
        ) periodized
        GROUP BY period_start, customer_id
    )
    SELECT COUNT(*) INTO v_diff
    FROM expected_counts expected
    FULL OUTER JOIN doudian.half_year_customer_health target
        USING (period_start, period_end, customer_id)
    WHERE expected.period_start IS NULL
       OR target.period_start IS NULL
       OR expected.purchase_count <> target.half_year_purchase_count;

    IF v_diff <> 0 THEN
        RAISE EXCEPTION 'doudian.half_year_customer_health拿货次数重算差异=%', v_diff;
    END IF;

    SELECT COUNT(*) INTO v_violation
    FROM doudian.half_year_customer_health
    WHERE half_year_purchase_count > period_end - period_start + 1;

    IF v_violation <> 0 THEN
        RAISE EXCEPTION 'doudian总体半年拿货次数超过周期天数，异常行=%', v_violation;
    END IF;
END
$validation$;

COMMIT;

-- 提交后摘要。
SELECT 'doudianChildren' AS schema_name,
       (SELECT COUNT(*) FROM "doudianChildren".customer_weekly_sales) AS weekly_rows,
       (SELECT MAX(weekly_purchase_count) FROM "doudianChildren".customer_weekly_sales) AS weekly_max,
       (SELECT COUNT(*) FROM "doudianChildren".customer_monthly_sales) AS monthly_rows,
       (SELECT MAX(monthly_purchase_count) FROM "doudianChildren".customer_monthly_sales) AS monthly_max,
       (SELECT COUNT(*) FROM "doudianChildren".customer_quarterly_sales) AS quarterly_rows,
       (SELECT MAX(quarterly_purchase_count) FROM "doudianChildren".customer_quarterly_sales) AS quarterly_max,
       (SELECT COUNT(*) FROM "doudianChildren".customer_half_year_sales) AS half_year_rows,
       (SELECT MAX(half_year_purchase_count) FROM "doudianChildren".customer_half_year_sales) AS half_year_max,
       (SELECT COUNT(*) FROM "doudianChildren".customer_health_detail) AS health_rows
UNION ALL
SELECT 'doudianKocotree',
       (SELECT COUNT(*) FROM "doudianKocotree".customer_weekly_sales),
       (SELECT MAX(weekly_purchase_count) FROM "doudianKocotree".customer_weekly_sales),
       (SELECT COUNT(*) FROM "doudianKocotree".customer_monthly_sales),
       (SELECT MAX(monthly_purchase_count) FROM "doudianKocotree".customer_monthly_sales),
       (SELECT COUNT(*) FROM "doudianKocotree".customer_quarterly_sales),
       (SELECT MAX(quarterly_purchase_count) FROM "doudianKocotree".customer_quarterly_sales),
       (SELECT COUNT(*) FROM "doudianKocotree".customer_half_year_sales),
       (SELECT MAX(half_year_purchase_count) FROM "doudianKocotree".customer_half_year_sales),
       (SELECT COUNT(*) FROM "doudianKocotree".customer_health_detail);

SELECT
    'doudian' AS schema_name,
    COUNT(*) AS health_rows,
    MAX(half_year_purchase_count) AS half_year_max,
    SUM(half_year_purchase_amount)::NUMERIC(18,2) AS total_amount
FROM doudian.half_year_customer_health;
