# 快手小店第25张表审核草稿：`kuaishouxiaodian.customer_daily_sales`

> 状态：已确认，已建表，已上传数据，已校验  
> 数据库：`weidian`  
> Schema：`kuaishouxiaodian`  
> 表序号：25 / 35  
> 直接上游：`kuaishouxiaodian.daily_customer_sales`（第5张正式表）  
> 客户对照表：`kuaishouxiaodian.customer_id_mapping`（第2张正式表）  
> 设计基准：`hh.customer_daily_sales`正式结构、《数据库英文命名映射修正版》和《AI看板-表结构最终版》  
> 样例说明：以下业务字段、`id`、`created_at`和`updated_at`均来自正式数据库查询。

## 1. 表的作用

`customer_daily_sales`用于以客户为第一检索维度，保存每个客户在每个自然日的交易金额。一条记录代表“一个客户ID + 一个交易日期”的销售汇总。

本表与第5张`daily_customer_sales`的字段内容和业务数据一致，但组织顺序不同：

- 第5张：先交易日期，再客户ID。
- 第25张：先客户ID，再交易日期。

本表供客户销售明细、单客户时间趋势及第26张客户日销售指标表使用。

## 2. 数据粒度、分组顺序与唯一性

- 数据粒度：一个客户在一个自然日的销售汇总。
- 分组顺序：先客户ID，再交易日期。
- 主键：`id`。
- 业务唯一键：`customer_id + transaction_date`。
- 同一客户、同一交易日期只能存在一条记录。
- 没有有效销售的客户或日期不生成金额为0的补零记录。

PostgreSQL表本身不保证无`ORDER BY`查询的返回顺序。因此，本设计通过以下三点落实“先客户、再日期”：

1. 联合唯一约束的字段顺序为`customer_id, transaction_date`。
2. 首次插入按`customer_id, transaction_date`升序执行。
3. 客户时间明细查询显式使用`ORDER BY customer_id, transaction_date`。

## 3. 字段设计

本表严格保留以下6个字段：

| 序号 | 字段 | PostgreSQL类型 | 是否必填 | 默认值 | 说明 |
|---:|---|---|---|---|---|
| 1 | `id` | `BIGINT` | 是 | 自增 | 主键，由数据库自动生成 |
| 2 | `transaction_date` | `DATE` | 是 | 无 | 客户发生有效销售的北京时间日期 |
| 3 | `customer_id` | `TEXT` | 是 | 无 | 按CPS达人ID、团长ID、快赚客ID优先级解析后的客户ID |
| 4 | `transaction_amount` | `NUMERIC(18,2)` | 是 | `0` | 同一客户在该日的毛销售额 |
| 5 | `created_at` | `TIMESTAMPTZ` | 是 | `CURRENT_TIMESTAMP` | 首次插入数据库的北京时间 |
| 6 | `updated_at` | `TIMESTAMPTZ` | 是 | `CURRENT_TIMESTAMP` | 最近刷新记录的北京时间 |

本表不增加客户昵称、客户来源、订单数、商品数、退款额或滚动金额字段。

## 4. 数据来源与字段映射

| 目标字段 | 上游字段或来源 | 处理方式 |
|---|---|---|
| `id` | 数据库Identity | 正式插入时自增生成 |
| `transaction_date` | `daily_customer_sales.transaction_date` | 原值继承 |
| `customer_id` | `daily_customer_sales.customer_id` | 原值继承 |
| `transaction_amount` | `daily_customer_sales.transaction_amount` | 原值继承，不再次聚合 |
| `created_at` | 数据库当前时间 | 正式插入时按北京时间生成 |
| `updated_at` | 数据库当前时间 | 正式插入时按北京时间生成 |

## 5. 必须继承的业务口径

第25张表完全继承第5张表已经确认并上传的业务口径：

- 仅包含`渠道 = '分销'`的客户销售数据。
- 有效订单状态为`交易成功`、`已发货`、`已收货`。
- 客户ID优先级为CPS达人ID、团长ID、快赚客ID。
- 三类客户ID均为空的记录不进入客户表。
- 交易金额使用`实付款`，保存毛销售额，不直接扣减退款。
- 本表不依赖SKU编码，空SKU规则不影响本表。
- 不按订单号额外去重。

由于第5张表已完成原始记录筛选和按日按客户汇总，本表不再读取`raw_data`，避免重复实现业务规则后产生口径漂移。

## 6. 与第5张表的一致性规则

以下内容必须与`daily_customer_sales`逐业务键完全一致：

