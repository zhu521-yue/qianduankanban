# 快手小店第8张表审核草稿：`kuaishouxiaodian.weekly_product_sales`

> 状态：已确认、已建表、已上传数据、已校验通过  
> 数据库：`weidian`  
> Schema：`kuaishouxiaodian`  
> 表序号：08 / 35  
> 上游表：`kuaishouxiaodian.daily_product_sales`  
> 样例说明：本文样例已经使用第8张正式表中的实际记录复核并更新。

## 1. 表的作用

`weekly_product_sales`用于保存快手小店每个SKU编码在每个自然周内的销售金额和销售数量。一条记录代表“一个完整自然周 + 一个SKU编码”的汇总结果。

本表用于商品周销售排行、商品周销量、商品趋势以及后续月商品销售额等表的计算。

## 2. 自然周定义

- 每周第一天：星期一。
- 每周最后一天：星期日。
- `period_start`必须是星期一。
- `period_end`必须等于`period_start + 6天`。
- 跨月、跨年时仍保留完整的自然周边界。
- 周内某一天没有该商品的销售记录，不会缩短自然周范围。

示例：

```text
交易日期：2025-03-01（星期六）
所属自然周：2025-02-24 至 2025-03-02
```

## 3. 数据粒度与唯一性

- 一条记录代表一个SKU编码在一个自然周内的销售汇总。
- 主键：`id`。
- 业务唯一键：`period_start + period_end + product_code`。
- 同一个SKU编码在同一个自然周只能存在一条记录。
- 某个SKU编码在某个自然周完全没有销售记录时，不生成金额和数量为0的补零记录。

## 4. 字段设计

本表严格保留以下8个字段：

| 序号 | 字段 | PostgreSQL类型 | 是否必填 | 默认值 | 说明 |
|---:|---|---|---|---|---|
| 1 | `id` | `BIGINT` | 是 | 自增 | 主键，由数据库自动生成 |
| 2 | `period_start` | `DATE` | 是 | 无 | 自然周开始日期，必须是星期一 |
| 3 | `period_end` | `DATE` | 是 | 无 | 自然周结束日期，必须是星期日 |
| 4 | `product_code` | `TEXT` | 是 | 无 | 商品编码，严格沿用`SKU编码` |
| 5 | `weekly_transaction_amount` | `NUMERIC(18,2)` | 是 | `0` | 该SKU在该自然周的毛销售金额 |
| 6 | `weekly_product_quantity` | `BIGINT` | 是 | `0` | 该SKU在该自然周的销售数量 |
| 7 | `created_at` | `TIMESTAMPTZ` | 是 | `CURRENT_TIMESTAMP` | 首次插入数据库的北京时间 |
| 8 | `updated_at` | `TIMESTAMPTZ` | 是 | `CURRENT_TIMESTAMP` | 最近刷新该记录的北京时间 |

## 5. 数据来源与字段映射

本表基于第4张正式表`daily_product_sales`二次汇总，不直接重复读取`raw_data`。

| 目标字段 | 上游字段 | 处理方式 |
|---|---|---|
| `period_start` | `daily_product_sales.transaction_date` | 向前推算至所属自然周的星期一 |
| `period_end` | `period_start` | 加6天得到星期日 |
| `product_code` | `daily_product_sales.product_code` | 原值保留，分组字段 |
| `weekly_transaction_amount` | `daily_product_sales.transaction_amount` | 同一自然周、同一商品编码求和 |
| `weekly_product_quantity` | `daily_product_sales.product_quantity` | 同一自然周、同一商品编码求和 |

第4张表当前结构和规模：

- 7个字段。
- 32,550条“交易日期 + SKU编码”日汇总记录。
- 3,208个不同SKU编码。
- 交易日期范围：2025-02-01至2026-07-28。
- 交易金额合计：6,247,470.14。
- 商品数量合计：127,787。

## 6. 继承第4张表的业务口径

由于本表完全从`daily_product_sales`汇总，因此继承第4张表已经确认的全部规则：

- 有效订单状态为`交易成功`、`已发货`、`已收货`。
- 交易金额使用原始字段`实付款`，保存毛销售额，不直接扣减退款。
- 商品数量使用原始字段`成交数量`。
- 商品编码只使用`SKU编码`。
- `SKU编码`为空的原始订单不进入商品维度表。
- 不使用`商品ID`、组合编码或其他字段补充空白SKU编码。
- 本表不是客户相关表，因此不筛选`渠道 = '分销'`，包含全部渠道的有效商品销售。

## 7. 与整体周销售额表的金额差异

第6张`weekly_sales`的销售金额合计为6,254,453.47，而本表预计算金额合计为6,247,470.14，相差6,983.33。

这不是汇总错误，原因是：

- `weekly_sales`统计全部有效销售订单。
- 商品维度要求SKU编码有值。
- 第4张表已经排除136条SKU编码为空的有效销售原始记录。
- 被排除记录的金额合计为6,983.33、商品数量合计为138。

