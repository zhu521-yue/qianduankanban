# 快手小店第11张表审核草稿：`kuaishouxiaodian.monthly_refunds`

> 状态：已确认、已建表、已上传、已校验  
> 数据库：`weidian`  
> Schema：`kuaishouxiaodian`  
> 表序号：11 / 35  
> 上游：`kuaishouxiaodian.raw_data（沿用第7张表确认的订单级退款解析结果）`  
> 样例说明：本文样例来自正式数据库，完整列出本表全部字段。

## 1. 表的作用

`monthly_refunds`用于保存快手小店每个自然月的退款金额。一条记录代表“一个自然月”的汇总结果。

## 2. 周期定义

- 每月1日至当月最后一日；2月结束日期自动按平年或闰年确定。
- 当前数据形成18个自然月，2025年2月至2026年7月。
- 当前最后一个周期为2026-07-01至2026-07-31，但当前源数据只到2026-07-28；周期仍保存完整自然月边界。
- 某个完整周期没有有效记录时，不主动生成金额为0的补零记录。

## 3. 数据粒度与唯一性

- 数据粒度：一个自然月。
- 主键：`id`。
- 业务唯一键：`period_start + period_end`。
- 同一业务唯一键只能出现一条记录。
- 目标表所有正式样例必须完整列出全部业务维度字段。

## 4. 字段设计

本表严格保留以下6个字段：

| 序号 | 字段 | PostgreSQL类型 | 是否必填 | 默认值 | 说明 |
|---:|---|---|---|---|---|
| 1 | `id` | `BIGINT` | 是 | 自增 | 主键，由数据库自动生成 |
| 2 | `period_start` | `DATE` | 是 | 无 | 一个自然月开始日期 |
| 3 | `period_end` | `DATE` | 是 | 无 | 一个自然月结束日期 |
| 4 | `monthly_refund_amount` | `NUMERIC(18,2)` | 是 | `0` | 本周期退款金额之和 |
| 5 | `created_at` | `TIMESTAMPTZ` | 是 | `CURRENT_TIMESTAMP` | 首次插入数据库的北京时间 |
| 6 | `updated_at` | `TIMESTAMPTZ` | 是 | `CURRENT_TIMESTAMP` | 最近刷新记录的北京时间 |

## 5. 数据来源与字段映射

上游数据：`kuaishouxiaodian.raw_data（沿用第7张表确认的订单级退款解析结果）`。

| 目标字段 | 上游字段 | 处理方式 |
|---|---|---|
| `period_start` | `transaction_date` | 按已确认规则换算为所属自然月开始日期 |
| `period_end` | `transaction_date` | 按已确认规则换算为所属自然月结束日期 |
| `monthly_refund_amount` | `refund_amount` | 按周期求和 |

`id`由数据库自增生成；`created_at`和`updated_at`按数据插入时的北京时间生成。

## 6. 必须继承的业务口径

- 订单归属日期使用`订单创建时间`对应的北京时间日期，不使用退款打款日期。
- 复用第7张`weekly_refunds`已经确认的订单级`refund_amount`解析口径，不重新发明退款规则。
- 系统小额打款按去重后的实际打款事件求和；特殊订单`2510900014140061`按10 + 23 = 33.00计算。
- `售后状态 = 退款成功`且备注只有一个可信明确金额时取该金额；没有明确金额或金额冲突时取`实付款`。
- 非退款成功状态只有在备注存在单一金额且有已完成证据时才计入。
- `退款关闭`本身不算退款；若存在已实际完成的小额打款，则只按实际打款金额计入。
- `refund_amount`仅是解析过程字段，不增加到`raw_data`表，也不破坏原始表结构。
- 退款表包含全部渠道，不筛选分销渠道。

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
→ 按period_start + period_end分组
→ 汇总refund_amount
→ 生成目标记录
```

## 9. 正式实际执行结果

| 检查项目 | 结果 |
|---|---:|
| 正式记录数 | 18条 |
| 不同自然月 | 18个 |
| 最早周期开始日期 | 2025-02-01 |
| 最晚周期结束日期 | 2026-07-31 |
| 金额合计 | 3,902,960.69 |
| 与对应上游金额合计差异 | 0.00 |
| 周期边界、空白维度或非正数记录 | 0条 |

## 10. 正式数据库完整字段样例

| `id` | `period_start` | `period_end` | `monthly_refund_amount` | `created_at` | `updated_at` |
|---:|---|---|---:|---|---|
| 1 | 2025-02-01 | 2025-02-28 | 79,035.10 | 2026-08-10 11:33:08.180113+08 | 2026-08-10 11:33:08.180113+08 |
| 6 | 2025-07-01 | 2025-07-31 | 216,944.96 | 2026-08-10 11:33:08.180113+08 | 2026-08-10 11:33:08.180113+08 |
| 11 | 2025-12-01 | 2025-12-31 | 62,201.66 | 2026-08-10 11:33:08.180113+08 | 2026-08-10 11:33:08.180113+08 |
| 12 | 2026-01-01 | 2026-01-31 | 33,605.34 | 2026-08-10 11:33:08.180113+08 | 2026-08-10 11:33:08.180113+08 |
| 16 | 2026-05-01 | 2026-05-31 | 124,089.59 | 2026-08-10 11:33:08.180113+08 | 2026-08-10 11:33:08.180113+08 |
| 18 | 2026-07-01 | 2026-07-31 | 39,996.54 | 2026-08-10 11:33:08.180113+08 | 2026-08-10 11:33:08.180113+08 |

以上记录均已逐条查询正式表确认。

## 11. 金额与其他表的关系

- 本表金额合计为3,902,960.69。
- 本表为退款金额，不改变销售额表；净销售额由看板查询时使用销售额减退款额。
- 本表必须从自身上游按当前周期重新汇总，不能直接累计可能跨周期边界的周记录。

## 12. 正式采用的建表SQL

```sql
CREATE TABLE kuaishouxiaodian.monthly_refunds (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    monthly_refund_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT monthly_refunds_period_check CHECK (
        period_start = DATE_TRUNC('month', period_start)::DATE
        AND period_end = (
            DATE_TRUNC('month', period_start)
            + INTERVAL '1 month - 1 day'
        )::DATE
    ),
    CONSTRAINT monthly_refunds_amount_check CHECK (
        monthly_refund_amount > 0
    ),
    CONSTRAINT monthly_refunds_business_uk UNIQUE (
        period_start, period_end
    )
);
```

## 13. 首次数据生成SQL

```sql
INSERT INTO kuaishouxiaodian.monthly_refunds (
    period_start,
    period_end,
    monthly_refund_amount
)
SELECT
    DATE_TRUNC('month', transaction_date)::DATE AS period_start,
    (DATE_TRUNC('month', transaction_date) + INTERVAL '1 month - 1 day')::DATE AS period_end,
    SUM(refund_amount)::NUMERIC(18,2) AS monthly_refund_amount
