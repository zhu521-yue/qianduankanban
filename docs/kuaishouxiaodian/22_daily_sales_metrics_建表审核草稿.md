# 快手小店第22张表审核草稿：`kuaishouxiaodian.daily_sales_metrics`

> 状态：已确认、已建表、已上传、已校验  
> 数据库：`weidian`  
> Schema：`kuaishouxiaodian`  
> 表序号：22 / 35  
> 上游：`kuaishouxiaodian.daily_sales`  
> 设计基准：`hh.daily_sales_metrics`正式结构、《数据库英文命名映射修正版》和《AI看板-表结构最终版》  
> 样例说明：本文样例直接查询正式表，完整包含全部8个字段。

## 1. 表的作用

`daily_sales_metrics`用于保存快手小店每个有销售记录的自然日对应的当日销售金额、同比、近7日交易额和近30日交易额。一条记录代表“一个交易日期”的整体销售指标，供销售指标卡片和日趋势查询使用。

本表是`daily_sales`的二次开发表，不重新读取原始Excel，也不重新判断订单有效性。

## 2. 与微店正式结构的对应关系

- 表名沿用英文映射：`daily_sales_metrics`。
- 字段顺序和字段名称对照`hh.daily_sales_metrics`正式结构，共8个字段；根据统一规则，比例字段`year_over_year_rate`调整为`NUMERIC(12,2)`。
- 根据《AI看板-表结构最终版》，同比直接通过当前金额与去年同日金额计算，不保存“去年交易金额”字段。
- 快手小店没有预售相关业务表，本表也不读取、不生成任何预售字段或预售指标。

## 3. 数据粒度与唯一性

- 数据粒度：一个有销售记录的自然日。
- 主键：`id`。
- 业务唯一键：`transaction_date`。
- 每个上游`daily_sales`日期在本表中必须且只能对应一条记录。
- 上游没有某个自然日记录时，本表不主动生成该日金额为0的补零记录。

## 4. 字段设计

本表严格保留以下8个字段，不保存“去年交易金额”或任何预售字段：

| 序号 | 字段 | PostgreSQL类型 | 是否必填 | 默认值 | 说明 |
|---:|---|---|---|---|---|
| 1 | `id` | `BIGINT` | 是 | 自增 | 主键，由数据库自动生成 |
| 2 | `transaction_date` | `DATE` | 是 | 无 | 指标所属交易日期，北京时间自然日 |
| 3 | `transaction_amount` | `NUMERIC(18,2)` | 是 | `0` | 直接继承上游对应日期的销售金额 |
| 4 | `year_over_year_rate` | `NUMERIC(12,2)` | 否 | `NULL` | 同比百分比；统一保留2位小数，无去年同日记录时实际写入`0.00` |
| 5 | `rolling_7_day_transaction_amount` | `NUMERIC(18,2)` | 是 | `0` | 当前日期及向前6个自然日的销售金额之和 |
| 6 | `rolling_30_day_transaction_amount` | `NUMERIC(18,2)` | 是 | `0` | 当前日期及向前29个自然日的销售金额之和 |
| 7 | `created_at` | `TIMESTAMPTZ` | 是 | `CURRENT_TIMESTAMP` | 首次插入数据库的北京时间 |
| 8 | `updated_at` | `TIMESTAMPTZ` | 是 | `CURRENT_TIMESTAMP` | 最近刷新记录的北京时间 |

`year_over_year_rate`的可空属性与`hh.daily_sales_metrics`正式结构保持一致；但本表正式生成SQL会对缺少去年同日记录的情况写入0，因此当前预计算结果中该字段没有空值。

## 5. 数据来源与字段映射

上游数据：`kuaishouxiaodian.daily_sales`。