因此，第8张表必须与`daily_product_sales`核对，不能强制与整体`weekly_sales`金额相等。

## 8. 自然周计算逻辑

PostgreSQL的`ISODOW`规定星期一为1、星期日为7：

```sql
transaction_date
    - (EXTRACT(ISODOW FROM transaction_date)::INTEGER - 1)
    AS period_start,

transaction_date
    - (EXTRACT(ISODOW FROM transaction_date)::INTEGER - 1)
    + 6
    AS period_end
```

分组顺序为：

```text
先按照自然周分组
→ 再按照product_code分组
→ 分别汇总transaction_amount和product_quantity
```

数据库实际使用`period_start + period_end + product_code`同时分组，结果与上述业务顺序一致。

## 9. 当前正式表数据结果

| 检查项目 | 结果 |
|---|---:|
| 实际周商品记录 | 16,932条 |
| 不同SKU编码 | 3,208个 |
| 不同自然周 | 79周 |
| 最早周开始日期 | 2025-01-27 |
| 最晚周结束日期 | 2026-08-02 |
| 周商品销售金额合计 | 6,247,470.14 |
| 周商品数量合计 | 127,787 |
| 非星期一开始或周期长度错误 | 0条 |
| 空白商品编码 | 0条 |
| 非正数周商品金额 | 0条 |
| 非正数周商品数量 | 0条 |

周商品销售金额和数量分别与第4张表全量金额、数量完全一致。

## 10. 正式表真实记录样例

| `id` | `period_start` | `period_end` | `product_code` | `weekly_transaction_amount` | `weekly_product_quantity` | `created_at` | `updated_at` |
|---:|---|---|---|---:|---:|---|---|
| 2 | 2025-01-27 | 2025-02-02 | `KQ20221172` | 149.90 | 1 | 2026-08-10 10:54:23.456794+08 | 2026-08-10 10:54:23.456794+08 |
| 364 | 2025-02-24 | 2025-03-02 | `6941716547974` | 30,309.40 | 506 | 2026-08-10 10:54:23.456794+08 | 2026-08-10 10:54:23.456794+08 |
| 6,826 | 2025-06-30 | 2025-07-06 | `KK20257516` | 2,182.60 | 14 | 2026-08-10 10:54:23.456794+08 | 2026-08-10 10:54:23.456794+08 |
| 10,952 | 2026-01-26 | 2026-02-01 | `6941716573539` | 13,833.20 | 508 | 2026-08-10 10:54:23.456794+08 | 2026-08-10 10:54:23.456794+08 |
| 11,842 | 2026-03-16 | 2026-03-22 | `6974318539931` | 14,735.40 | 246 | 2026-08-10 10:54:23.456794+08 | 2026-08-10 10:54:23.456794+08 |
| 16,876 | 2026-07-27 | 2026-08-02 | `6941716542054` | 3,257.60 | 324 | 2026-08-10 10:54:23.456794+08 | 2026-08-10 10:54:23.456794+08 |

例如，SKU编码`6941716547974`在2025-02-24至2025-03-02自然周内有2条日汇总记录，交易金额合计30,309.40，商品数量合计506。

## 11. 自然周整体汇总辅助样例

下表只用于检查同一周内有多少个商品，不是第8张表的字段结构：

| `period_start` | `period_end` | 商品数 | 周内全部商品金额 | 周内全部商品数量 |
|---|---|---:|---:|---:|
| 2025-01-27 | 2025-02-02 | 2 | 179.80 | 2 |
| 2025-02-03 | 2025-02-09 | 29 | 3,300.00 | 40 |
| 2025-02-10 | 2025-02-16 | 42 | 56,901.20 | 498 |
| 2025-02-17 | 2025-02-23 | 87 | 19,677.90 | 281 |
| 2025-02-24 | 2025-03-02 | 360 | 355,307.10 | 6,829 |

## 12. 拟执行建表SQL

```sql
CREATE TABLE kuaishouxiaodian.weekly_product_sales (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    product_code TEXT NOT NULL,
    weekly_transaction_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    weekly_product_quantity BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT weekly_product_sales_period_check CHECK (
        EXTRACT(ISODOW FROM period_start) = 1
        AND period_end = period_start + 6
    ),
    CONSTRAINT weekly_product_sales_product_code_check CHECK (
        BTRIM(product_code) <> ''
    ),
    CONSTRAINT weekly_product_sales_amount_check CHECK (
        weekly_transaction_amount > 0
    ),
    CONSTRAINT weekly_product_sales_quantity_check CHECK (
        weekly_product_quantity > 0
    ),
    CONSTRAINT weekly_product_sales_business_uk UNIQUE (
        period_start,
        period_end,
        product_code
    )
);
```

## 13. 首次数据生成SQL

