# 快手小店第17张表审核草稿：`kuaishouxiaodian.quarterly_customer_sales`

> 状态：已确认、已建表、已上传、已校验  
> 数据库：`weidian`  
> Schema：`kuaishouxiaodian`  
> 表序号：17 / 35  
> 上游：`kuaishouxiaodian.daily_customer_sales`  
> 样例说明：本文样例直接查询正式表，完整保留`id`、`customer_id`、全部业务字段、`created_at`和`updated_at`。

## 1. 表的作用

`quarterly_customer_sales`用于保存每个分销客户在每个自定义季度内的销售金额。一条记录代表“一个自定义季度 + 一个客户ID”的汇总结果。

## 2. 周期定义

- 季度固定划分为2—4月、5—7月、8—10月、11月—次年1月；1月归入上一年11月开始的季度。
- 当前数据形成6个自定义季度：2025-02—04、2025-05—07、2025-08—10、2025-11—2026-01、2026-02—04、2026-05—07。
- 当前最后一个周期为2026-05-01至2026-07-31，但当前源数据只到2026-07-28；周期仍保存完整自定义季度边界。
- 某个完整周期没有有效记录时，不主动生成金额为0的补零记录。

## 3. 数据粒度与唯一性

- 数据粒度：一个自定义季度 + 一个客户ID。
- 主键：`id`。
- 业务唯一键：`period_start + period_end + customer_id`。
- 同一业务唯一键只能出现一条记录。
- 目标表所有正式样例必须完整列出全部业务维度字段。

## 4. 字段设计

本表严格保留以下7个字段：

| 序号 | 字段 | PostgreSQL类型 | 是否必填 | 默认值 | 说明 |
|---:|---|---|---|---|---|
| 1 | `id` | `BIGINT` | 是 | 自增 | 主键，由数据库自动生成 |
| 2 | `period_start` | `DATE` | 是 | 无 | 一个自定义季度开始日期 |
| 3 | `period_end` | `DATE` | 是 | 无 | 一个自定义季度结束日期 |
| 4 | `customer_id` | `TEXT` | 是 | 无 | 客户ID，不允许空白 |
| 5 | `quarterly_transaction_amount` | `NUMERIC(18,2)` | 是 | `0` | 本周期销售金额之和 |
| 6 | `created_at` | `TIMESTAMPTZ` | 是 | `CURRENT_TIMESTAMP` | 首次插入数据库的北京时间 |
| 7 | `updated_at` | `TIMESTAMPTZ` | 是 | `CURRENT_TIMESTAMP` | 最近刷新记录的北京时间 |

## 5. 数据来源与字段映射

上游数据：`kuaishouxiaodian.daily_customer_sales`。

| 目标字段 | 上游字段 | 处理方式 |
|---|---|---|
| `period_start` | `transaction_date` | 按已确认规则换算为所属自定义季度开始日期 |
| `period_end` | `transaction_date` | 按已确认规则换算为所属自定义季度结束日期 |
| `customer_id` | `customer_id` | 原值继承后参与分组 |
| `quarterly_transaction_amount` | `transaction_amount` | 按周期及维度求和 |

`id`由数据库自增生成；`created_at`和`updated_at`按数据插入时的北京时间生成。

## 6. 必须继承的业务口径

- 完全继承第5张`daily_customer_sales`的有效销售、日期和金额口径。
- 凡是客户相关表，必须只汇总`渠道 = '分销'`的记录；该筛选已经在第5张表中完成。
- 客户ID优先级为：CPS达人ID → 团长ID → 快赚客ID。
- 本表必须保留完整`customer_id`，不保存客户昵称；昵称需要时关联`customer_id_mapping`。
- 保存毛销售额，不直接扣减退款。
- 当前分销客户金额比全部渠道销售额少544,554.81，这是渠道筛选造成的已确认差异。

## 7. 周期计算规则

`period_start`计算：

```sql
CASE
    WHEN EXTRACT(MONTH FROM transaction_date) BETWEEN 2 AND 4
        THEN MAKE_DATE(EXTRACT(YEAR FROM transaction_date)::INTEGER, 2, 1)
    WHEN EXTRACT(MONTH FROM transaction_date) BETWEEN 5 AND 7
        THEN MAKE_DATE(EXTRACT(YEAR FROM transaction_date)::INTEGER, 5, 1)
    WHEN EXTRACT(MONTH FROM transaction_date) BETWEEN 8 AND 10
        THEN MAKE_DATE(EXTRACT(YEAR FROM transaction_date)::INTEGER, 8, 1)
    WHEN EXTRACT(MONTH FROM transaction_date) = 1
        THEN MAKE_DATE(EXTRACT(YEAR FROM transaction_date)::INTEGER - 1, 11, 1)
    ELSE MAKE_DATE(EXTRACT(YEAR FROM transaction_date)::INTEGER, 11, 1)
END
```

`period_end`计算：