| 目标字段 | 上游字段或来源 | 处理方式 |
|---|---|---|
| `id` | 数据库Identity | 正式插入时自增生成 |
| `transaction_date` | `daily_sales.transaction_date` | 原值继承，作为唯一业务日期 |
| `transaction_amount` | `daily_sales.transaction_amount` | 原值继承，不重复聚合 |
| `year_over_year_rate` | 当前日金额、去年同日金额 | 按第7节公式计算；去年同日不存在或金额为0时写0 |
| `rolling_7_day_transaction_amount` | `daily_sales.transaction_amount` | 汇总`transaction_date - 6`至`transaction_date`的记录 |
| `rolling_30_day_transaction_amount` | `daily_sales.transaction_amount` | 汇总`transaction_date - 29`至`transaction_date`的记录 |
| `created_at` | 数据库当前时间 | 正式插入时按北京时间生成 |
| `updated_at` | 数据库当前时间 | 正式插入时按北京时间生成 |

## 6. 必须继承的业务口径

- 完全继承第3张`daily_sales`已经确认的有效销售、交易日期和金额口径。
- `transaction_amount`使用原始订单的`实付款`汇总结果；当前上游已经完成订单状态筛选和按日聚合。
- 本表属于整体销售指标，包含全部渠道，不增加`渠道 = '分销'`筛选；分销筛选只用于客户相关表。
- 本表保存毛销售额，不在表内扣减退款；退款数据由退款表独立保存。
- 不重复读取`raw_data`，避免日销售口径在综合表中发生漂移。
- 快手小店无预售相关逻辑，本表不依赖预售字段或预售表。
- 当前上游只保存有有效销售的日期；没有记录的日期在滚动窗口中等价于贡献0，但不会在目标表中额外生成一行。

## 7. 指标计算规则

### 7.1 同比

先查找当前交易日期的去年同月同日记录。

```text
如果去年同日记录不存在，或去年同日金额为0：
    year_over_year_rate = 0.00

否则：
    year_over_year_rate
    = (当日交易金额 - 去年同日交易金额)
      / 去年同日交易金额
      × 100
```

- 结果保留2位小数。
- 本字段保存的是百分比数值。例如`-88.31`表示同比下降88.31%，不是小数`-0.8831`。
- 2月29日只有在上一年度也存在完全相同的2月29日日期时才可匹配；没有完全相同日期时按0处理，不错误映射到2月28日。
- “去年交易金额”只在计算过程中使用，不保存到目标表。

### 7.2 近7日交易额

```text
rolling_7_day_transaction_amount
= SUM(daily_sales.transaction_amount)
  WHERE transaction_date BETWEEN 当前日期 - 6 AND 当前日期
```

窗口包含当前日期，共覆盖7个自然日；不是当前记录及其前6条数据。

### 7.3 近30日交易额

```text
rolling_30_day_transaction_amount
= SUM(daily_sales.transaction_amount)
  WHERE transaction_date BETWEEN 当前日期 - 29 AND 当前日期
```

窗口包含当前日期，共覆盖30个自然日；不是当前记录及其前29条数据。

## 8. 分组与生成流程

```text
读取daily_sales全部正式记录
→ 每个transaction_date保留一条基础记录
→ 左连接去年同月同日记录并计算同比
→ 按自然日范围计算近7日和近30日交易额
→ 按transaction_date升序写入目标表
→ 数据库生成id、created_at和updated_at
```

## 9. 正式表实际结果

| 检查项目 | 结果 |
|---|---:|
| 实际写入记录 | 543条 |
| 不同交易日期 | 543个 |
| 最早交易日期 | 2025-02-01 |
| 最晚交易日期 | 2026-07-28 |
| `transaction_amount`合计 | 6,254,453.47 |
| `rolling_7_day_transaction_amount`逐行合计 | 43,572,354.09 |
| `rolling_30_day_transaction_amount`逐行合计 | 185,319,805.35 |
| 存在去年同日记录、实际计算同比 | 178条 |
| 不存在去年同日记录、同比写0 | 365条 |
| 非0同比记录 | 178条 |
| 同比最小值 | -99.75 |
| 同比最大值 | 8,923.75 |
| 必填指标空值 | 0条 |
| 近7日小于当日、或近30日小于近7日 | 0条 |
| 重复交易日期 | 0组 |

滚动金额的“逐行合计”仅用于本次完整性校验，不是额外业务指标，也不能与总销售额直接比较。

## 10. 正式表完整字段样例

