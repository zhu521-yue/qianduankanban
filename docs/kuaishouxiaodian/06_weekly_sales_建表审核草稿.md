# 快手小店第6张表审核草稿：`kuaishouxiaodian.weekly_sales`

> 状态：已确认、已建表、已上传数据、已校验通过  
> 数据库：`weidian`  
> Schema：`kuaishouxiaodian`  
> 表序号：06 / 35  
> 上游表：`kuaishouxiaodian.daily_sales`  
> 样例说明：本文样例最初依据第3张正式表计算，正式上传后已用数据库实际记录复核并更新。

## 1. 表的作用

`weekly_sales`用于保存快手小店按自然周汇总的整体销售额。一条记录代表一个完整的周一至周日周期，供周销售趋势、周同比环比以及后续销售指标表使用。

本表属于整体销售表，不属于客户相关表，因此不增加`渠道 = '分销'`筛选条件。

## 2. 自然周定义

- 每周第一天：星期一。
- 每周最后一天：星期日。
- `period_start`始终为星期一。
- `period_end`始终等于`period_start + 6天`，即星期日。
- 周期不会因为月末、年末或数据文件边界而拆开。

示例：

```text
2025-03-01是星期六
→ 所属自然周开始日期：2025-02-24（星期一）
→ 所属自然周结束日期：2025-03-02（星期日）
```

跨年示例：

```text
2025-12-31是星期三
→ 所属自然周：2025-12-29 至 2026-01-04
```

## 3. 数据粒度与唯一性

- 一条记录代表一个自然周的整体销售额。
- 主键：`id`。
- 业务唯一键：`period_start + period_end`。
- 同一个自然周只能存在一条记录。
- 某个自然周完全没有日销售记录时，不主动生成补零记录。

## 4. 字段设计

本表严格保留以下6个字段：

| 序号 | 字段 | PostgreSQL类型 | 是否必填 | 默认值 | 说明 |
|---:|---|---|---|---|---|
| 1 | `id` | `BIGINT` | 是 | 自增 | 主键，由数据库自动生成 |
| 2 | `period_start` | `DATE` | 是 | 无 | 自然周开始日期，必须是星期一 |
| 3 | `period_end` | `DATE` | 是 | 无 | 自然周结束日期，必须是星期日 |
| 4 | `weekly_transaction_amount` | `NUMERIC(18,2)` | 是 | `0` | 自然周内各日`transaction_amount`之和 |
| 5 | `created_at` | `TIMESTAMPTZ` | 是 | `CURRENT_TIMESTAMP` | 首次插入数据库的北京时间 |
| 6 | `updated_at` | `TIMESTAMPTZ` | 是 | `CURRENT_TIMESTAMP` | 最近刷新该记录的北京时间 |

## 5. 数据来源与计算口径

本表基于第3张正式表`daily_sales`进行二次汇总，不直接重复读取`raw_data`：

| 目标字段 | 上游字段 | 处理方式 |
|---|---|---|
| `period_start` | `daily_sales.transaction_date` | 向前推算至所属周的星期一 |
| `period_end` | `period_start` | 加6天得到星期日 |
| `weekly_transaction_amount` | `daily_sales.transaction_amount` | 按自然周求和 |

由于`daily_sales`已经完成订单状态、交易日期和`实付款`口径处理，因此本表完全继承以下规则：

- 销售金额来自有效订单的`实付款`。
- 有效订单状态为`交易成功`、`已发货`、`已收货`。
- 保存毛销售额，不直接扣减退款。
- 包含全部渠道，不筛选`渠道 = '分销'`。
- `raw_data`中的重复原始记录是否计入，完全沿用第3张表结果。

## 6. 自然周日期计算逻辑

PostgreSQL中`ISODOW`规定星期一为1、星期日为7，因此自然周开始日期计算为：

```sql
transaction_date
    - (EXTRACT(ISODOW FROM transaction_date)::INTEGER - 1)
```

