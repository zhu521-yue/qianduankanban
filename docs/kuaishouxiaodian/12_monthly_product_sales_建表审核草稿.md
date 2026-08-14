# 快手小店第12张表审核草稿：`kuaishouxiaodian.monthly_product_sales`

> 状态：已确认、已建表、已上传、已校验  
> 数据库：`weidian`  
> Schema：`kuaishouxiaodian`  
> 表序号：12 / 35  
> 上游：`kuaishouxiaodian.daily_product_sales`  
> 样例说明：本文样例来自正式数据库，完整列出本表全部字段，包括SKU编码。

## 1. 表的作用

`monthly_product_sales`用于保存每个SKU编码在每个自然月内的销售金额和商品数量。一条记录代表“一个自然月 + 一个SKU编码”的汇总结果。

## 2. 周期定义

- 每月1日至当月最后一日；2月结束日期自动按平年或闰年确定。
- 当前数据形成18个自然月，2025年2月至2026年7月。
- 当前最后一个周期为2026-07-01至2026-07-31，但当前源数据只到2026-07-28；周期仍保存完整自然月边界。
- 某个完整周期没有有效记录时，不主动生成金额为0的补零记录。

## 3. 数据粒度与唯一性

- 数据粒度：一个自然月 + 一个SKU编码。
- 主键：`id`。
- 业务唯一键：`period_start + period_end + product_code`。
- 同一业务唯一键只能出现一条记录。
- 目标表所有正式样例必须完整列出全部业务维度字段。

## 4. 字段设计

本表严格保留以下8个字段：

| 序号 | 字段 | PostgreSQL类型 | 是否必填 | 默认值 | 说明 |
|---:|---|---|---|---|---|
| 1 | `id` | `BIGINT` | 是 | 自增 | 主键，由数据库自动生成 |
| 2 | `period_start` | `DATE` | 是 | 无 | 一个自然月开始日期 |
| 3 | `period_end` | `DATE` | 是 | 无 | 一个自然月结束日期 |
| 4 | `product_code` | `TEXT` | 是 | 无 | SKU编码，不允许空白 |
| 5 | `monthly_transaction_amount` | `NUMERIC(18,2)` | 是 | `0` | 本周期销售金额之和 |
| 6 | `monthly_product_quantity` | `BIGINT` | 是 | `0` | 本周期商品数量之和 |
| 7 | `created_at` | `TIMESTAMPTZ` | 是 | `CURRENT_TIMESTAMP` | 首次插入数据库的北京时间 |
| 8 | `updated_at` | `TIMESTAMPTZ` | 是 | `CURRENT_TIMESTAMP` | 最近刷新记录的北京时间 |

## 5. 数据来源与字段映射

上游数据：`kuaishouxiaodian.daily_product_sales`。

| 目标字段 | 上游字段 | 处理方式 |
|---|---|---|
| `period_start` | `transaction_date` | 按已确认规则换算为所属自然月开始日期 |
| `period_end` | `transaction_date` | 按已确认规则换算为所属自然月结束日期 |
| `product_code` | `product_code` | 原值继承后参与分组 |
| `monthly_transaction_amount` | `transaction_amount` | 按周期及维度求和 |
| `monthly_product_quantity` | `product_quantity` | 按周期及SKU编码求和 |

`id`由数据库自增生成；`created_at`和`updated_at`按数据插入时的北京时间生成。

## 6. 必须继承的业务口径

- 完全继承第4张`daily_product_sales`的有效销售、日期、金额和数量口径。
- 商品编码只使用原始`SKU编码`；SKU编码为空的记录已经在第4张表中作废并排除。
- 保存毛销售额和商品数量，不直接扣减退款。
- 商品相关表包含全部渠道，不筛选分销渠道。
- 当前因空白SKU被排除的金额为6,983.33，因此商品销售金额合计与整体销售额不同，这是已确认的业务差异。

## 7. 周期计算规则

`period_start`计算：

```sql
DATE_TRUNC('month', transaction_date)::DATE
```

