# 快手小店第10张表审核草稿：`kuaishouxiaodian.monthly_sales`

> 状态：已确认、已建表、已上传数据、已校验通过  
> 数据库：`weidian`  
> Schema：`kuaishouxiaodian`  
> 表序号：10 / 35  
> 上游表：`kuaishouxiaodian.daily_sales`  
> 样例说明：本文样例已经使用第10张正式表中的实际记录复核并更新。

## 1. 表的作用

`monthly_sales`用于保存快手小店每个自然月的整体销售金额。一条记录代表一个完整自然月的销售汇总结果。

本表可用于月销售趋势、月度经营分析，以及后续季度和半年销售额表的计算。

## 2. 自然月定义

- 每个自然月从当月1日开始。
- 每个自然月到当月最后一天结束。
- 2月结束日期根据实际年份自动判断为28日或29日。
- 跨年时按公历月份划分，不受自定义季度和半年周期影响。
- 月内某一天没有销售记录，不会缩短自然月边界。

示例：

```text
交易日期：2025-07-18
所属自然月：2025-07-01 至 2025-07-31

交易日期：2026-02-08
所属自然月：2026-02-01 至 2026-02-28
```

## 3. 数据粒度与唯一性

- 一条记录代表一个自然月的整体销售金额。
- 主键：`id`。
- 业务唯一键：`period_start + period_end`。
- 同一个自然月只能存在一条记录。
- 某个自然月完全没有日销售记录时，不主动生成金额为0的补零记录。

## 4. 字段设计

本表严格保留以下6个字段：

| 序号 | 字段 | PostgreSQL类型 | 是否必填 | 默认值 | 说明 |
|---:|---|---|---|---|---|
| 1 | `id` | `BIGINT` | 是 | 自增 | 主键，由数据库自动生成 |
| 2 | `period_start` | `DATE` | 是 | 无 | 自然月开始日期，必须是当月1日 |
| 3 | `period_end` | `DATE` | 是 | 无 | 自然月结束日期，必须是当月最后一天 |
| 4 | `monthly_transaction_amount` | `NUMERIC(18,2)` | 是 | `0` | 自然月内各日`transaction_amount`之和 |
| 5 | `created_at` | `TIMESTAMPTZ` | 是 | `CURRENT_TIMESTAMP` | 首次插入数据库的北京时间 |
| 6 | `updated_at` | `TIMESTAMPTZ` | 是 | `CURRENT_TIMESTAMP` | 最近刷新该记录的北京时间 |

## 5. 数据来源与字段映射

本表基于第3张正式表`daily_sales`进行二次汇总，不直接重复读取`raw_data`：

| 目标字段 | 上游字段 | 处理方式 |
|---|---|---|
| `period_start` | `daily_sales.transaction_date` | 取交易日期所在月份的第1日 |
| `period_end` | `daily_sales.transaction_date` | 取交易日期所在月份的最后一日 |
| `monthly_transaction_amount` | `daily_sales.transaction_amount` | 按自然月求和 |

`id`由数据库自增生成；`created_at`和`updated_at`按数据插入时的北京时间生成。

## 6. 继承的销售数据口径

由于`daily_sales`已经完成订单状态、交易日期和`实付款`口径处理，因此本表完全继承以下规则：

- 交易日期来自原始数据的`订单创建时间`。
- 交易金额来自有效订单的`实付款`。
- 有效订单状态为`交易成功`、`已发货`、`已收货`。
- 保存毛销售额，不直接扣减退款。
- 包含全部渠道，不筛选`渠道 = '分销'`。
- 本表不是客户相关表，不计算客户ID，也不应用CPS达人、团长和快赚客的优先级。
- 本表不是商品相关表，不要求`SKU编码`有值。

## 7. 自然月日期计算逻辑

自然月开始日期：

```sql
DATE_TRUNC('month', transaction_date)::DATE AS period_start
```

自然月结束日期：

```sql
(
    DATE_TRUNC('month', transaction_date)
    + INTERVAL '1 month - 1 day'
)::DATE AS period_end
```

该算法会自动适配每月28日、29日、30日或31日的结束日期。

## 8. 当前数据边界处理

