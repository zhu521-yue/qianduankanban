# 快手小店第9张表审核草稿：`kuaishouxiaodian.weekly_customer_sales`

> 状态：已确认、已建表、已上传数据、已校验通过  
> 数据库：`weidian`  
> Schema：`kuaishouxiaodian`  
> 表序号：09 / 35  
> 上游表：`kuaishouxiaodian.daily_customer_sales`  
> 样例说明：本文样例已经使用第9张正式表中的实际记录复核并更新。

## 1. 表的作用

`weekly_customer_sales`用于保存每个客户在每个自然周内的销售金额。一条记录代表“一个完整自然周 + 一个客户ID”的汇总结果。

本表可用于客户周销售排行、客户周销售趋势、客户活跃度分析以及后续月客户销售额等表的计算。

## 2. 自然周定义

- 每周第一天：星期一。
- 每周最后一天：星期日。
- `period_start`必须是星期一。
- `period_end`必须等于`period_start + 6天`。
- 跨月、跨年时仍保留完整自然周边界。
- 周内某一天没有该客户的销售记录，不会缩短自然周范围。

示例：

```text
交易日期：2025-03-01（星期六）
所属自然周：2025-02-24 至 2025-03-02
```

## 3. 数据粒度与唯一性

- 一条记录代表一个客户在一个自然周内的销售金额。
- 主键：`id`。
- 业务唯一键：`period_start + period_end + customer_id`。
- 同一个客户在同一个自然周只能存在一条记录。
- 某个客户在某个自然周完全没有销售记录时，不生成金额为0的补零记录。
- 本表必须完整保留`customer_id`，任何正式样例和上传记录都不能省略客户ID字段。

## 4. 字段设计

本表严格保留以下7个字段：

| 序号 | 字段 | PostgreSQL类型 | 是否必填 | 默认值 | 说明 |
|---:|---|---|---|---|---|
| 1 | `id` | `BIGINT` | 是 | 自增 | 主键，由数据库自动生成 |
| 2 | `period_start` | `DATE` | 是 | 无 | 自然周开始日期，必须是星期一 |
| 3 | `period_end` | `DATE` | 是 | 无 | 自然周结束日期，必须是星期日 |
| 4 | `customer_id` | `TEXT` | 是 | 无 | 统一后的客户ID |
| 5 | `weekly_transaction_amount` | `NUMERIC(18,2)` | 是 | `0` | 该客户在该自然周的毛销售金额 |
| 6 | `created_at` | `TIMESTAMPTZ` | 是 | `CURRENT_TIMESTAMP` | 首次插入数据库的北京时间 |
| 7 | `updated_at` | `TIMESTAMPTZ` | 是 | `CURRENT_TIMESTAMP` | 最近刷新该记录的北京时间 |

本表不保存客户昵称。需要展示客户昵称时，通过`customer_id`关联第2张`customer_id_mapping`。

## 5. 数据来源与字段映射

本表基于第5张正式表`daily_customer_sales`二次汇总，不直接重复读取`raw_data`。

| 目标字段 | 上游字段 | 处理方式 |
|---|---|---|
| `period_start` | `daily_customer_sales.transaction_date` | 向前推算至所属自然周的星期一 |
| `period_end` | `period_start` | 加6天得到星期日 |
| `customer_id` | `daily_customer_sales.customer_id` | 原值保留，作为客户分组字段 |
| `weekly_transaction_amount` | `daily_customer_sales.transaction_amount` | 同一自然周、同一客户ID求和 |

第5张表当前结构和规模：

- 6个字段。
- 8,941条“交易日期 + 客户ID”日汇总记录。
- 946个有有效销售的客户ID。
- 交易日期范围：2025-02-01至2026-07-28。
- 交易金额合计：5,709,898.66。
- 空白客户ID：0条。
- 非正数日交易金额：0条。

## 6. 必须继承的分销渠道规则

本表属于客户相关表，必须严格沿用已经确认的规则：

```text
凡是与客户相关的表，都必须筛选渠道字段的值为“分销”。
```

第5张`daily_customer_sales`在生成客户ID和日客户销售额前已经执行：

```sql
BTRIM("渠道"::text) = '分销'
```

因此第9张表不再直接读取`raw_data`重复筛选，而是只汇总已经完成渠道筛选的`daily_customer_sales`。非分销渠道不会进入本表。

## 7. 客户ID计算规则的继承

第9张表不重新生成客户ID，完整继承第2张和第5张表已经确认的优先级：

1. `CPS达人ID`有值：`customer_id = CPS达人ID`。
2. `CPS达人ID`为空、`团长ID`有值：`customer_id = 团长ID`。
3. `CPS达人ID`和`团长ID`都为空、`快赚客ID`有值：`customer_id = 快赚客ID`。
4. 三种ID都为空：该记录无法形成有效客户ID，不进入客户维度表。