```sql
INSERT INTO kuaishouxiaodian.weekly_product_sales (
    period_start,
    period_end,
    product_code,
    weekly_transaction_amount,
    weekly_product_quantity
)
SELECT
    transaction_date
        - (EXTRACT(ISODOW FROM transaction_date)::INTEGER - 1)
        AS period_start,
    transaction_date
        - (EXTRACT(ISODOW FROM transaction_date)::INTEGER - 1)
        + 6
        AS period_end,
    product_code,
    SUM(transaction_amount)::NUMERIC(18,2)
        AS weekly_transaction_amount,
    SUM(product_quantity)::BIGINT
        AS weekly_product_quantity
FROM kuaishouxiaodian.daily_product_sales
GROUP BY period_start, period_end, product_code
ORDER BY period_start, product_code;
```

## 14. 原子建表与上传流程

1. 开启PostgreSQL事务，并将事务时区设置为`Asia/Shanghai`。
2. 创建`kuaishouxiaodian.weekly_product_sales`。
3. 读取第4张表的交易日期、商品编码、交易金额和商品数量。
4. 将每个交易日期换算为所属自然周的星期一和星期日。
5. 按`period_start + period_end + product_code`分组。
6. 分别汇总交易金额和商品数量。
7. 写入周商品销售记录。
8. 校验字段数、记录数、业务键唯一性、商品编码、自然周边界和正数金额数量。
9. 将全部周商品金额、数量与`daily_product_sales`全量金额、数量核对，差异必须均为0。
10. 核对本文真实样例。
11. 全部通过后提交；任一环节失败则回滚建表和全部数据写入。

## 15. 后续日商品销售数据变动时的刷新逻辑

每次原始文件上传导致`daily_product_sales`新增或更新后，在同一事务内刷新受影响的自然周和商品编码：

```text
daily_product_sales新增或更新
→ 根据受影响交易日期定位自然周
→ 获取受影响的product_code
→ 删除weekly_product_sales中对应“自然周 + product_code”的旧记录
→ 使用该自然周内该product_code的全部日记录重新汇总
→ 写入新的周商品销售记录
→ 校验通过后与上游变动一起提交
→ 任一步失败则全部回滚
```

## 16. 正式上传后验证规则

- 表字段数必须为8个。
- 当前数据下记录数必须为16,932条。
- 必填字段空值必须为0条。
- 重复`period_start + period_end + product_code`必须为0组。
- 空白`product_code`必须为0条。
- `period_start`必须全部为星期一。
- `period_end`必须全部等于`period_start + 6天`。
- 非正数周商品金额和商品数量必须均为0条。
- 最早周开始日期必须为2025-01-27。
- 最晚周结束日期必须为2026-08-02。
- 不同SKU编码必须为3,208个，不同自然周必须为79周。
- 周商品销售金额合计必须为6,247,470.14。
- 周商品数量合计必须为127,787。
- 与`daily_product_sales`重新全量汇总相比，金额和数量差异必须均为0。
- 本文列出的6条商品周样例必须与正式表逐条一致。

## 17. 用户审核确认项

- [x] 确认本表严格保留8个字段。
- [x] 确认数据粒度为“一个自然周 + 一个SKU编码”。
- [x] 确认自然周定义为星期一至星期日。
- [x] 确认`product_code`只沿用SKU编码，不使用其他编码补充。
- [x] 确认周交易金额和周商品数量分别汇总第4张表对应字段。
- [x] 确认本表保存毛销售额，不直接扣减退款。
- [x] 确认本表不是客户相关表，因此不筛选分销渠道。
- [x] 确认无销售记录的“自然周 + SKU编码”组合不生成补零记录。
- [x] 确认空白商品编码、非正数金额和非正数数量不允许写入。
- [x] 确认上述真实样例和总体结果可以作为正式上传后的校验基准。

## 18. 用户修改区

请直接在下方填写需要修改的内容：

```text
（待填写）
```

## 19. 实际执行与校验结果

执行时间：2026-08-10 10:54:23（北京时间）。

- 建表、自然周与商品汇总、事务内校验在同一PostgreSQL事务中完成，全部通过后成功提交。
- 实际写入16,932条周商品销售记录、8个字段。
- 不同SKU编码：3,208个；不同自然周：79周。
- 最早周开始日期：2025-01-27；最晚周结束日期：2026-08-02。
- 周商品销售金额合计：6,247,470.14。
- 周商品数量合计：127,787。
- 必填字段空值、重复业务键、错误自然周、空白商品编码、非正数金额和非正数数量均为0。
- 与`daily_product_sales`重新全量汇总相比，金额不一致记录为0条，数量不一致记录为0条。
- 主键、自然周、商品编码非空白、正数金额、正数数量和业务唯一约束均已生效。
- 本文6条正式样例已逐条与数据库核对一致。
- 表所有者为`root`。
