# 快手小店第26张表审核草稿：`kuaishouxiaodian.customer_daily_sales_metrics`

> 状态：已确认，已建表，已上传数据，已校验  
> 数据库：`weidian`  
> Schema：`kuaishouxiaodian`  
> 表序号：26 / 35  
> 直接上游：`kuaishouxiaodian.customer_daily_sales`（第25张正式表）  
> 客户对照表：`kuaishouxiaodian.customer_id_mapping`（第2张正式表）  
> 设计基准：`hh.customer_daily_sales_metrics`正式结构、《数据库英文命名映射修正版》和《AI看板-表结构最终版》  
> 样例说明：以下业务指标、`id`、`created_at`和`updated_at`均来自正式数据库查询。

## 1. 表的作用

`customer_daily_sales_metrics`用于保存每个客户在每个有销售记录的自然日的当日交易金额、近7日交易金额和近30日交易金额。一条记录代表“一个客户ID + 一个交易日期”的客户日销售指标。

本表是第25张`customer_daily_sales`的二次开发表，不重新读取原始Excel，也不重新判断订单状态、渠道或客户ID。

## 2. 数据粒度与唯一性

- 数据粒度：一个客户在一个有销售记录的自然日的指标。
- 主键：`id`。
- 业务唯一键：`customer_id + transaction_date`。
- 每条第25张表记录在本表中必须且只能对应一条记录。
- 第25张表没有某个客户某日记录时，本表不生成金额为0的补零行。
- 插入顺序：先客户ID，再交易日期。

## 3. 字段设计

本表严格保留以下8个字段：

| 序号 | 字段 | PostgreSQL类型 | 是否必填 | 默认值 | 说明 |
|---:|---|---|---|---|---|
| 1 | `id` | `BIGINT` | 是 | 自增 | 主键，由数据库自动生成 |
| 2 | `transaction_date` | `DATE` | 是 | 无 | 指标对应的北京时间交易日期 |
| 3 | `customer_id` | `TEXT` | 是 | 无 | 客户ID |
| 4 | `transaction_amount` | `NUMERIC(18,2)` | 是 | `0` | 该客户在当天的毛销售额 |
| 5 | `rolling_7_day_transaction_amount` | `NUMERIC(18,2)` | 是 | `0` | 同一客户当天及前6个自然日的交易金额合计 |
| 6 | `rolling_30_day_transaction_amount` | `NUMERIC(18,2)` | 是 | `0` | 同一客户当天及前29个自然日的交易金额合计 |
| 7 | `created_at` | `TIMESTAMPTZ` | 是 | `CURRENT_TIMESTAMP` | 首次插入数据库的北京时间 |
| 8 | `updated_at` | `TIMESTAMPTZ` | 是 | `CURRENT_TIMESTAMP` | 最近刷新记录的北京时间 |

本表不保存客户昵称、同比、环比、退款额、订单数或商品数。三个金额字段均保留2位小数。

## 4. 数据来源与字段映射

| 目标字段 | 上游字段或来源 | 处理方式 |
|---|---|---|
| `id` | 数据库Identity | 正式插入时自增生成 |
| `transaction_date` | `customer_daily_sales.transaction_date` | 原值继承 |
| `customer_id` | `customer_daily_sales.customer_id` | 原值继承 |
| `transaction_amount` | `customer_daily_sales.transaction_amount` | 原值继承 |
| `rolling_7_day_transaction_amount` | 同一客户当前日及前6日记录 | 按第6节自然日窗口求和 |
| `rolling_30_day_transaction_amount` | 同一客户当前日及前29日记录 | 按第6节自然日窗口求和 |
| `created_at` | 数据库当前时间 | 正式插入时按北京时间生成 |
| `updated_at` | 数据库当前时间 | 正式插入时按北京时间生成 |

## 5. 必须继承的业务口径

本表完全继承第25张表已经确认的业务口径：

- 仅包含分销渠道客户数据。
- 客户ID按CPS达人ID、团长ID、快赚客ID的优先级形成。
- 交易金额使用有效订单的`实付款`，保存毛销售额，不直接扣减退款。
- 不受SKU是否为空影响。
- 不按订单号额外去重。
- 所有客户ID必须存在于`customer_id_mapping`。