当前第3张日销售额表的数据范围为2025-02-01至2026-07-28：

- 第一条月记录边界为2025-02-01至2025-02-28。
- 最后一条月记录边界为2026-07-01至2026-07-31。
- 当前2026年7月只有7月1日至7月28日的数据，但`period_end`仍保存完整自然月结束日期2026-07-31。
- 以后上传7月29日至7月31日的数据时，应重新汇总并更新同一条2026年7月记录，不新增第二条7月记录。
- 当前相邻月份均有日销售数据，因此预计生成18个连续自然月；此结论只代表当前数据，不设置强制补零规则。

## 9. 交易金额与退款的关系

`monthly_transaction_amount`表示有效订单的月度毛销售额：

```text
monthly_transaction_amount
= 同一自然月内daily_sales.transaction_amount之和
```

- 不从月销售额中直接扣除退款。
- 月退款金额由第11张`monthly_refunds`单独保存。
- 如看板需要月净销售额，应在查询或指标层使用“月销售额 - 月退款额”，不改变本表字段结构。

## 10. 分组和聚合顺序

```text
读取daily_sales
→ 根据transaction_date确定自然月开始与结束日期
→ 按period_start + period_end分组
→ 汇总transaction_amount
→ 生成一条月销售额记录
```

## 11. 正式表实际结果

| 检查项目 | 结果 |
|---|---:|
| 第3张日销售记录 | 543条 |
| 实际写入月销售记录 | 18条 |
| 不同自然月 | 18个月 |
| 最早月开始日期 | 2025-02-01 |
| 最晚月结束日期 | 2026-07-31 |
| 月销售金额合计 | 6,254,453.47 |
| 与第3张日销售额合计差异 | 0.00 |
| 月开始或结束日期错误 | 0条 |
| 非正数月销售金额 | 0条 |

## 12. 正式表实际样例

以下样例直接读取第10张正式表，完整列出全部6个字段：

| `id` | `period_start` | `period_end` | `monthly_transaction_amount` | `created_at` | `updated_at` |
|---:|---|---|---:|---|---|
| 1 | 2025-02-01 | 2025-02-28 | 89,675.20 | 2026-08-10 11:09:52.579086+08 | 2026-08-10 11:09:52.579086+08 |
| 6 | 2025-07-01 | 2025-07-31 | 334,037.01 | 2026-08-10 11:09:52.579086+08 | 2026-08-10 11:09:52.579086+08 |
| 11 | 2025-12-01 | 2025-12-31 | 95,736.50 | 2026-08-10 11:09:52.579086+08 | 2026-08-10 11:09:52.579086+08 |
| 12 | 2026-01-01 | 2026-01-31 | 54,267.70 | 2026-08-10 11:09:52.579086+08 | 2026-08-10 11:09:52.579086+08 |
| 16 | 2026-05-01 | 2026-05-31 | 234,047.60 | 2026-08-10 11:09:52.579086+08 | 2026-08-10 11:09:52.579086+08 |
| 18 | 2026-07-01 | 2026-07-31 | 113,657.47 | 2026-08-10 11:09:52.579086+08 | 2026-08-10 11:09:52.579086+08 |

2026年7月的28条日记录分别对应7月1日至7月28日；月记录仍使用完整的自然月边界。

## 13. 与周销售额表的关系

- 第6张`weekly_sales`和本表都来自第3张`daily_sales`，当前金额合计均为6,254,453.47。
- 周表按星期一至星期日分组，月表按每月1日至最后一日分组。
- 一个自然周可能跨越两个月，因此不能直接把整条周记录归入某一个月份。
- 本表必须从`daily_sales`重新按自然月汇总，不能直接对`weekly_sales`求和生成。

## 14. 已执行建表SQL

```sql
CREATE TABLE kuaishouxiaodian.monthly_sales (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    monthly_transaction_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT monthly_sales_period_check CHECK (
        period_start = DATE_TRUNC('month', period_start)::DATE
        AND period_end = (
            DATE_TRUNC('month', period_start)
            + INTERVAL '1 month - 1 day'
        )::DATE
    ),
    CONSTRAINT monthly_sales_amount_check CHECK (
        monthly_transaction_amount > 0
    ),
    CONSTRAINT monthly_sales_business_uk UNIQUE (
        period_start,
        period_end
    )
);
```