```sql
CASE
    WHEN EXTRACT(MONTH FROM transaction_date) BETWEEN 2 AND 4
        THEN MAKE_DATE(EXTRACT(YEAR FROM transaction_date)::INTEGER, 4, 30)
    WHEN EXTRACT(MONTH FROM transaction_date) BETWEEN 5 AND 7
        THEN MAKE_DATE(EXTRACT(YEAR FROM transaction_date)::INTEGER, 7, 31)
    WHEN EXTRACT(MONTH FROM transaction_date) BETWEEN 8 AND 10
        THEN MAKE_DATE(EXTRACT(YEAR FROM transaction_date)::INTEGER, 10, 31)
    WHEN EXTRACT(MONTH FROM transaction_date) = 1
        THEN MAKE_DATE(EXTRACT(YEAR FROM transaction_date)::INTEGER, 1, 31)
    ELSE MAKE_DATE(EXTRACT(YEAR FROM transaction_date)::INTEGER + 1, 1, 31)
END
```

## 8. 分组与聚合流程

```text
读取上游有效记录
→ 根据transaction_date确定period_start与period_end
→ 按period_start + period_end + customer_id分组
→ 汇总transaction_amount
→ 生成目标记录
```

## 9. 正式上传与校验结果

| 检查项目 | 结果 |
|---|---:|
| 正式记录数 | 1,371条 |
| 不同自定义季度 | 6个 |
| 有销售客户ID | 946个 |
| 最早周期开始日期 | 2025-02-01 |
| 最晚周期结束日期 | 2026-07-31 |
| 金额合计 | 5,709,898.66 |
| 与对应上游金额合计差异 | 0.00 |
| 周期边界、空白维度或非正数记录 | 0条 |

## 10. 正式表完整字段样例

| `id` | `period_start` | `period_end` | `customer_id` | `quarterly_transaction_amount` | `created_at` | `updated_at` |
|---:|---|---|---|---:|---|---|
| 296 | 2025-02-01 | 2025-04-30 | `745575951` | 1,145,596.60 | 2026-08-10 11:33:08.180113+08 | 2026-08-10 11:33:08.180113+08 |
| 738 | 2025-05-01 | 2025-07-31 | `745575951` | 628,748.02 | 2026-08-10 11:33:08.180113+08 | 2026-08-10 11:33:08.180113+08 |
| 786 | 2025-08-01 | 2025-10-31 | `1098269263` | 69,916.40 | 2026-08-10 11:33:08.180113+08 | 2026-08-10 11:33:08.180113+08 |
| 979 | 2025-11-01 | 2026-01-31 | `1833627526` | 57,624.69 | 2026-08-10 11:33:08.180113+08 | 2026-08-10 11:33:08.180113+08 |
| 1,180 | 2026-02-01 | 2026-04-30 | `745575951` | 403,791.80 | 2026-08-10 11:33:08.180113+08 | 2026-08-10 11:33:08.180113+08 |
| 1,308 | 2026-05-01 | 2026-07-31 | `415121040` | 62,865.94 | 2026-08-10 11:33:08.180113+08 | 2026-08-10 11:33:08.180113+08 |

以上样例从正式表中选取每个自定义季度销售金额最高的一条记录；正式表已写入全部有效组合。

## 11. 金额与其他表的关系

- 本表金额合计为5,709,898.66。
- 本表保存毛销售额，不在表内直接扣减退款。
- 本表必须从自身上游按当前周期重新汇总，不能直接累计可能跨周期边界的周记录。

## 12. 正式执行的建表SQL

```sql
CREATE TABLE kuaishouxiaodian.quarterly_customer_sales (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    customer_id TEXT NOT NULL,
    quarterly_transaction_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT quarterly_customer_sales_period_check CHECK (
        EXTRACT(DAY FROM period_start) = 1
        AND EXTRACT(MONTH FROM period_start) IN (2, 5, 8, 11)
        AND period_end = (period_start + INTERVAL '3 months - 1 day')::DATE
    ),
    CONSTRAINT quarterly_customer_sales_customer_id_check CHECK (
        BTRIM(customer_id) <> ''
    ),
    CONSTRAINT quarterly_customer_sales_amount_check CHECK (
        quarterly_transaction_amount > 0
    ),
    CONSTRAINT quarterly_customer_sales_business_uk UNIQUE (
        period_start, period_end, customer_id
    )
);
```

## 13. 首次数据生成SQL