`period_end`计算：

```sql
(DATE_TRUNC('month', transaction_date) + INTERVAL '1 month - 1 day')::DATE
```

## 8. 分组与聚合流程

```text
读取上游有效记录
→ 根据transaction_date确定period_start与period_end
→ 按period_start + period_end + product_code分组
→ 汇总transaction_amount和product_quantity
→ 生成目标记录
```

## 9. 正式实际执行结果

| 检查项目 | 结果 |
|---|---:|
| 正式记录数 | 9,044条 |
| 不同自然月 | 18个 |
| 不同SKU编码 | 3,208个 |
| 最早周期开始日期 | 2025-02-01 |
| 最晚周期结束日期 | 2026-07-31 |
| 金额合计 | 6,247,470.14 |
| 商品数量合计 | 127,787 |
| 与对应上游金额合计差异 | 0.00 |
| 周期边界、空白维度或非正数记录 | 0条 |

## 10. 正式数据库完整字段样例

| `id` | `period_start` | `period_end` | `product_code` | `monthly_transaction_amount` | `monthly_product_quantity` | `created_at` | `updated_at` |
|---:|---|---|---|---:|---:|---|---|
| 94 | 2025-02-01 | 2025-02-28 | `6941716550103` | 16,638.90 | 111 | 2026-08-10 11:33:08.180113+08 | 2026-08-10 11:33:08.180113+08 |
| 3601 | 2025-07-01 | 2025-07-31 | `KK20257726` | 37,620.00 | 380 | 2026-08-10 11:33:08.180113+08 | 2026-08-10 11:33:08.180113+08 |
| 5151 | 2025-12-01 | 2025-12-31 | `6941716553708` | 6,508.00 | 320 | 2026-08-10 11:33:08.180113+08 | 2026-08-10 11:33:08.180113+08 |
| 5532 | 2026-01-01 | 2026-01-31 | `6941716573539` | 13,166.70 | 483 | 2026-08-10 11:33:08.180113+08 | 2026-08-10 11:33:08.180113+08 |
| 7613 | 2026-05-01 | 2026-05-31 | `6941716542047` | 27,840.10 | 1,399 | 2026-08-10 11:33:08.180113+08 | 2026-08-10 11:33:08.180113+08 |
| 8747 | 2026-07-01 | 2026-07-31 | `6941716542054` | 18,945.60 | 1,840 | 2026-08-10 11:33:08.180113+08 | 2026-08-10 11:33:08.180113+08 |

以上正式样例完整保留`product_code`，并已逐条查询正式表确认。

## 11. 金额与其他表的关系

- 本表金额合计为6,247,470.14。
- 本表保存毛销售额，不在表内直接扣减退款。
- 本表必须从自身上游按当前周期重新汇总，不能直接累计可能跨周期边界的周记录。

## 12. 正式采用的建表SQL

```sql
CREATE TABLE kuaishouxiaodian.monthly_product_sales (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    product_code TEXT NOT NULL,
    monthly_transaction_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    monthly_product_quantity BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT monthly_product_sales_period_check CHECK (
        period_start = DATE_TRUNC('month', period_start)::DATE
        AND period_end = (
            DATE_TRUNC('month', period_start)
            + INTERVAL '1 month - 1 day'
        )::DATE
    ),
    CONSTRAINT monthly_product_sales_product_code_check CHECK (
        BTRIM(product_code) <> ''
    ),
    CONSTRAINT monthly_product_sales_amount_check CHECK (
        monthly_transaction_amount > 0
    ),
    CONSTRAINT monthly_product_sales_quantity_check CHECK (
        monthly_product_quantity > 0
    ),
    CONSTRAINT monthly_product_sales_business_uk UNIQUE (
        period_start, period_end, product_code
    )
);
```

## 13. 首次数据生成SQL

