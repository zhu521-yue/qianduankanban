\set ON_ERROR_STOP on

BEGIN;
SET LOCAL TIME ZONE 'Asia/Shanghai';

LOCK TABLE
    "doudianChildren".weekly_refunds,
    "doudianChildren".monthly_refunds,
    "doudianChildren".quarterly_refunds,
    "doudianChildren".half_year_refunds,
    "doudianKocotree".weekly_refunds,
    "doudianKocotree".monthly_refunds,
    "doudianKocotree".quarterly_refunds,
    "doudianKocotree".half_year_refunds
IN SHARE MODE;

CREATE TABLE doudian.weekly_refunds_summary (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    weekly_refund_amount NUMERIC(18,2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_weekly_refunds_summary_period UNIQUE (period_start, period_end),
    CONSTRAINT ck_weekly_refunds_summary_boundary CHECK (
        EXTRACT(ISODOW FROM period_start) = 1
        AND period_end = period_start + 6
    ),
    CONSTRAINT ck_weekly_refunds_summary_amount CHECK (weekly_refund_amount >= 0)
);

CREATE TABLE doudian.monthly_refunds_summary (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    monthly_refund_amount NUMERIC(18,2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_monthly_refunds_summary_period UNIQUE (period_start, period_end),
    CONSTRAINT ck_monthly_refunds_summary_boundary CHECK (
        period_start = DATE_TRUNC('month', period_start)::DATE
        AND period_end = (period_start + INTERVAL '1 month - 1 day')::DATE
    ),
    CONSTRAINT ck_monthly_refunds_summary_amount CHECK (monthly_refund_amount >= 0)
);

CREATE TABLE doudian.quarterly_refunds_summary (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    quarterly_refund_amount NUMERIC(18,2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_quarterly_refunds_summary_period UNIQUE (period_start, period_end),
    CONSTRAINT ck_quarterly_refunds_summary_boundary CHECK (
        EXTRACT(DAY FROM period_start) = 1
        AND EXTRACT(MONTH FROM period_start) IN (2, 5, 8, 11)
        AND period_end = (period_start + INTERVAL '3 months - 1 day')::DATE
    ),
    CONSTRAINT ck_quarterly_refunds_summary_amount CHECK (quarterly_refund_amount >= 0)
);

CREATE TABLE doudian.half_year_refunds_summary (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    half_year_refund_amount NUMERIC(18,2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_half_year_refunds_summary_period UNIQUE (period_start, period_end),
    CONSTRAINT ck_half_year_refunds_summary_boundary CHECK (
        EXTRACT(DAY FROM period_start) = 1
        AND EXTRACT(MONTH FROM period_start) IN (2, 8)
        AND period_end = (period_start + INTERVAL '6 months - 1 day')::DATE
    ),
    CONSTRAINT ck_half_year_refunds_summary_amount CHECK (half_year_refund_amount >= 0)
);

ALTER TABLE doudian.weekly_refunds_summary OWNER TO root;
ALTER TABLE doudian.monthly_refunds_summary OWNER TO root;
ALTER TABLE doudian.quarterly_refunds_summary OWNER TO root;
ALTER TABLE doudian.half_year_refunds_summary OWNER TO root;

COMMENT ON TABLE doudian.weekly_refunds_summary IS '抖店两家店按自然周合并的退款金额';
COMMENT ON TABLE doudian.monthly_refunds_summary IS '抖店两家店按自然月合并的退款金额';
COMMENT ON TABLE doudian.quarterly_refunds_summary IS '抖店两家店按业务季度合并的退款金额';
COMMENT ON TABLE doudian.half_year_refunds_summary IS '抖店两家店按业务半年合并的退款金额';

INSERT INTO doudian.weekly_refunds_summary (
    period_start,
    period_end,
    weekly_refund_amount
)
SELECT
    period_start,
    period_end,
    SUM(weekly_refund_amount)::NUMERIC(18,2)
FROM (
    SELECT period_start, period_end, weekly_refund_amount
    FROM "doudianChildren".weekly_refunds
    UNION ALL
    SELECT period_start, period_end, weekly_refund_amount
    FROM "doudianKocotree".weekly_refunds
) source_rows
GROUP BY period_start, period_end
ORDER BY period_start;

INSERT INTO doudian.monthly_refunds_summary (
    period_start,
    period_end,
    monthly_refund_amount
)
SELECT
    period_start,
    period_end,
    SUM(monthly_refund_amount)::NUMERIC(18,2)
FROM (
    SELECT period_start, period_end, monthly_refund_amount
    FROM "doudianChildren".monthly_refunds
    UNION ALL
    SELECT period_start, period_end, monthly_refund_amount
    FROM "doudianKocotree".monthly_refunds
) source_rows
GROUP BY period_start, period_end
ORDER BY period_start;

INSERT INTO doudian.quarterly_refunds_summary (
    period_start,
    period_end,
    quarterly_refund_amount
)
SELECT
    period_start,
    period_end,
    SUM(quarterly_refund_amount)::NUMERIC(18,2)
FROM (
    SELECT period_start, period_end, quarterly_refund_amount
    FROM "doudianChildren".quarterly_refunds
    UNION ALL
    SELECT period_start, period_end, quarterly_refund_amount
    FROM "doudianKocotree".quarterly_refunds
) source_rows
GROUP BY period_start, period_end
ORDER BY period_start;

INSERT INTO doudian.half_year_refunds_summary (
    period_start,
    period_end,
    half_year_refund_amount
)
SELECT
    period_start,
    period_end,
    SUM(half_year_refund_amount)::NUMERIC(18,2)
FROM (
    SELECT period_start, period_end, half_year_refund_amount
    FROM "doudianChildren".half_year_refunds
    UNION ALL
    SELECT period_start, period_end, half_year_refund_amount
    FROM "doudianKocotree".half_year_refunds
) source_rows
GROUP BY period_start, period_end
ORDER BY period_start;

DO $validation$
DECLARE
    v_table_count INTEGER;
    v_week_total NUMERIC(18,2);
    v_month_total NUMERIC(18,2);
    v_quarter_total NUMERIC(18,2);
    v_half_total NUMERIC(18,2);
BEGIN
    SELECT COUNT(*)
    INTO v_table_count
    FROM information_schema.tables
    WHERE table_schema = 'doudian'
      AND table_type = 'BASE TABLE';

    IF v_table_count <> 11 THEN
        RAISE EXCEPTION 'doudian Schema正式表数量应为11，实际为%', v_table_count;
    END IF;

    IF EXISTS (
        WITH expected AS (
            SELECT period_start, period_end, SUM(weekly_refund_amount)::NUMERIC(18,2) AS amount
            FROM (
                SELECT period_start, period_end, weekly_refund_amount FROM "doudianChildren".weekly_refunds
                UNION ALL
                SELECT period_start, period_end, weekly_refund_amount FROM "doudianKocotree".weekly_refunds
            ) source_rows
            GROUP BY period_start, period_end
        ), differences AS (
            (SELECT period_start, period_end, weekly_refund_amount FROM doudian.weekly_refunds_summary
             EXCEPT
             SELECT period_start, period_end, amount FROM expected)
            UNION ALL
            (SELECT period_start, period_end, amount FROM expected
             EXCEPT
             SELECT period_start, period_end, weekly_refund_amount FROM doudian.weekly_refunds_summary)
        )
        SELECT 1 FROM differences
    ) THEN
        RAISE EXCEPTION 'weekly_refunds_summary与两家店周退款上游存在差异';
    END IF;

    IF EXISTS (
        WITH expected AS (
            SELECT period_start, period_end, SUM(monthly_refund_amount)::NUMERIC(18,2) AS amount
            FROM (
                SELECT period_start, period_end, monthly_refund_amount FROM "doudianChildren".monthly_refunds
                UNION ALL
                SELECT period_start, period_end, monthly_refund_amount FROM "doudianKocotree".monthly_refunds
            ) source_rows
            GROUP BY period_start, period_end
        ), differences AS (
            (SELECT period_start, period_end, monthly_refund_amount FROM doudian.monthly_refunds_summary
             EXCEPT
             SELECT period_start, period_end, amount FROM expected)
            UNION ALL
            (SELECT period_start, period_end, amount FROM expected
             EXCEPT
             SELECT period_start, period_end, monthly_refund_amount FROM doudian.monthly_refunds_summary)
        )
        SELECT 1 FROM differences
    ) THEN
        RAISE EXCEPTION 'monthly_refunds_summary与两家店月退款上游存在差异';
    END IF;

    IF EXISTS (
        WITH expected AS (
            SELECT period_start, period_end, SUM(quarterly_refund_amount)::NUMERIC(18,2) AS amount
            FROM (
                SELECT period_start, period_end, quarterly_refund_amount FROM "doudianChildren".quarterly_refunds
                UNION ALL
                SELECT period_start, period_end, quarterly_refund_amount FROM "doudianKocotree".quarterly_refunds
            ) source_rows
            GROUP BY period_start, period_end
        ), differences AS (
            (SELECT period_start, period_end, quarterly_refund_amount FROM doudian.quarterly_refunds_summary
             EXCEPT
             SELECT period_start, period_end, amount FROM expected)
            UNION ALL
            (SELECT period_start, period_end, amount FROM expected
             EXCEPT
             SELECT period_start, period_end, quarterly_refund_amount FROM doudian.quarterly_refunds_summary)
        )
        SELECT 1 FROM differences
    ) THEN
        RAISE EXCEPTION 'quarterly_refunds_summary与两家店季度退款上游存在差异';
    END IF;

    IF EXISTS (
        WITH expected AS (
            SELECT period_start, period_end, SUM(half_year_refund_amount)::NUMERIC(18,2) AS amount
            FROM (
                SELECT period_start, period_end, half_year_refund_amount FROM "doudianChildren".half_year_refunds
                UNION ALL
                SELECT period_start, period_end, half_year_refund_amount FROM "doudianKocotree".half_year_refunds
            ) source_rows
            GROUP BY period_start, period_end
        ), differences AS (
            (SELECT period_start, period_end, half_year_refund_amount FROM doudian.half_year_refunds_summary
             EXCEPT
             SELECT period_start, period_end, amount FROM expected)
            UNION ALL
            (SELECT period_start, period_end, amount FROM expected
             EXCEPT
             SELECT period_start, period_end, half_year_refund_amount FROM doudian.half_year_refunds_summary)
        )
        SELECT 1 FROM differences
    ) THEN
        RAISE EXCEPTION 'half_year_refunds_summary与两家店半年退款上游存在差异';
    END IF;

    SELECT SUM(weekly_refund_amount) INTO v_week_total FROM doudian.weekly_refunds_summary;
    SELECT SUM(monthly_refund_amount) INTO v_month_total FROM doudian.monthly_refunds_summary;
    SELECT SUM(quarterly_refund_amount) INTO v_quarter_total FROM doudian.quarterly_refunds_summary;
    SELECT SUM(half_year_refund_amount) INTO v_half_total FROM doudian.half_year_refunds_summary;

    IF v_week_total IS DISTINCT FROM v_month_total
       OR v_week_total IS DISTINCT FROM v_quarter_total
       OR v_week_total IS DISTINCT FROM v_half_total THEN
        RAISE EXCEPTION '四种周期退款总额不一致：周%，月%，季度%，半年%',
            v_week_total, v_month_total, v_quarter_total, v_half_total;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_class table_class
        JOIN pg_namespace schema_namespace ON schema_namespace.oid = table_class.relnamespace
        WHERE schema_namespace.nspname = 'doudian'
          AND table_class.relname IN (
              'weekly_refunds_summary',
              'monthly_refunds_summary',
              'quarterly_refunds_summary',
              'half_year_refunds_summary'
          )
          AND pg_get_userbyid(table_class.relowner) <> 'root'
    ) THEN
        RAISE EXCEPTION '新增退款汇总表OWNER必须全部为root';
    END IF;
END
$validation$;

COMMIT;