| `id` | `transaction_date` | `transaction_amount` | `year_over_year_rate` | `rolling_7_day_transaction_amount` | `rolling_30_day_transaction_amount` | `created_at` | `updated_at` |
|---:|---|---:|---:|---:|---:|---|---|
| 1 | 2025-02-01 | 29.90 | 0.00 | 29.90 | 29.90 | 2026-08-10 12:53:10.766005+08 | 2026-08-10 12:53:10.766005+08 |
| 151 | 2025-07-01 | 8,186.43 | 0.00 | 49,800.40 | 451,179.53 | 2026-08-10 12:53:10.766005+08 | 2026-08-10 12:53:10.766005+08 |
| 366 | 2026-02-01 | 2,698.10 | 8,923.75 | 45,541.20 | 55,725.10 | 2026-08-10 12:53:10.766005+08 | 2026-08-10 12:53:10.766005+08 |
| 385 | 2026-02-20 | 215.80 | -88.31 | 1,495.80 | 60,157.30 | 2026-08-10 12:53:10.766005+08 | 2026-08-10 12:53:10.766005+08 |
| 516 | 2026-07-01 | 1,906.00 | -76.72 | 16,780.20 | 82,914.11 | 2026-08-10 12:53:10.766005+08 | 2026-08-10 12:53:10.766005+08 |
| 543 | 2026-07-28 | 5,808.90 | -69.85 | 71,109.50 | 118,994.27 | 2026-08-10 12:53:10.766005+08 | 2026-08-10 12:53:10.766005+08 |

以上每行都直接来自正式数据库，并完整列出8个目标字段。

## 11. 指标关系说明

- 本表`transaction_amount`合计必须与`daily_sales.transaction_amount`合计一致，当前均为6,254,453.47。
- 近7日与近30日是每个目标日期各自对应的滚动窗口金额，跨行窗口会重叠，因此不能对逐行滚动金额求和后当作期间销售额。
- 同比是比例，不能跨日期直接相加或平均后作为整体同比。
- 本表不改变`daily_sales`、退款表或任何客户相关表。

## 12. 已执行建表SQL

字段顺序与`hh.daily_sales_metrics`保持一致；比例字段按统一两位小数规则执行：

```sql
CREATE TABLE kuaishouxiaodian.daily_sales_metrics (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    transaction_date DATE NOT NULL,
    transaction_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    year_over_year_rate NUMERIC(12,2),
    rolling_7_day_transaction_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    rolling_30_day_transaction_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT daily_sales_metrics_transaction_date_uk UNIQUE (
        transaction_date
    )
);

ALTER TABLE kuaishouxiaodian.daily_sales_metrics OWNER TO root;
```

## 13. 已执行首次数据生成SQL

```sql
INSERT INTO kuaishouxiaodian.daily_sales_metrics (
    transaction_date,
    transaction_amount,
    year_over_year_rate,
    rolling_7_day_transaction_amount,
    rolling_30_day_transaction_amount
)
SELECT
    current_day.transaction_date,
    current_day.transaction_amount,
    CASE
        WHEN previous_year.transaction_amount IS NULL
          OR previous_year.transaction_amount = 0
            THEN 0::NUMERIC(12,2)
        ELSE ROUND(
            (
                (current_day.transaction_amount - previous_year.transaction_amount)
                / previous_year.transaction_amount
            ) * 100,
            2
        )::NUMERIC(12,2)
    END AS year_over_year_rate,
    SUM(window_day.transaction_amount) FILTER (
        WHERE window_day.transaction_date
              BETWEEN current_day.transaction_date - 6
                  AND current_day.transaction_date
    )::NUMERIC(18,2) AS rolling_7_day_transaction_amount,
    SUM(window_day.transaction_amount)::NUMERIC(18,2)
        AS rolling_30_day_transaction_amount
FROM kuaishouxiaodian.daily_sales AS current_day
LEFT JOIN kuaishouxiaodian.daily_sales AS previous_year
  ON previous_year.transaction_date = CASE
      WHEN EXTRACT(MONTH FROM current_day.transaction_date) = 2
       AND EXTRACT(DAY FROM current_day.transaction_date) = 29
          THEN NULL
      ELSE (current_day.transaction_date - INTERVAL '1 year')::DATE
  END
JOIN kuaishouxiaodian.daily_sales AS window_day
  ON window_day.transaction_date
     BETWEEN current_day.transaction_date - 29
         AND current_day.transaction_date
GROUP BY
    current_day.transaction_date,
    current_day.transaction_amount,
    previous_year.transaction_amount
ORDER BY current_day.transaction_date;
```

