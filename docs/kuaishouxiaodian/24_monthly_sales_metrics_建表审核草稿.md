# 快手小店第24张表审核草稿：`kuaishouxiaodian.monthly_sales_metrics`

> 状态：已确认，已建表，已上传数据，已校验  
> 数据库：`weidian`  
> Schema：`kuaishouxiaodian`  
> 表序号：24 / 35  
> 上游：`kuaishouxiaodian.monthly_sales`  
> 设计基准：`hh.monthly_sales_metrics`正式结构、《数据库英文命名映射修正版》和《AI看板-表结构最终版》  
> 样例说明：以下业务指标、`id`、`created_at`和`updated_at`均来自正式数据库查询。

## 1. 表的作用

`monthly_sales_metrics`用于保存每个自然月的月销售金额和月环比。一条记录代表一个自然月的整体销售指标。

本表是第10张`monthly_sales`的二次开发表，不重新读取原始Excel，也不重新判断订单有效性。

## 2. 与微店结构及两位小数规则的关系

- 表名、字段顺序和字段名称对照`hh.monthly_sales_metrics`正式结构。
- 快手小店本表严格保留7个字段，不保存“上月交易金额”。
- 微店参考表的环比字段是`NUMERIC(12,6)`；根据最新统一规则，本表已按`NUMERIC(12,2)`建成。
- 所有同比、环比等比例指标统一保留2位小数。
- 快手小店没有预售相关逻辑，本表不增加预售字段。

## 3. 数据粒度与唯一性

- 数据粒度：一个自然月。
- 自然月：每月1日至该月最后一天。
- 主键：`id`。
- 业务唯一键：`period_start + period_end`。
- 每条`monthly_sales`记录在本表中必须且只能对应一条记录。
- 上游没有某个自然月记录时，本表不生成金额为0的补零记录。

## 4. 字段设计

本表严格保留以下7个字段：

| 序号 | 字段 | PostgreSQL类型 | 是否必填 | 默认值 | 说明 |
|---:|---|---|---|---|---|
| 1 | `id` | `BIGINT` | 是 | 自增 | 主键，由数据库自动生成 |
| 2 | `period_start` | `DATE` | 是 | 无 | 自然月第一天 |
| 3 | `period_end` | `DATE` | 是 | 无 | 自然月最后一天 |
| 4 | `monthly_transaction_amount` | `NUMERIC(18,2)` | 是 | `0` | 直接继承该自然月的毛销售额 |
| 5 | `month_over_month_rate` | `NUMERIC(12,2)` | 否 | `NULL` | 月环比比率，统一保留2位小数；缺少上月记录时写`0.00` |
| 6 | `created_at` | `TIMESTAMPTZ` | 是 | `CURRENT_TIMESTAMP` | 首次插入数据库的北京时间 |
| 7 | `updated_at` | `TIMESTAMPTZ` | 是 | `CURRENT_TIMESTAMP` | 最近刷新记录的北京时间 |

`month_over_month_rate`的可空属性与微店正式结构保持一致；正式生成SQL会对缺少上月或上月金额为0的情况写入`0.00`，因此当前预计算没有空值。

## 5. 数据来源与字段映射

| 目标字段 | 上游字段或来源 | 处理方式 |
|---|---|---|
| `id` | 数据库Identity | 正式插入时自增生成 |
| `period_start` | `monthly_sales.period_start` | 原值继承 |
| `period_end` | `monthly_sales.period_end` | 原值继承 |
| `monthly_transaction_amount` | `monthly_sales.monthly_transaction_amount` | 原值继承，不重复聚合 |
| `month_over_month_rate` | 本月金额、上一个自然月金额 | 按第7节公式计算并保留2位小数 |
| `created_at` | 数据库当前时间 | 正式插入时按北京时间生成 |
| `updated_at` | 数据库当前时间 | 正式插入时按北京时间生成 |

## 6. 必须继承的业务口径