该逻辑只在`渠道 = '分销'`的原始记录中执行。

当前第5张表的946个客户ID全部能在第2张`customer_id_mapping`中找到，对不上客户映射表的孤立客户数量为0。

## 8. 销售金额口径

本表继承第5张表已经确认的销售口径：

- 有效订单状态为`交易成功`、`已发货`、`已收货`。
- 交易金额使用原始字段`实付款`。
- 保存毛销售额，不直接扣减退款。
- 退款指标通过退款相关表单独展示。
- 不增加商品编码或商品数量字段。

## 9. 与整体周销售额表的金额差异

第6张`weekly_sales`包含全部渠道，销售金额合计为6,254,453.47；第9张表只包含分销渠道客户销售，预计算金额合计为5,709,898.66，相差544,554.81。

该差异来自非分销渠道销售，不是客户周汇总错误。第9张表必须与第5张`daily_customer_sales`核对，不能强制与整体`weekly_sales`金额相等。

## 10. 自然周与客户分组逻辑

```sql
transaction_date
    - (EXTRACT(ISODOW FROM transaction_date)::INTEGER - 1)
    AS period_start,

transaction_date
    - (EXTRACT(ISODOW FROM transaction_date)::INTEGER - 1)
    + 6
    AS period_end
```

业务分组顺序：

```text
先按照自然周分组
→ 再按照customer_id分组
→ 汇总transaction_amount
```

数据库实际使用`period_start + period_end + customer_id`同时分组，结果与上述业务顺序一致。

## 11. 正式表实际结果

| 检查项目 | 结果 |
|---|---:|
| 实际写入周客户记录 | 3,650条 |
| 有销售的客户ID | 946个 |
| 不同自然周 | 79周 |
| 最早周开始日期 | 2025-01-27 |
| 最晚周结束日期 | 2026-08-02 |
| 周客户销售金额合计 | 5,709,898.66 |
| 非星期一开始或周期长度错误 | 0条 |
| 空白客户ID | 0条 |
| 非正数周客户金额 | 0条 |
| 无法关联客户映射表的客户ID | 0个 |

## 12. 正式表实际样例

以下样例直接读取第9张正式表，每一条都完整列出7个字段，包括客户ID：

| `id` | `period_start` | `period_end` | `customer_id` | `weekly_transaction_amount` | `created_at` | `updated_at` |
|---:|---|---|---|---:|---|---|
| 1 | 2025-01-27 | 2025-02-02 | `105193469` | 149.90 | 2026-08-10 11:03:06.348516+08 | 2026-08-10 11:03:06.348516+08 |
| 92 | 2025-02-24 | 2025-03-02 | `745575951` | 331,693.50 | 2026-08-10 11:03:06.348516+08 | 2026-08-10 11:03:06.348516+08 |
| 1,583 | 2025-06-30 | 2025-07-06 | `745575951` | 8,350.00 | 2026-08-10 11:03:06.348516+08 | 2026-08-10 11:03:06.348516+08 |
| 2,611 | 2026-01-26 | 2026-02-01 | `1833627526` | 40,756.80 | 2026-08-10 11:03:06.348516+08 | 2026-08-10 11:03:06.348516+08 |
| 2,752 | 2026-03-16 | 2026-03-22 | `745575951` | 230,360.30 | 2026-08-10 11:03:06.348516+08 | 2026-08-10 11:03:06.348516+08 |
| 3,639 | 2026-07-27 | 2026-08-02 | `415121040` | 7,211.80 | 2026-08-10 11:03:06.348516+08 | 2026-08-10 11:03:06.348516+08 |

例如，客户`745575951`在2025-02-24至2025-03-02自然周内的正式周交易金额为331,693.50。

## 13. 自然周整体汇总辅助样例

下表只用于检查同一周内有多少个分销客户，不是第9张表的字段结构：

| `period_start` | `period_end` | 客户数 | 周内全部客户金额 |
|---|---|---:|---:|
| 2025-01-27 | 2025-02-02 | 2 | 179.80 |
| 2025-02-03 | 2025-02-09 | 17 | 1,997.60 |
| 2025-02-10 | 2025-02-16 | 17 | 54,093.10 |
| 2025-02-17 | 2025-02-23 | 20 | 16,584.40 |
| 2025-02-24 | 2025-03-02 | 37 | 343,422.30 |

## 14. 已执行建表SQL

```sql
CREATE TABLE kuaishouxiaodian.weekly_customer_sales (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    customer_id TEXT NOT NULL,
    weekly_transaction_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT weekly_customer_sales_period_check CHECK (
        EXTRACT(ISODOW FROM period_start) = 1
        AND period_end = period_start + 6
    ),
    CONSTRAINT weekly_customer_sales_customer_id_check CHECK (
        BTRIM(customer_id) <> ''
    ),
    CONSTRAINT weekly_customer_sales_amount_check CHECK (
        weekly_transaction_amount > 0
    ),
    CONSTRAINT weekly_customer_sales_business_uk UNIQUE (
        period_start,
        period_end,
        customer_id
    )
);
```