- 记录数。
- 客户ID集合。
- 交易日期集合。
- 每个`customer_id + transaction_date`对应的`transaction_amount`。
- 全表交易金额合计。

允许不同的字段只有：

- `id`：两张表分别自增生成。
- `created_at`、`updated_at`：按各自正式插入时间生成。

若第5张表与第25张表业务字段出现任何差异，验证必须失败并回滚。

## 7. 生成流程

```text
读取daily_customer_sales全部正式记录
→ 校验第5张表业务键唯一、字段完整、客户映射完整
→ 原值选择transaction_date、customer_id、transaction_amount
→ 按customer_id升序、transaction_date升序排列
→ 一次性写入customer_daily_sales
→ 数据库生成id、created_at和updated_at
→ 与第5张表逐业务键全量比对
```

## 8. 正式执行结果

| 检查项目 | 结果 |
|---|---:|
| 正式记录数 | 8,941条 |
| 不同业务键 | 8,941组 |
| 不同客户ID | 946个 |
| 不同交易日期 | 541日 |
| 最早交易日期 | 2025-02-01 |
| 最晚交易日期 | 2026-07-28 |
| `transaction_amount`合计 | 5,709,898.66 |
| 必填字段空值或空客户ID | 0条 |
| 非正交易金额 | 0条 |
| 重复业务键 | 0组 |
| 客户对照表缺失 | 0条 |
| 与第5张表预期业务差异 | 0条 |

## 9. 基于真实上游数据的完整字段样例

| `id` | `transaction_date` | `customer_id` | `transaction_amount` | `created_at` | `updated_at` |
|---:|---|---|---:|---|---|
| 1 | 2025-04-03 | `1007729857` | 49.90 | 2026-08-10 13:20:23.299439+08 | 2026-08-10 13:20:23.299439+08 |
| 2 | 2025-03-30 | `1014787244` | 59.90 | 2026-08-10 13:20:23.299439+08 | 2026-08-10 13:20:23.299439+08 |
| 3 | 2025-04-16 | `1014787244` | 49.90 | 2026-08-10 13:20:23.299439+08 | 2026-08-10 13:20:23.299439+08 |
| 100 | 2025-05-23 | `105193469` | 299.50 | 2026-08-10 13:20:23.299439+08 | 2026-08-10 13:20:23.299439+08 |
| 1,000 | 2025-04-11 | `1351293684` | 79.80 | 2026-08-10 13:20:23.299439+08 | 2026-08-10 13:20:23.299439+08 |
| 5,000 | 2025-04-08 | `3990861400` | 39.90 | 2026-08-10 13:20:23.299439+08 | 2026-08-10 13:20:23.299439+08 |
| 8,941 | 2025-07-08 | `99800117` | 165.90 | 2026-08-10 13:20:23.299439+08 | 2026-08-10 13:20:23.299439+08 |

以上样例完整列出6个目标字段，全部来自正式表，未省略任何字段。

## 10. 已执行建表SQL

```sql
CREATE TABLE kuaishouxiaodian.customer_daily_sales (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    transaction_date DATE NOT NULL,
    customer_id TEXT NOT NULL,
    transaction_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT customer_daily_sales_customer_date_uk UNIQUE (
        customer_id,
        transaction_date
    )
);

ALTER TABLE kuaishouxiaodian.customer_daily_sales OWNER TO root;
```

## 11. 首次数据生成SQL

```sql
INSERT INTO kuaishouxiaodian.customer_daily_sales (
    transaction_date,
    customer_id,
    transaction_amount
)
SELECT
    transaction_date,
    customer_id,
    transaction_amount
FROM kuaishouxiaodian.daily_customer_sales
ORDER BY customer_id, transaction_date;
```

此处不使用`SUM`再次聚合，因为第5张表已经保证每个“交易日期 + 客户ID”只有一条汇总记录。第25张表只改变组织顺序，不改变数据值。

## 12. 已执行的原子建表与上传流程

1. 开启PostgreSQL事务，并执行`SET LOCAL TIME ZONE 'Asia/Shanghai'`。
2. 确认目标表不存在。
3. 校验第5张表的字段、记录数、业务键、客户映射、日期范围和金额。
4. 创建`customer_daily_sales`并将所有者设为`root`。
5. 按客户ID、交易日期顺序一次性复制8,941条业务记录。
6. 校验目标表字段数、主键、联合唯一键、必填字段和金额。
7. 与第5张表按业务键执行全量双向比对，差异必须为0。
8. 全部断言通过后提交；任一步失败则回滚建表和全部数据写入。

## 13. 后续上游变化时的刷新逻辑

第25张表必须与第5张表在同一业务事务中保持一致：