- 完全继承第10张`monthly_sales`的自然月、有效销售、交易金额和渠道口径。
- `monthly_transaction_amount`为有效订单`实付款`形成的毛销售额，不直接扣减退款。
- 本表包含全部渠道，不增加`渠道 = '分销'`筛选。
- 不从月退款、月商品或月客户表计算环比。
- 不重新按原始订单聚合，避免指标表与第10张表的销售口径漂移。

## 7. 月环比计算规则

### 7.1 上一个自然月的匹配

上月必须按自然月边界严格匹配：

```text
上月period_start = 本月period_start向前推1个月
上月period_end   = 本月period_start向前推1天
```

例如，本月为2026-03-01至2026-03-31，则上月只能是2026-02-01至2026-02-28。不能简单读取数据库中的上一条记录；如果中间缺少一个自然月，则当前月的上月记录视为不存在。

### 7.2 环比公式和保存单位

```text
如果上月记录不存在，或上月交易金额为0：
    month_over_month_rate = 0.00

否则：
    month_over_month_rate
    = (本月交易金额 - 上月交易金额)
      / 上月交易金额
```

- 结果四舍五入保留2位小数。
- 本字段沿用微店正式表的“小数比率”口径，不额外乘100。
- 例如`0.25`表示本月比上月增长25%，`-0.20`表示下降20%，`10.58`表示增长约1,058%。
- “上月交易金额”只用于计算，不保存到目标表。

## 8. 生成流程

```text
读取monthly_sales全部正式记录
→ 每个自然月保留一条基础记录
→ 严格左连接对应的上一个自然月
→ 计算month_over_month_rate并保留2位小数
→ 按period_start升序写入目标表
→ 数据库生成id、created_at和updated_at
```

## 9. 正式执行结果

| 检查项目 | 结果 |
|---|---:|
| 正式记录数 | 18条 |
| 不同自然月 | 18个月 |
| 最早月开始日期 | 2025-02-01 |
| 最晚月结束日期 | 2026-07-31 |
| `monthly_transaction_amount`合计 | 6,254,453.47 |
| 存在严格上一个自然月记录 | 17条 |
| 缺少上一个自然月、环比写0.00 | 1条 |
| 环比为0.00 | 1条 |
| 非0环比 | 17条 |
| 环比最小值 | -0.64 |
| 环比最大值 | 21.25 |
| 必填业务指标空值 | 0条 |
| 自然月边界错误 | 0条 |
| 重复业务周期 | 0组 |

## 10. 基于真实上游数据的完整字段样例

| `id` | `period_start` | `period_end` | `monthly_transaction_amount` | `month_over_month_rate` | `created_at` | `updated_at` |
|---:|---|---|---:|---:|---|---|
| 1 | 2025-02-01 | 2025-02-28 | 89,675.20 | 0.00 | 2026-08-10 13:13:37.57043+08 | 2026-08-10 13:13:37.57043+08 |
| 2 | 2025-03-01 | 2025-03-31 | 1,038,595.01 | 10.58 | 2026-08-10 13:13:37.57043+08 | 2026-08-10 13:13:37.57043+08 |
| 6 | 2025-07-01 | 2025-07-31 | 334,037.01 | -0.25 | 2026-08-10 13:13:37.57043+08 | 2026-08-10 13:13:37.57043+08 |
| 11 | 2025-12-01 | 2025-12-31 | 95,736.50 | 0.79 | 2026-08-10 13:13:37.57043+08 | 2026-08-10 13:13:37.57043+08 |
| 12 | 2026-01-01 | 2026-01-31 | 54,267.70 | -0.43 | 2026-08-10 13:13:37.57043+08 | 2026-08-10 13:13:37.57043+08 |
| 16 | 2026-05-01 | 2026-05-31 | 234,047.60 | -0.55 | 2026-08-10 13:13:37.57043+08 | 2026-08-10 13:13:37.57043+08 |
| 18 | 2026-07-01 | 2026-07-31 | 113,657.47 | 0.34 | 2026-08-10 13:13:37.57043+08 | 2026-08-10 13:13:37.57043+08 |