完整字段计算：

```sql
transaction_date
    - (EXTRACT(ISODOW FROM transaction_date)::INTEGER - 1)
    AS period_start,

transaction_date
    - (EXTRACT(ISODOW FROM transaction_date)::INTEGER - 1)
    + 6
    AS period_end
```

## 7. 数据边界处理

当前日销售数据范围是2025-02-01至2026-07-28，但周字段仍保存完整自然周边界：

- 第一条周记录：2025-01-27至2025-02-02。
- 第一周当前只有2025-02-01、2025-02-02两天的数据。
- 最后一条周记录：2026-07-27至2026-08-02。
- 最后一周当前只有2026-07-27、2026-07-28两天的数据。
- 不会把首周开始日期改成2025-02-01，也不会把末周结束日期改成2026-07-28。
- 以后补充这些自然周内的其他日期数据时，重新汇总并更新同一周记录。

首尾周属于数据范围不完整，不代表自然周定义发生变化。

## 8. 基于真实数据计算的样例

以下样例是第6张正式表中的实际记录。

“日记录数”仅用于审核计算过程，不是`weekly_sales`字段。

| `id` | `period_start` | `period_end` | 日记录数（仅审核用） | `weekly_transaction_amount` | `created_at` | `updated_at` |
|---|---|---|---:|---:|---|---|
| 1 | 2025-01-27 | 2025-02-02 | 2 | 179.80 | 2026-08-10 10:09:40.75555+08 | 2026-08-10 10:09:40.75555+08 |
| 5 | 2025-02-24 | 2025-03-02 | 7 | 355,906.30 | 2026-08-10 10:09:40.75555+08 | 2026-08-10 10:09:40.75555+08 |
| 23 | 2025-06-30 | 2025-07-06 | 7 | 47,023.68 | 2026-08-10 10:09:40.75555+08 | 2026-08-10 10:09:40.75555+08 |
| 53 | 2026-01-26 | 2026-02-01 | 7 | 45,541.20 | 2026-08-10 10:09:40.75555+08 | 2026-08-10 10:09:40.75555+08 |
| 75 | 2026-06-29 | 2026-07-05 | 7 | 17,601.12 | 2026-08-10 10:09:40.75555+08 | 2026-08-10 10:09:40.75555+08 |
| 79 | 2026-07-27 | 2026-08-02 | 2 | 13,668.30 | 2026-08-10 10:09:40.75555+08 | 2026-08-10 10:09:40.75555+08 |

例如，2025-02-24至2025-03-02的355,906.30，是该自然周7条日销售记录的`transaction_amount`之和。

## 9. 当前口径下的实际总体结果

- 实际生成周销售额记录：79条。
- 最早周开始日期：2025-01-27。
- 最晚周结束日期：2026-08-02。
- 日销售记录数为7天的自然周：77周。
- 日销售记录数少于7天的自然周：2周，即数据边界处的首周和末周。
- 周销售金额合计：6,254,453.47。
- 第6张表全部周金额之和与第3张`daily_sales`全部日金额之和差异：0.00。
- 周开始日期不是星期一：0条。
- 周结束日期不是星期日：0条。
- 周结束日期不等于开始日期加6天：0条。

## 10. 拟执行建表SQL

```sql
CREATE TABLE kuaishouxiaodian.weekly_sales (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    weekly_transaction_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT weekly_sales_period_check CHECK (
        EXTRACT(ISODOW FROM period_start) = 1
        AND period_end = period_start + 6
    ),
    CONSTRAINT weekly_sales_period_uk UNIQUE (period_start, period_end)
);
```

## 11. 首次数据生成SQL