```sql
INSERT INTO kuaishouxiaodian.monthly_product_sales (
    period_start,
    period_end,
    product_code,
    monthly_transaction_amount,
    monthly_product_quantity
)
SELECT
    DATE_TRUNC('month', transaction_date)::DATE AS period_start,
    (DATE_TRUNC('month', transaction_date) + INTERVAL '1 month - 1 day')::DATE AS period_end,
    product_code,
    SUM(transaction_amount)::NUMERIC(18,2) AS monthly_transaction_amount,
    SUM(product_quantity)::BIGINT AS monthly_product_quantity
FROM kuaishouxiaodian.daily_product_sales
GROUP BY period_start, period_end, product_code
ORDER BY period_start, period_end, product_code;
```



## 14. 实际原子建表与上传流程

1. 开启PostgreSQL事务，并将事务时区设置为`Asia/Shanghai`。
2. 创建`kuaishouxiaodian.monthly_product_sales`。
3. 读取并校验上游字段、记录粒度和业务口径。
4. 计算每条上游记录所属的自然月。
5. 按业务唯一键分组并聚合。
6. 写入目标记录。
7. 校验字段数、记录数、周期边界、业务键、金额、数量和上游重算结果。
8. 全部通过后提交；任一环节失败则回滚建表和全部数据写入。

## 15. 后续上游数据变动时的刷新逻辑

```text
上游数据新增或更新
→ 定位受影响的自然月和业务维度
→ 删除目标表中的对应旧记录
→ 使用该周期内的全部上游记录重新汇总
→ 写入新记录并更新updated_at
→ 校验通过后与上游变动一起提交
→ 任一步失败则全部回滚
```

## 16. 正式上传验证规则

- 表字段数必须为8个。
- 当前数据下记录数必须为9,044条。
- 不同自然月必须为18个。
- 最早周期开始日期必须为2025-02-01。
- 最晚周期结束日期必须为2026-07-31。
- 必填字段空值和重复业务键必须均为0。
- 所有周期必须符合已确认的每月1日至当月最后一日；2月结束日期自动按平年或闰年确定。
- `monthly_transaction_amount`必须全部大于0，金额合计必须为6,247,470.14。
- `monthly_product_quantity`必须全部大于0，数量合计必须为127,787。
- 空白`product_code`必须为0条，不同SKU编码必须为3,208个。
- 与上游重新全量汇总相比，金额和数量差异必须为0。
- 本文真实样例必须与正式表逐条一致。

## 17. 用户审核确认项

- [x] 确认本表严格保留8个字段。
- [x] 确认数据粒度为“一个自然月 + 一个SKU编码”。
- [x] 确认周期规则为：每月1日至当月最后一日；2月结束日期自动按平年或闰年确定。
- [x] 确认本表包含全部渠道。
- [x] 确认金额字段为`monthly_transaction_amount`，口径与上游一致。
- [x] 确认不生成无数据周期或组合的补零记录。
- [x] 确认目标表与上游变更采用同一事务，任一步失败全部回滚。
- [x] 确认商品编码只使用SKU编码，空白SKU不会写入本表。
- [x] 确认上述真实样例和总体结果可以作为正式上传后的校验基准。

## 18. 用户修改区

请直接在下方填写需要修改的内容：

```text
（待填写）
```

## 19. 实际执行与校验结果

- 正式表于2026-08-10完成创建、数据写入和校验，表所有者为`root`。
- 正式写入9,044条记录，覆盖18个自然月和3,208个SKU编码，周期边界为2025-02-01至2026-07-31。
- `monthly_transaction_amount`合计为6,247,470.14，`monthly_product_quantity`合计为127,787。
- 必填字段空值、异常自然月边界、空白SKU、非正销售金额、非正商品数量和重复业务键均为0条。
- 从`daily_product_sales`按自然月和SKU编码全量重算后，逐业务键金额差异、数量差异均为0。
- `created_at`和`updated_at`统一为北京时间`2026-08-10 11:33:08.180113+08`。
- 本表与同批表在同一个总事务中完成创建、写入和校验；全部断言通过后一次性提交，未发生部分成功。