以上样例完整列出7个目标字段，全部来自正式表，未省略任何字段。

## 11. 指标关系说明

- 本表月金额合计必须与`monthly_sales`一致，当前均为6,254,453.47。
- 环比是每个自然月相对于严格上一个自然月的比率，不能跨月相加。
- 某月金额发生变化时，该月环比和下一个自然月环比都会受到影响。
- 本表不修改月销售额、月退款额、月商品销售额或月客户销售额。

## 12. 已执行建表SQL

```sql
CREATE TABLE kuaishouxiaodian.monthly_sales_metrics (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    monthly_transaction_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    month_over_month_rate NUMERIC(12,2),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT monthly_sales_metrics_period_check CHECK (
        period_start = DATE_TRUNC('month', period_start)::DATE
        AND period_end =
            (
                period_start
                + INTERVAL '1 month'
                - INTERVAL '1 day'
            )::DATE
    ),
    CONSTRAINT monthly_sales_metrics_business_uk UNIQUE (
        period_start,
        period_end
    )
);

ALTER TABLE kuaishouxiaodian.monthly_sales_metrics OWNER TO root;
```

## 13. 首次数据生成SQL

```sql
INSERT INTO kuaishouxiaodian.monthly_sales_metrics (
    period_start,
    period_end,
    monthly_transaction_amount,
    month_over_month_rate
)
SELECT
    current_month.period_start,
    current_month.period_end,
    current_month.monthly_transaction_amount,
    CASE
        WHEN previous_month.monthly_transaction_amount IS NULL
          OR previous_month.monthly_transaction_amount = 0
            THEN 0::NUMERIC(12,2)
        ELSE ROUND(
            (
                current_month.monthly_transaction_amount
                - previous_month.monthly_transaction_amount
            ) / previous_month.monthly_transaction_amount,
            2
        )::NUMERIC(12,2)
    END AS month_over_month_rate
FROM kuaishouxiaodian.monthly_sales AS current_month
LEFT JOIN kuaishouxiaodian.monthly_sales AS previous_month
  ON previous_month.period_start =
        (current_month.period_start - INTERVAL '1 month')::DATE
 AND previous_month.period_end =
        (current_month.period_start - INTERVAL '1 day')::DATE
ORDER BY current_month.period_start;
```

## 14. 已执行的原子建表与上传流程

1. 开启PostgreSQL事务，并执行`SET LOCAL TIME ZONE 'Asia/Shanghai'`。
2. 确认目标表不存在，并校验`monthly_sales`的字段、自然月、唯一性和金额。
3. 创建目标表并将所有者设为`root`。
4. 从`monthly_sales`全量计算月环比。
5. 按`period_start`升序一次性写入全部记录。
6. 校验字段数、记录数、周期范围、唯一键、两位小数、金额、环比和逐周期重算结果。
7. 全部断言通过后提交；任一步失败则回滚建表和全部数据写入。

## 15. 后续上游变化时的刷新逻辑

一条月销售记录会影响本月和下一个自然月的环比。当前仅18条记录，为避免漏刷依赖周期，与上游变更在同一事务内全量刷新：

```text
monthly_sales完成新增或更新
→ 在临时结果中全量重算monthly_sales_metrics
→ 校验记录数、周期、金额和环比
→ 替换目标表全部旧记录
→ 校验目标表与临时结果逐月一致
→ 与上游变化一次性提交
```

## 16. 正式上传验证结果