## 6. 近7日和近30日计算规则

### 6.1 近7日交易金额

对当前记录的同一个`customer_id`，累加日期范围：

```text
transaction_date - 6天
至
transaction_date当天
```

共覆盖7个自然日，包含当前交易日期。

### 6.2 近30日交易金额

对当前记录的同一个`customer_id`，累加日期范围：

```text
transaction_date - 29天
至
transaction_date当天
```

共覆盖30个自然日，包含当前交易日期。

### 6.3 日期缺口处理

- 滚动窗口按自然日范围判断，不按“前6条记录”或“前29条记录”计算。
- 某客户在窗口内没有销售的日期不生成补零记录，但视为该日贡献金额0。
- 不同客户之间绝不相互累加。
- 对当前数据中的每条记录，应满足：`rolling_30_day_transaction_amount >= rolling_7_day_transaction_amount >= transaction_amount`。

## 7. 生成流程

```text
读取customer_daily_sales全部正式记录
→ 按customer_id分区
→ 每个客户内部按transaction_date升序
→ 计算当天及前6个自然日金额
→ 计算当天及前29个自然日金额
→ 按customer_id、transaction_date升序写入目标表
→ 数据库生成id、created_at和updated_at
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
| `transaction_amount`逐行合计 | 5,709,898.66 |
| `rolling_7_day_transaction_amount`逐行合计 | 36,884,630.38 |
| `rolling_30_day_transaction_amount`逐行合计 | 145,158,842.79 |
| 近7日金额最小值 / 最大值 | 9.90 / 528,635.40 |
| 近30日金额最小值 / 最大值 | 9.90 / 827,210.00 |
| 近7日金额等于当日金额 | 2,002条 |
| 近7日金额大于当日金额 | 6,939条 |
| 近30日金额等于近7日金额 | 1,890条 |
| 近30日金额大于近7日金额 | 7,051条 |
| 滚动金额大小关系异常 | 0条 |
| 必填字段空值或空客户ID | 0条 |
| 重复业务键 | 0组 |
| 客户对照表缺失 | 0条 |

滚动金额的“逐行合计”仅用于验证每行计算是否稳定，不代表可直接对外展示的独立销售总额，因为相邻日期的滚动窗口会重复覆盖相同销售记录。

## 9. 基于真实上游数据的完整字段样例

| `id` | `transaction_date` | `customer_id` | `transaction_amount` | `rolling_7_day_transaction_amount` | `rolling_30_day_transaction_amount` | `created_at` | `updated_at` |
|---:|---|---|---:|---:|---:|---|---|
| 1 | 2025-04-03 | `1007729857` | 49.90 | 49.90 | 49.90 | 2026-08-10 13:28:07.443667+08 | 2026-08-10 13:28:07.443667+08 |
| 2 | 2025-03-30 | `1014787244` | 59.90 | 59.90 | 59.90 | 2026-08-10 13:28:07.443667+08 | 2026-08-10 13:28:07.443667+08 |
| 3 | 2025-04-16 | `1014787244` | 49.90 | 49.90 | 109.80 | 2026-08-10 13:28:07.443667+08 | 2026-08-10 13:28:07.443667+08 |
| 100 | 2025-05-23 | `105193469` | 299.50 | 8,642.60 | 25,156.60 | 2026-08-10 13:28:07.443667+08 | 2026-08-10 13:28:07.443667+08 |
| 1,000 | 2025-04-11 | `1351293684` | 79.80 | 1,616.30 | 34,187.69 | 2026-08-10 13:28:07.443667+08 | 2026-08-10 13:28:07.443667+08 |
| 7,902 | 2025-04-28 | `745575951` | 3,553.10 | 33,841.70 | 689,287.20 | 2026-08-10 13:28:07.443667+08 | 2026-08-10 13:28:07.443667+08 |
| 8,941 | 2025-07-08 | `99800117` | 165.90 | 165.90 | 165.90 | 2026-08-10 13:28:07.443667+08 | 2026-08-10 13:28:07.443667+08 |

以上样例完整列出8个目标字段，全部来自正式表，未省略任何字段。

## 10. 已执行建表SQL

```sql
CREATE TABLE kuaishouxiaodian.customer_daily_sales_metrics (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    transaction_date DATE NOT NULL,
    customer_id TEXT NOT NULL,
    transaction_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    rolling_7_day_transaction_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    rolling_30_day_transaction_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT customer_daily_sales_metrics_customer_date_uk UNIQUE (
        customer_id,
        transaction_date
    )
);