## 14. 原子建表与上传流程

1. 开启PostgreSQL事务，并执行`SET LOCAL TIME ZONE 'Asia/Shanghai'`。
2. 确认`daily_sales_metrics`尚不存在，并校验`daily_sales`的字段、日期唯一性和金额完整性。
3. 创建目标表并将所有者设为`root`。
4. 从`daily_sales`全量计算同比、近7日交易额和近30日交易额。
5. 按交易日期升序一次性写入全部记录。
6. 校验字段数、记录数、日期范围、唯一键、空值、金额、同比、滚动金额及逐业务键重算结果。
7. 全部断言通过后提交；任一步失败则回滚建表和全部数据写入。

## 15. 后续上游数据变动时的原子刷新逻辑

一条日销售记录会影响自身指标、之后29个自然日内的滚动指标，以及次年同月同日的同比。为避免漏刷依赖日期，当前建议在每次文件上传成功的同一事务中对本表执行全量重算：

```text
raw_data和daily_sales完成本次变更
→ 在临时表中全量重算daily_sales_metrics
→ 校验临时结果
→ 删除目标表旧记录
→ 写入全部新结果
→ 校验目标表与临时结果逐日一致
→ 与本次基础表变更一次性提交
```

当前仅543条记录，全量重算的成本可控，且比只定位受影响日期更不容易遗漏滚动窗口或次年同比依赖。

## 16. 正式上传后验证规则

- 表字段数必须为8个，字段名称、顺序和类型必须与第4节一致。
- 当前数据下记录数必须为543条，不同交易日期必须为543个。
- 最早交易日期必须为2025-02-01，最晚交易日期必须为2026-07-28。
- `transaction_date`重复业务键、必填字段空值和生成结果中的空同比均必须为0。
- `transaction_amount`合计必须为6,254,453.47，并与`daily_sales`完全一致。
- 存在去年同日记录的日期必须为178条；缺少去年同日记录并将同比写0的日期必须为365条。
- 每一条同比必须按第7.1节公式重算一致，逐日差异必须为0。
- 每一条近7日和近30日交易额必须按自然日窗口重算一致，逐日金额差异必须为0。
- `rolling_7_day_transaction_amount < transaction_amount`必须为0条。
- `rolling_30_day_transaction_amount < rolling_7_day_transaction_amount`必须为0条。
- 目标表必须完整覆盖`daily_sales`的每个日期，不得存在遗漏日期或多余日期。
- 表所有者必须为`root`，`created_at`和`updated_at`必须按正式插入时的北京时间生成。
- 第10节样例中的全部8个字段必须与正式记录一致。

## 17. 逐业务键全量重算校验SQL