FROM temp_refund_resolution
WHERE refund_amount > 0
GROUP BY period_start, period_end
ORDER BY period_start, period_end;
```

退款表SQL中的`temp_refund_resolution`会在同一事务内根据第7张表已确认的规则从`raw_data`临时生成，不是持久化业务表。

## 14. 实际原子建表与上传流程

1. 开启PostgreSQL事务，并将事务时区设置为`Asia/Shanghai`。
2. 创建`kuaishouxiaodian.monthly_refunds`。
3. 读取并校验上游字段、记录粒度和业务口径。
4. 计算每条上游记录所属的自然月。
5. 按业务唯一键分组并聚合。
6. 写入目标记录。
7. 校验字段数、记录数、周期边界、业务键、金额和上游重算结果。
8. 全部通过后提交；任一环节失败则回滚建表和全部数据写入。

## 15. 后续上游数据变动时的刷新逻辑

```text
上游数据新增或更新
→ 定位受影响的自然月
→ 删除目标表中的对应旧记录
→ 使用该周期内的全部上游记录重新汇总
→ 写入新记录并更新updated_at
→ 校验通过后与上游变动一起提交
→ 任一步失败则全部回滚
```

## 16. 正式上传验证规则

- 表字段数必须为6个。
- 当前数据下记录数必须为18条。
- 不同自然月必须为18个。
- 最早周期开始日期必须为2025-02-01。
- 最晚周期结束日期必须为2026-07-31。
- 必填字段空值和重复业务键必须均为0。
- 所有周期必须符合已确认的每月1日至当月最后一日；2月结束日期自动按平年或闰年确定。
- `monthly_refund_amount`必须全部大于0，金额合计必须为3,902,960.69。
- 与上游重新全量汇总相比，金额差异必须为0。
- 本文真实样例必须与正式表逐条一致。

## 17. 用户审核确认项

- [x] 确认本表严格保留6个字段。
- [x] 确认数据粒度为“一个自然月”。
- [x] 确认周期规则为：每月1日至当月最后一日；2月结束日期自动按平年或闰年确定。
- [x] 确认本表包含全部渠道。
- [x] 确认金额字段为`monthly_refund_amount`，口径与上游一致。
- [x] 确认不生成无数据周期或组合的补零记录。
- [x] 确认目标表与上游变更采用同一事务，任一步失败全部回滚。
- [x] 确认退款金额完整沿用第7张表的订单级解析规则，退款关闭不因状态本身计入。
- [x] 确认上述真实样例和总体结果可以作为正式上传后的校验基准。

## 18. 用户修改区

请直接在下方填写需要修改的内容：

```text
（待填写）
```

## 19. 实际执行与校验结果

- 正式表于2026-08-10完成创建、数据写入和校验，表所有者为`root`。
- 正式写入18条记录，覆盖18个自然月，周期边界为2025-02-01至2026-07-31。
- `monthly_refund_amount`合计为3,902,960.69。
- 必填字段空值、异常自然月边界、非正退款金额和重复业务键均为0条。
- 按第7张表确认的订单级退款解析规则从`raw_data`全量重算后，逐月业务键差异和金额差异均为0。
- `created_at`和`updated_at`统一为北京时间`2026-08-10 11:33:08.180113+08`。
- 本表与同批表在同一个总事务中完成创建、写入和校验；全部断言通过后一次性提交，未发生部分成功。