## 15. 首次数据生成SQL

```sql
INSERT INTO kuaishouxiaodian.monthly_sales (
    period_start,
    period_end,
    monthly_transaction_amount
)
SELECT
    DATE_TRUNC('month', transaction_date)::DATE
        AS period_start,
    (
        DATE_TRUNC('month', transaction_date)
        + INTERVAL '1 month - 1 day'
    )::DATE AS period_end,
    SUM(transaction_amount)::NUMERIC(18,2)
        AS monthly_transaction_amount
FROM kuaishouxiaodian.daily_sales
GROUP BY period_start, period_end
ORDER BY period_start;
```

## 16. 原子建表与上传流程

1. 开启PostgreSQL事务，并将事务时区设置为`Asia/Shanghai`。
2. 创建`kuaishouxiaodian.monthly_sales`。
3. 读取第3张表的交易日期和交易金额。
4. 将每个交易日期换算为所属自然月的第1日和最后一日。
5. 按`period_start + period_end`分组。
6. 汇总每个自然月的交易金额。
7. 写入月销售额记录。
8. 校验字段数、记录数、月边界、业务键、金额和上游重算结果。
9. 全部通过后提交；任一环节失败则回滚建表和全部数据写入。

## 17. 后续日销售数据变动时的刷新逻辑

每次原始文件上传导致`daily_sales`新增或更新后，在同一事务内刷新受影响的自然月：

```text
daily_sales新增或更新
→ 根据受影响交易日期定位自然月
→ 删除monthly_sales中该自然月的旧记录
→ 使用该自然月内的全部日记录重新汇总
→ 写入新的月销售额记录
→ 校验通过后与上游变动一起提交
→ 任一步失败则全部回滚
```

## 18. 正式上传后验证规则

- 表字段数必须为6个。
- 当前数据下记录数必须为18条。
- 必填字段空值必须为0条。
- 重复`period_start + period_end`必须为0组。
- `period_start`必须全部为当月1日。
- `period_end`必须全部为当月最后一日。
- 非正数月销售金额必须为0条。
- 最早月开始日期必须为2025-02-01。
- 最晚月结束日期必须为2026-07-31。
- 不同自然月必须为18个月。
- 月销售金额合计必须为6,254,453.47。
- 与`daily_sales`重新全量汇总相比，金额差异必须为0。
- 本文列出的6条月销售样例必须与正式表逐条一致。

## 19. 用户审核确认项

- [x] 确认本表严格保留6个字段。
- [x] 确认数据粒度为一个自然月一条记录。
- [x] 确认自然月为当月1日至当月最后一日。
- [x] 确认2026年7月当前只有1日至28日的源数据，但`period_end`保存为7月31日。
- [x] 确认月交易金额汇总第3张表的`transaction_amount`。
- [x] 确认本表保存毛销售额，不直接扣减退款。
- [x] 确认本表包含全部渠道，不筛选分销渠道。
- [x] 确认本表直接从`daily_sales`汇总，不从跨月的`weekly_sales`汇总。
- [x] 确认无销售记录的自然月不生成补零记录。
- [x] 确认非正数金额不允许写入。
- [x] 确认上述真实样例和总体结果可以作为正式上传后的校验基准。

## 20. 用户修改区

请直接在下方填写需要修改的内容：

```text
（待填写）
```

## 21. 实际执行与校验结果

执行时间：2026-08-10 11:09:52（北京时间）。

- 建表、自然月汇总和事务内校验在同一PostgreSQL事务中完成，全部通过后成功提交。
- 实际写入18条月销售记录、6个字段。
- 最早月开始日期：2025-02-01；最晚月结束日期：2026-07-31。
- 月销售金额合计：6,254,453.47。
- 必填字段空值、重复业务键、错误自然月和非正数金额均为0。
- 与`daily_sales`重新全量汇总相比，金额不一致记录为0条。
- 主键、自然月、正数金额和业务唯一约束均已生效。
- 本文6条正式样例已逐条与数据库核对一致。
- 表所有者为`root`。