ALTER TABLE kuaishouxiaodian.customer_daily_sales_metrics OWNER TO root;
```

## 11. 首次数据生成SQL

```sql
INSERT INTO kuaishouxiaodian.customer_daily_sales_metrics (
    transaction_date,
    customer_id,
    transaction_amount,
    rolling_7_day_transaction_amount,
    rolling_30_day_transaction_amount
)
SELECT
    transaction_date,
    customer_id,
    transaction_amount,
    SUM(transaction_amount) OVER (
        PARTITION BY customer_id
        ORDER BY transaction_date
        RANGE BETWEEN INTERVAL '6 days' PRECEDING AND CURRENT ROW
    )::NUMERIC(18,2),
    SUM(transaction_amount) OVER (
        PARTITION BY customer_id
        ORDER BY transaction_date
        RANGE BETWEEN INTERVAL '29 days' PRECEDING AND CURRENT ROW
    )::NUMERIC(18,2)
FROM kuaishouxiaodian.customer_daily_sales
ORDER BY customer_id, transaction_date;
```

`RANGE ... INTERVAL`按日期距离计算自然日窗口，不会把“前6条有销售记录”误当成“前6个自然日”。

## 12. 已执行的原子建表与上传流程

1. 开启PostgreSQL事务，并执行`SET LOCAL TIME ZONE 'Asia/Shanghai'`。
2. 确认目标表不存在。
3. 校验第25张表的字段、记录数、业务键、客户映射、日期范围和金额。
4. 创建目标表并将所有者设为`root`。
5. 按客户分区、按交易日期计算两个自然日滚动窗口。
6. 按客户ID、交易日期顺序一次性写入8,941条记录。
7. 校验字段数、金额精度、业务键、窗口关系和汇总结果。
8. 与第25张表逐业务键核对基础日金额，并逐键重算两个滚动金额。
9. 全部断言通过后提交；任一步失败则回滚建表和全部数据写入。

## 13. 后续上游变化时的刷新逻辑

某个客户某日的基础金额变化，会影响该客户当天至之后29天内已有销售记录的滚动指标。为避免漏刷依赖日期，与第25张表变化在同一事务内全量重算本表：

```text
customer_daily_sales完成新增、修改或删除
→ 在临时结果中按客户全量重算近7日和近30日金额
→ 校验业务键、金额关系和逐键差异
→ 替换customer_daily_sales_metrics全部旧记录
→ 与第25张表及临时结果再次全量比对
→ 全部通过后一次性提交；失败则一起回滚
```

## 14. 正式上传验证结果

- 表字段数必须为8个，名称、顺序和类型必须与第3节一致。
- 三个金额字段必须均为`NUMERIC(18,2)`。
- `id`必须为Identity主键，表所有者必须为`root`。
- 当前数据下必须生成8,941条记录和8,941组不同业务键。
- 不同客户必须为946个，不同交易日期必须为541日。
- 日期范围必须为2025-02-01至2026-07-28。
- 基础日金额逐行合计必须为5,709,898.66，并与第25张表一致。
- 近7日金额逐行合计必须为36,884,630.38，近30日金额逐行合计必须为145,158,842.79。
- 近7日金额范围必须为9.90至528,635.40，近30日金额范围必须为9.90至827,210.00。
- `近30日金额 >= 近7日金额 >= 当日金额`异常必须为0条。
- 必填字段空值、空客户ID、重复业务键、孤立客户必须均为0。
- 与第25张表基础字段差异及两个窗口逐业务键重算差异必须均为0。
- 第9节全部业务字段必须与正式记录一致；正式上传后再更新实际`id`和时间字段。

## 15. 逐业务键全量重算校验SQL

```sql
WITH expected AS (
    SELECT
        transaction_date,
        customer_id,
        transaction_amount,
        SUM(transaction_amount) OVER (
            PARTITION BY customer_id
            ORDER BY transaction_date
            RANGE BETWEEN INTERVAL '6 days' PRECEDING AND CURRENT ROW
        )::NUMERIC(18,2) AS rolling_7_day_transaction_amount,
        SUM(transaction_amount) OVER (
            PARTITION BY customer_id
            ORDER BY transaction_date
            RANGE BETWEEN INTERVAL '29 days' PRECEDING AND CURRENT ROW
        )::NUMERIC(18,2) AS rolling_30_day_transaction_amount
    FROM kuaishouxiaodian.customer_daily_sales
)
SELECT COUNT(*) AS mismatched_rows
FROM expected AS source
FULL OUTER JOIN kuaishouxiaodian.customer_daily_sales_metrics AS target
  ON target.customer_id = source.customer_id
 AND target.transaction_date = source.transaction_date