```text
daily_customer_sales完成新增、修改或删除
→ 获取受影响的customer_id + transaction_date业务键
→ 同步替换customer_daily_sales中的对应记录
→ 校验受影响业务键逐条一致
→ 校验两表全量记录数、总金额和双向差异
→ 全部通过后一次性提交；失败则一起回滚
```

这样能够保证基础客户日数据发生变化时，第25张表及其后续指标表同步变化。

## 14. 正式上传验证结果

- 表字段数必须为6个，名称、顺序和类型必须与第3节一致。
- `id`必须为Identity主键，表所有者必须为`root`。
- 当前数据下必须生成8,941条记录和8,941组不同业务键。
- 不同客户ID必须为946个，不同交易日期必须为541日。
- 日期范围必须为2025-02-01至2026-07-28。
- 交易金额合计必须为5,709,898.66。
- 必填字段空值、空客户ID、非正金额、重复业务键必须均为0。
- 所有客户ID必须存在于`customer_id_mapping`，孤立客户必须为0。
- 与第5张表按业务键全量双向比对的差异必须为0。
- 第9节全部业务字段必须与正式记录一致；正式上传后再更新实际`id`和时间字段。

## 15. 逐业务键全量一致性校验SQL

```sql
SELECT COUNT(*) AS mismatched_rows
FROM kuaishouxiaodian.daily_customer_sales AS source
FULL OUTER JOIN kuaishouxiaodian.customer_daily_sales AS target
  ON target.customer_id = source.customer_id
 AND target.transaction_date = source.transaction_date
WHERE source.transaction_amount IS DISTINCT FROM target.transaction_amount;
```

正式上传后`mismatched_rows`实际为0。`FULL OUTER JOIN`同时检查源表缺记录、目标表多记录和同业务键金额不同三类问题。

## 16. 客户映射完整性校验SQL

```sql
SELECT COUNT(*) AS orphan_customer_rows
FROM kuaishouxiaodian.customer_daily_sales AS target
LEFT JOIN kuaishouxiaodian.customer_id_mapping AS mapping
  ON mapping.customer_id = target.customer_id
WHERE mapping.customer_id IS NULL;
```

正式上传后`orphan_customer_rows`实际为0。

## 17. 与后续第26张表的关系

第26张`customer_daily_sales_metrics`将以本表为直接上游，按同一客户分别计算：

- 当前交易日期的`transaction_amount`。
- 包含当天及前6个自然日的`rolling_7_day_transaction_amount`。
- 包含当天及前29个自然日的`rolling_30_day_transaction_amount`。

第25张表只保存基础日金额，不提前保存滚动金额。

## 18. 用户审核确认项

- [x] 确认本表严格保留6个字段。
- [x] 确认本表与第5张表业务数据完全一致，不重新读取原始Excel。
- [x] 确认本表先按客户ID、再按交易日期组织。
- [x] 确认联合唯一键顺序为`customer_id + transaction_date`。
- [x] 确认`transaction_amount`直接继承第5张表，不再次聚合。
- [x] 确认本表仅含分销渠道客户数据，保存毛销售额，不扣减退款。
- [x] 确认所有客户ID必须存在于`customer_id_mapping`。
- [x] 确认与第5张表逐业务键双向比对差异必须为0。
- [x] 确认后续第5张表变化时，第25张表在同一事务内同步变化。
- [x] 确认第8节正式结果和第9节完整字段样例已通过正式上传校验。

## 19. 用户修改区

请直接在下方填写需要修改的内容：

```text
无。
```

## 20. 实际执行与校验记录

- 正式执行时间：2026-08-10 13:20:23.299439+08（北京时间）。
- 执行方式：在一个PostgreSQL事务内完成上游基线校验、建表、所有者设置、8,941条数据写入和强制断言；全部通过后一次性提交。
- 正式表：`kuaishouxiaodian.customer_daily_sales`，所有者为`root`。
- 正式结果：8,941条记录、8,941组业务键、946个客户、541个交易日，日期范围2025-02-01至2026-07-28，交易金额合计5,709,898.66。
- 数据质量：必填字段空值或空客户ID 0条、非正金额0条、重复业务键0组、孤立客户0条。
- 上下游一致性：与第5张`daily_customer_sales`逐业务键全量双向比对差异0条。
- 顺序校验：按`customer_id + transaction_date`计算的预期序号与正式`id`差异0条。
- 表结构校验：6个字段，`id`为Identity主键，金额精度为`NUMERIC(18,2)`，联合唯一约束生效。
- 提交后再次在独立连接中运行验证SQL，全部断言通过。