```sql
INSERT INTO kuaishouxiaodian.quarterly_customer_sales (
    period_start,
    period_end,
    customer_id,
    quarterly_transaction_amount
)
SELECT
    CASE
        WHEN EXTRACT(MONTH FROM transaction_date) BETWEEN 2 AND 4
            THEN MAKE_DATE(EXTRACT(YEAR FROM transaction_date)::INTEGER, 2, 1)
        WHEN EXTRACT(MONTH FROM transaction_date) BETWEEN 5 AND 7
            THEN MAKE_DATE(EXTRACT(YEAR FROM transaction_date)::INTEGER, 5, 1)
        WHEN EXTRACT(MONTH FROM transaction_date) BETWEEN 8 AND 10
            THEN MAKE_DATE(EXTRACT(YEAR FROM transaction_date)::INTEGER, 8, 1)
        WHEN EXTRACT(MONTH FROM transaction_date) = 1
            THEN MAKE_DATE(EXTRACT(YEAR FROM transaction_date)::INTEGER - 1, 11, 1)
        ELSE MAKE_DATE(EXTRACT(YEAR FROM transaction_date)::INTEGER, 11, 1)
    END AS period_start,
    CASE
        WHEN EXTRACT(MONTH FROM transaction_date) BETWEEN 2 AND 4
            THEN MAKE_DATE(EXTRACT(YEAR FROM transaction_date)::INTEGER, 4, 30)
        WHEN EXTRACT(MONTH FROM transaction_date) BETWEEN 5 AND 7
            THEN MAKE_DATE(EXTRACT(YEAR FROM transaction_date)::INTEGER, 7, 31)
        WHEN EXTRACT(MONTH FROM transaction_date) BETWEEN 8 AND 10
            THEN MAKE_DATE(EXTRACT(YEAR FROM transaction_date)::INTEGER, 10, 31)
        WHEN EXTRACT(MONTH FROM transaction_date) = 1
            THEN MAKE_DATE(EXTRACT(YEAR FROM transaction_date)::INTEGER, 1, 31)
        ELSE MAKE_DATE(EXTRACT(YEAR FROM transaction_date)::INTEGER + 1, 1, 31)
    END AS period_end,
    customer_id,
    SUM(transaction_amount)::NUMERIC(18,2) AS quarterly_transaction_amount
FROM kuaishouxiaodian.daily_customer_sales
GROUP BY period_start, period_end, customer_id
ORDER BY period_start, period_end, customer_id;
```



## 14. 原子建表与上传流程

1. 开启PostgreSQL事务，并将事务时区设置为`Asia/Shanghai`。
2. 创建`kuaishouxiaodian.quarterly_customer_sales`。
3. 读取并校验上游字段、记录粒度和业务口径。
4. 计算每条上游记录所属的自定义季度。
5. 按业务唯一键分组并聚合。
6. 写入目标记录。
7. 校验字段数、记录数、周期边界、业务键、金额和上游重算结果。
8. 全部通过后提交；任一环节失败则回滚建表和全部数据写入。

## 15. 后续上游数据变动时的刷新逻辑

```text
上游数据新增或更新
→ 定位受影响的自定义季度和业务维度
→ 删除目标表中的对应旧记录
→ 使用该周期内的全部上游记录重新汇总
→ 写入新记录并更新updated_at
→ 校验通过后与上游变动一起提交
→ 任一步失败则全部回滚
```

## 16. 正式上传验证规则

- 表字段数必须为7个。
- 当前数据下记录数必须为1,371条。
- 不同自定义季度必须为6个。
- 最早周期开始日期必须为2025-02-01。
- 最晚周期结束日期必须为2026-07-31。
- 必填字段空值和重复业务键必须均为0。
- 所有周期必须符合已确认的季度固定划分为2—4月、5—7月、8—10月、11月—次年1月；1月归入上一年11月开始的季度。
- `quarterly_transaction_amount`必须全部大于0，金额合计必须为5,709,898.66。
- 空白`customer_id`必须为0条，不同客户ID必须为946个。
- 无法关联`customer_id_mapping`的客户ID必须为0个。
- 与上游重新全量汇总相比，金额差异必须为0。
- 本文真实样例必须与正式表逐条一致。

## 17. 用户审核确认项

- [x] 确认本表严格保留7个字段。
- [x] 确认数据粒度为“一个自定义季度 + 一个客户ID”。
- [x] 确认周期规则为：季度固定划分为2—4月、5—7月、8—10月、11月—次年1月；1月归入上一年11月开始的季度。
- [x] 确认本表只统计分销渠道。
- [x] 确认金额字段为`quarterly_transaction_amount`，口径与上游一致。
- [x] 确认不生成无数据周期或组合的补零记录。
- [x] 确认目标表与上游变更采用同一事务，任一步失败全部回滚。
- [x] 确认只统计分销渠道，并完整保留`customer_id`。
- [x] 确认客户ID优先级为CPS达人ID → 团长ID → 快赚客ID。
- [x] 确认上述真实样例和总体结果可以作为正式上传后的校验基准。

## 18. 用户修改区

请直接在下方填写需要修改的内容：

```text
（待填写）
```

## 19. 实际执行与校验结果

- 正式上传记录数：1,371条。
- 自定义季度数：6个，范围为2025-02-01至2026-07-31。
- 有销售客户ID：946个。
- 销售金额合计：5,709,898.66。
- 字段缺失、必填字段空值、重复业务键、非法周期、空白`customer_id`及非正数金额：均为0条。
- 与`daily_customer_sales`按相同自定义季度和`customer_id`全量重算的记录及金额差异：均为0。
- 与`customer_id_mapping`无法关联的客户记录：0条。
- 表所有者：`root`。
- `created_at`和`updated_at`统一为北京时间`2026-08-10 11:33:08.180113+08`。
- 本表与同批次其他销售维度表在一个总事务中一次性提交成功；任一校验失败均会使总事务回滚。