## 15. 首次数据生成SQL

```sql
INSERT INTO kuaishouxiaodian.weekly_customer_sales (
    period_start,
    period_end,
    customer_id,
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
    customer_id,
    SUM(transaction_amount)::NUMERIC(18,2)
        AS weekly_transaction_amount
FROM kuaishouxiaodian.daily_customer_sales
GROUP BY period_start, period_end, customer_id
ORDER BY period_start, customer_id;
```

## 16. 原子建表与上传流程

1. 开启PostgreSQL事务，并将事务时区设置为`Asia/Shanghai`。
2. 创建`kuaishouxiaodian.weekly_customer_sales`。
3. 读取第5张表的交易日期、客户ID和交易金额。
4. 将每个交易日期换算为所属自然周的星期一和星期日。
5. 按`period_start + period_end + customer_id`分组。
6. 汇总每个客户在每个自然周内的交易金额。
7. 写入周客户销售记录。
8. 校验字段数、记录数、业务键唯一性、客户ID、自然周边界和正数金额。
9. 校验所有客户ID都能关联第2张客户映射表。
10. 将全部周客户金额与`daily_customer_sales`全量金额核对，差异必须为0。
11. 核对本文真实样例。
12. 全部通过后提交；任一环节失败则回滚建表和全部数据写入。

## 17. 后续日客户销售数据变动时的刷新逻辑

每次原始文件上传导致`daily_customer_sales`新增或更新后，在同一事务内刷新受影响的自然周和客户ID：

```text
daily_customer_sales新增或更新
→ 根据受影响交易日期定位自然周
→ 获取受影响的customer_id
→ 删除weekly_customer_sales中对应“自然周 + customer_id”的旧记录
→ 使用该自然周内该customer_id的全部日记录重新汇总
→ 写入新的周客户销售记录
→ 校验通过后与上游变动一起提交
→ 任一步失败则全部回滚
```

## 18. 正式上传后验证规则

- 表字段数必须为7个。
- 当前数据下记录数必须为3,650条。
- 必填字段空值必须为0条。
- 重复`period_start + period_end + customer_id`必须为0组。
- 空白`customer_id`必须为0条。
- `period_start`必须全部为星期一。
- `period_end`必须全部等于`period_start + 6天`。
- 非正数周客户金额必须为0条。
- 最早周开始日期必须为2025-01-27。
- 最晚周结束日期必须为2026-08-02。
- 有销售客户ID必须为946个，不同自然周必须为79周。
- 周客户销售金额合计必须为5,709,898.66。
- 与`daily_customer_sales`重新全量汇总相比，金额差异必须为0。
- 无法关联`customer_id_mapping`的客户ID必须为0个。
- 本文列出的6条客户周样例必须与正式表逐条一致，并且不能省略客户ID。

## 19. 用户审核确认项

- [x] 确认本表严格保留7个字段，其中必须包含`customer_id`。
- [x] 确认数据粒度为“一个自然周 + 一个客户ID”。
- [x] 确认自然周定义为星期一至星期日。
- [x] 确认本表只汇总分销渠道客户数据。
- [x] 确认客户ID继承CPS达人ID、团长ID、快赚客ID的优先级。
- [x] 确认本表不保存客户昵称，需要时关联客户映射表。
- [x] 确认周客户交易金额汇总第5张表的`transaction_amount`。
- [x] 确认本表保存毛销售额，不直接扣减退款。
- [x] 确认无销售记录的“自然周 + 客户ID”组合不生成补零记录。
- [x] 确认空白客户ID和非正数金额不允许写入。
- [x] 确认上述真实样例和总体结果可以作为正式上传后的校验基准。

## 20. 用户修改区

请直接在下方填写需要修改的内容：

```text
（待填写）
```

## 21. 实际执行与校验结果

执行时间：2026-08-10 11:03:06（北京时间）。

- 建表、自然周客户汇总和事务内校验在同一PostgreSQL事务中完成，全部通过后成功提交。
- 实际写入3,650条周客户销售记录、7个字段。
- 有销售客户ID：946个；不同自然周：79周。
- 最早周开始日期：2025-01-27；最晚周结束日期：2026-08-02。
- 周客户销售金额合计：5,709,898.66。
- 必填字段空值、重复业务键、错误自然周、空白客户ID和非正数金额均为0。
- 与`daily_customer_sales`重新全量汇总相比，金额不一致记录为0条。
- 无法关联`customer_id_mapping`的客户ID为0个。
- 主键、自然周、客户ID非空白、正数金额和业务唯一约束均已生效。
- 本文6条正式样例已逐条与数据库核对一致，且完整包含`customer_id`。
- 表所有者为`root`。