- 表字段数必须为7个，字段名称、顺序和类型必须与第4节一致。
- `month_over_month_rate`必须为`NUMERIC(12,2)`。
- 当前数据下记录数必须为18条，不同自然月必须为18个月。
- 最早月开始日期必须为2025-02-01，最晚月结束日期必须为2026-07-31。
- 月金额合计必须为6,254,453.47，并与`monthly_sales`完全一致。
- 严格存在上一个自然月的记录必须为17条；缺少上月记录并写入0.00的记录必须为1条。
- 环比为0.00的记录必须为1条，非0环比必须为17条。
- 环比最小值必须为-0.64，最大值必须为21.25。
- 必填字段空值、生成结果中的空环比、错误自然月和重复业务键必须均为0。
- 每条月金额和环比必须与第13节逻辑逐周期重算一致，差异必须为0。
- 第10节的5个业务字段必须与正式记录一致；正式上传后再更新实际`id`和时间字段。
- 表所有者必须为`root`。

## 17. 逐业务键全量重算校验SQL

```sql
WITH expected AS (
    SELECT
        current_month.period_start,
        current_month.period_end,
        current_month.monthly_transaction_amount,
        CASE
            WHEN previous_month.monthly_transaction_amount IS NULL
              OR previous_month.monthly_transaction_amount = 0
                THEN 0::NUMERIC(12,2)
            ELSE ROUND(
                (
                    current_month.monthly_transaction_amount
                    - previous_month.monthly_transaction_amount
                ) / previous_month.monthly_transaction_amount,
                2
            )::NUMERIC(12,2)
        END AS month_over_month_rate
    FROM kuaishouxiaodian.monthly_sales AS current_month
    LEFT JOIN kuaishouxiaodian.monthly_sales AS previous_month
      ON previous_month.period_start =
            (current_month.period_start - INTERVAL '1 month')::DATE
     AND previous_month.period_end =
            (current_month.period_start - INTERVAL '1 day')::DATE
)
SELECT COUNT(*) AS mismatched_month_rows
FROM expected AS e
FULL OUTER JOIN kuaishouxiaodian.monthly_sales_metrics AS a
  USING (period_start, period_end)
WHERE e.monthly_transaction_amount
          IS DISTINCT FROM a.monthly_transaction_amount
   OR e.month_over_month_rate
          IS DISTINCT FROM a.month_over_month_rate;
```

正式上传后`mismatched_month_rows`实际为0。

## 18. 用户审核确认项

- [x] 确认本表严格保留7个字段，不保存“上月交易金额”。
- [x] 确认自然月为每月1日至该月最后一天。
- [x] 确认上一个自然月必须按日历边界严格匹配，不按上一条记录匹配。
- [x] 确认月环比沿用小数比率口径，不额外乘100。
- [x] 确认月环比统一保留2位小数，字段类型为`NUMERIC(12,2)`。
- [x] 确认缺少上月记录或上月金额为0时，月环比写`0.00`。
- [x] 确认本表包含全部渠道，保存毛销售额，不扣减退款。
- [x] 确认快手小店无预售逻辑，本表不增加预售字段。
- [x] 确认后续上游变化时在同一事务内全量重算，任一步失败全部回滚。
- [x] 确认第9节正式结果和第10节完整字段样例已通过正式上传校验。

## 19. 用户修改区

请直接在下方填写需要修改的内容：

```text
无。
```

## 20. 实际执行与校验记录

- 正式执行时间：2026-08-10 13:13:37.57043+08（北京时间）。
- 执行方式：在一个PostgreSQL事务内完成上游基线校验、建表、所有者设置、18条数据写入和强制断言；全部通过后一次性提交。
- 正式表：`kuaishouxiaodian.monthly_sales_metrics`，所有者为`root`。
- 正式结果：18条记录、18个自然月，日期范围2025-02-01至2026-07-31，月金额合计6,254,453.47。
- 环比结果：1条为0.00、17条非0，最小值-0.64、最大值21.25，字段类型为`NUMERIC(12,2)`。
- 数据质量：必填字段空值0条、空环比0条、自然月边界错误0条、重复业务键0组。
- 依赖校验：严格存在上一个自然月17条、缺少上一个自然月1条；逐业务键全量重算差异0条。
- 提交后再次在独立连接中运行验证SQL，全部断言通过。
