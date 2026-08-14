BEGIN;

-- 抖店平台级健康表原先只有分数和状态。客户状态规则保存需要与其他
-- 组级、平台级、店铺级健康表保持一致，因此补齐说明和跟进动作字段。
ALTER TABLE doudian.half_year_customer_health
    ADD COLUMN IF NOT EXISTS state_instructions TEXT,
    ADD COLUMN IF NOT EXISTS follow_up_action TEXT;

COMMIT;