WHERE source.transaction_amount
          IS DISTINCT FROM target.transaction_amount
   OR source.rolling_7_day_transaction_amount
          IS DISTINCT FROM target.rolling_7_day_transaction_amount
   OR source.rolling_30_day_transaction_amount
          IS DISTINCT FROM target.rolling_30_day_transaction_amount;
```

正式上传后`mismatched_rows`实际为0。

## 16. 滚动窗口边界说明

以某客户2026-07-30的指标为例：

- 近7日窗口：2026-07-24至2026-07-30。
- 近30日窗口：2026-07-01至2026-07-30。
- 2026-07-23的金额不进入近7日，但仍可能进入近30日。
- 其他客户在相同日期的金额不进入该客户窗口。

## 17. 指标使用限制

- 每行滚动金额适合查看“该客户截至该日”的近期销售情况。
- 不能把多日的滚动金额直接相加作为销售总额，因为窗口之间存在重复覆盖。
- 需要统计真实期间销售额时，应使用第25张表的`transaction_amount`按日期范围求和。
- 本表只生成第25张表已有业务日期的指标，不承担连续日历补零功能。

## 18. 用户审核确认项

- [x] 确认本表严格保留8个字段，不增加同比、环比或退款字段。
- [x] 确认本表以第25张`customer_daily_sales`为唯一直接上游。
- [x] 确认近7日包含当前日及前6个自然日。
- [x] 确认近30日包含当前日及前29个自然日。
- [x] 确认滚动窗口按自然日范围计算，不按前若干条记录计算。
- [x] 确认不同客户之间不相互累加，缺少销售的日期不补行。
- [x] 确认三个金额字段均保留2位小数。
- [x] 确认本表继承分销渠道和毛销售额口径，不扣减退款。
- [x] 确认上游变化时在同一事务内全量重算，任一步失败全部回滚。
- [x] 确认第8节正式结果和第9节完整字段样例已通过正式上传校验。

## 19. 用户修改区

请直接在下方填写需要修改的内容：

```text
无。
```

## 20. 实际执行与校验记录

- 正式执行时间：2026-08-10 13:28:07.443667+08（北京时间）。
- 执行方式：在一个PostgreSQL事务内完成上游校验、建表、所有者设置、8,941条指标写入和强制断言；全部通过后一次性提交。
- 正式表：`kuaishouxiaodian.customer_daily_sales_metrics`，所有者为`root`。
- 正式结果：8,941条记录、8,941组业务键、946个客户、541个交易日，日期范围2025-02-01至2026-07-28。
- 金额结果：基础日金额5,709,898.66，近7日逐行合计36,884,630.38，近30日逐行合计145,158,842.79。
- 数据质量：必填字段空值或空客户ID 0条、滚动金额关系异常0条、重复业务键0组、孤立客户0条。
- 逐业务键重算：基础日金额、近7日金额、近30日金额差异均为0条。
- 表结构校验：8个字段，`id`为Identity主键，三个金额字段均为`NUMERIC(18,2)`，联合唯一约束生效。
- 提交后再次在独立连接中运行验证SQL，全部断言通过。