```sql
WITH expected AS (
    SELECT
        current_day.transaction_date,
        current_day.transaction_amount,
        CASE
            WHEN previous_year.transaction_amount IS NULL
              OR previous_year.transaction_amount = 0
                THEN 0::NUMERIC(12,2)
            ELSE ROUND(
                (
                    (current_day.transaction_amount - previous_year.transaction_amount)
                    / previous_year.transaction_amount
                ) * 100,
                2
            )::NUMERIC(12,2)
        END AS year_over_year_rate,
        SUM(window_day.transaction_amount) FILTER (
            WHERE window_day.transaction_date
                  BETWEEN current_day.transaction_date - 6
                      AND current_day.transaction_date
        )::NUMERIC(18,2) AS rolling_7_day_transaction_amount,
        SUM(window_day.transaction_amount)::NUMERIC(18,2)
            AS rolling_30_day_transaction_amount
    FROM kuaishouxiaodian.daily_sales AS current_day
    LEFT JOIN kuaishouxiaodian.daily_sales AS previous_year
      ON previous_year.transaction_date = CASE
          WHEN EXTRACT(MONTH FROM current_day.transaction_date) = 2
           AND EXTRACT(DAY FROM current_day.transaction_date) = 29
              THEN NULL
          ELSE (current_day.transaction_date - INTERVAL '1 year')::DATE
      END
    JOIN kuaishouxiaodian.daily_sales AS window_day
      ON window_day.transaction_date
         BETWEEN current_day.transaction_date - 29
             AND current_day.transaction_date
    GROUP BY
        current_day.transaction_date,
        current_day.transaction_amount,
        previous_year.transaction_amount
), compared AS (
    SELECT
        COALESCE(e.transaction_date, a.transaction_date) AS transaction_date,
        e.transaction_amount AS expected_transaction_amount,
        a.transaction_amount AS actual_transaction_amount,
        e.year_over_year_rate AS expected_year_over_year_rate,
        a.year_over_year_rate AS actual_year_over_year_rate,
        e.rolling_7_day_transaction_amount AS expected_rolling_7_day_amount,
        a.rolling_7_day_transaction_amount AS actual_rolling_7_day_amount,
        e.rolling_30_day_transaction_amount AS expected_rolling_30_day_amount,
        a.rolling_30_day_transaction_amount AS actual_rolling_30_day_amount
    FROM expected AS e
    FULL OUTER JOIN kuaishouxiaodian.daily_sales_metrics AS a
      USING (transaction_date)
)
SELECT COUNT(*) AS mismatched_day_rows
FROM compared
WHERE expected_transaction_amount
          IS DISTINCT FROM actual_transaction_amount
   OR expected_year_over_year_rate
          IS DISTINCT FROM actual_year_over_year_rate
   OR expected_rolling_7_day_amount
          IS DISTINCT FROM actual_rolling_7_day_amount
   OR expected_rolling_30_day_amount
          IS DISTINCT FROM actual_rolling_30_day_amount;
```

正式上传后`mismatched_day_rows`必须为0。

## 18. 用户审核确认项

- [x] 确认本表严格保留8个字段，不保存“去年交易金额”。
- [x] 确认数据粒度为“一个有销售记录的自然日”，不为无记录日期补零行。
- [x] 确认同比、环比等比例指标统一按百分比保存，并保留2位小数。
- [x] 确认去年同月同日记录不存在或金额为0时，同比写`0.00`。
- [x] 确认近7日包含当前日期及向前6个自然日。
- [x] 确认近30日包含当前日期及向前29个自然日。
- [x] 确认滚动窗口按自然日范围计算，不按记录条数计算。
- [x] 确认本表包含全部渠道，保存毛销售额，不扣减退款。
- [x] 确认快手小店无预售逻辑，本表不增加任何预售字段或筛选。
- [x] 确认后续上游变动时采用同一事务内全量重算，任一步失败全部回滚。
- [x] 确认第9节正式结果和第10节完整字段样例可作为正式校验基准。

## 19. 用户修改区

请直接在下方填写需要修改的内容：

```text
（待填写）
```

## 20. 实际执行与校验结果

执行时间：2026-08-10 12:53:10（北京时间）。

- 建表、全量指标计算和事务内强断言使用同一PostgreSQL事务，全部通过后成功提交。
- 实际写入543条记录、543个唯一交易日期、8个字段。
- 最早交易日期为2025-02-01，最晚交易日期为2026-07-28。
- `transaction_amount`合计为6,254,453.47，与`daily_sales`完全一致。
- `rolling_7_day_transaction_amount`逐行合计为43,572,354.09。
- `rolling_30_day_transaction_amount`逐行合计为185,319,805.35。
- 实际计算同比178条；缺少去年同日而写入0.00的记录365条。
- 同比最小值为-99.75，最大值为8,923.75；字段类型为`NUMERIC(12,2)`。
- 必填指标空值、重复日期、滚动金额关系异常和逐日全量重算差异均为0。
- 本文6条正式样例已经逐字段与数据库核对一致。
- 表所有者为`root`，主键和交易日期唯一约束均已生效。