```sql
INSERT INTO kuaishouxiaodian.weekly_sales (
    period_start,
    period_end,
    weekly_transaction_amount
)
SELECT
    transaction_date
        - (EXTRACT(ISODOW FROM transaction_date)::INTEGER - 1)
        AS period_start,
    transaction_date
        - (EXTRACT(ISODOW FROM transaction_date)::INTEGER - 1)
        + 6
        AS period_end,
    SUM(transaction_amount)::NUMERIC(18,2)
        AS weekly_transaction_amount
FROM kuaishouxiaodian.daily_sales
GROUP BY period_start, period_end
ORDER BY period_start;
```

## 12. 原子建表与上传流程

1. 开启PostgreSQL事务，并将事务时区设为`Asia/Shanghai`。
2. 创建`kuaishouxiaodian.weekly_sales`。
3. 读取第3张`daily_sales`中的交易日期和交易金额。
4. 将每个交易日期换算为所属自然周的周一和周日。
5. 按`period_start + period_end`分组，对日交易金额求和。
6. 写入周销售额记录。
7. 校验字段数、周期唯一性、周一开始、周日结束和周期长度。
8. 校验记录数、日期范围、总金额以及本文真实样例。
9. 将全部周金额再次求和，与`daily_sales`总金额核对，差异必须为0。
10. 全部通过后提交；任一步失败则回滚建表和全部数据写入。

## 13. 后续日销售数据变动时的刷新逻辑

每次原始文件上传导致`daily_sales`新增或更新后，在同一个事务中刷新受影响的自然周：

```text
daily_sales新增或更新成功
→ 根据受影响日期计算对应的周一和周日
→ 删除weekly_sales中这些自然周的旧记录
→ 使用daily_sales中这些自然周的全部日记录重新汇总
→ 写入新的周销售额
→ 校验通过后一起提交；失败则一起回滚
```

如果一次上传同时影响多个自然周，则这些自然周在同一事务中一起刷新。

## 14. 正式上传后的验证规则

- 表字段数必须为6个。
- 记录数必须为79条，除非上传前`daily_sales`发生变化。
- 重复“周开始日期 + 周结束日期”必须为0组。
- 必填字段空值必须为0条。
- 周开始日期必须全部为星期一。
- 周结束日期必须全部为星期日。
- 周结束日期必须全部等于周开始日期加6天。
- 最早周开始日期应为2025-01-27。
- 最晚周结束日期应为2026-08-02。
- 周销售金额总计应为6,254,453.47。
- 与`daily_sales`总金额的差异必须为0.00。
- 本文列出的6个自然周样例必须与正式表逐条一致。

## 15. 用户审核确认结果

- [x] 确认本表严格保留6个字段。
- [x] 确认自然周定义为星期一至星期日。
- [x] 确认周期字段始终保存完整自然周边界。
- [x] 确认首周和末周即使只有部分日期数据，也不缩短周期边界。
- [x] 确认周销售金额来自`daily_sales.transaction_amount`之和。
- [x] 确认本表属于整体销售表，不筛选分销渠道。
- [x] 确认本表保存毛销售额，不直接扣减退款。
- [x] 确认没有任何日销售记录的自然周不生成补零记录。
- [x] 确认上述真实样例和总体结果可作为正式上传后的校验基准。

## 16. 用户修改区

请直接在下方填写需要修改的内容：

```text
（待填写）
```

## 17. 实际执行与校验结果

执行时间：2026-08-10 10:09:40（北京时间）。

- 建表、自然周汇总和事务内校验在同一个PostgreSQL事务中完成，全部通过后成功提交。
- 实际写入记录：79条。
- 最早周开始日期：2025-01-27。
- 最晚周结束日期：2026-08-02。
- 周销售金额合计：6,254,453.47。
- 必填字段空值：0条。
- 重复“周开始日期 + 周结束日期”：0组。
- 非星期一开始、非星期日结束或周期长度错误：0条。
- 实际字段数：6个。
- 主键、周期检查约束和周期唯一约束均已生效。
- 与`daily_sales`重新逐周全量汇总的结果对比：差异0周。
- 本文列出的6个自然周样例均与正式表逐条一致。
