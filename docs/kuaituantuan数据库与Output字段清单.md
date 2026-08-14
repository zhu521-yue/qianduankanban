# 快团团数据库与 Output 字段清单

生成时间：2026-08-08 16:10:39

## 范围说明

- 数据库：`ai_dashboard`
- 数据库表：所有 schema 下表名为 `kuaituantuan` 的表。
- 文件目录：`Output` 文件夹下的 `.xlsx` 文件。
- 本文只记录字段结构，不记录数据库连接凭据，也不导出业务明细数据。

## 一、数据库字段信息

查询范围：`ai_dashboard` 中所有表名为 `kuaituantuan` 的非系统表。

### customer_list.kuaituantuan（客户名单表）

共 4 个字段。

| 序号 | 字段名 | 类型 | 可空 | 默认值 | 注释 |
|---:|---|---|---|---|---|
| 1 | id | bigint | NO |  | 主键递增 |
| 2 | customID | character varying(255) | NO |  | 客户ID |
| 3 | created_time | timestamp without time zone | NO | CURRENT_TIMESTAMP |  |
| 4 | updated_time | timestamp without time zone | NO | CURRENT_TIMESTAMP |  |

### custom_health.kuaituantuan（客户健康度初始表）

共 15 个字段。

| 序号 | 字段名 | 类型 | 可空 | 默认值 | 注释 |
|---:|---|---|---|---|---|
| 1 | id | bigint | NO |  | 主键递增 |
| 2 | dealTime | date | NO |  | 交易日期 |
| 3 | customID | character varying(255) | NO |  | 客户ID |
| 4 | count_today | bigint | YES |  | 今日拿货次数 |
| 5 | count_near_7_days | bigint | YES |  | 近7日拿货次数 |
| 6 | count_near_30_days | bigint | YES |  | 近30日拿货次数 |
| 7 | count_per_week | bigint | YES |  | 周拿货次数 |
| 8 | count_per_month | bigint | YES |  | 月拿货次数 |
| 9 | amount_today | numeric(18,2) | YES |  | 当日拿货金额 |
| 10 | count_near_7_days_amount | numeric(18,2) | YES |  | 近7日拿货金额 |
| 11 | count_near_30_days_amount | numeric(18,2) | YES |  | 近30日拿货金额 |
| 12 | amount_per_week | numeric(18,2) | YES |  | 周拿货金额 |
| 13 | amount_per_month | numeric(18,2) | YES |  | 月拿货金额 |
| 14 | created_time | timestamp without time zone | NO | CURRENT_TIMESTAMP |  |
| 15 | updated_time | timestamp without time zone | NO | CURRENT_TIMESTAMP |  |

### custom_amount_platform.kuaituantuan（客户销售表）

共 8 个字段。

| 序号 | 字段名 | 类型 | 可空 | 默认值 | 注释 |
|---:|---|---|---|---|---|
| 1 | id | bigint | NO |  | 主键递增 |
| 2 | customID | character varying(255) | NO |  | 客户ID |
| 3 | dealTime | date | NO |  | 交易日期 |
| 4 | goodID | character varying(255) | NO |  | 商品编码 |
| 5 | goodQuantity | bigint | YES |  | 商品数量 |
| 6 | goodCustomAmount | numeric(18,2) | YES |  | 销售金额 |
| 7 | created_time | timestamp without time zone | NO | CURRENT_TIMESTAMP |  |
| 8 | updated_time | timestamp without time zone | NO | CURRENT_TIMESTAMP |  |

### custom_platform.kuaituantuan（平台销售表）

共 5 个字段。

| 序号 | 字段名 | 类型 | 可空 | 默认值 | 注释 |
|---:|---|---|---|---|---|
| 1 | id | bigint | NO |  | 递增 |
| 2 | dealTime | date | NO |  | 交易日期 |
| 3 | customAmount | numeric(18,2) | YES |  | 交易金额 |
| 4 | created_time | timestamp without time zone | NO | CURRENT_TIMESTAMP |  |
| 5 | updated_time | timestamp without time zone | NO | CURRENT_TIMESTAMP |  |

### platform_custom_dimision.kuaituantuan（平台销售指标表）

共 13 个字段。

| 序号 | 字段名 | 类型 | 可空 | 默认值 | 注释 |
|---:|---|---|---|---|---|
| 1 | id | bigint | NO |  | 主键递增 |
| 2 | dealTime | date | NO |  | 交易日期 |
| 3 | customAmount | numeric(18,2) | NO |  | 交易金额 |
| 4 | near_7_days | numeric(18,2) | YES |  | 近7日销售额 |
| 5 | near_30_days | numeric(18,2) | YES |  | 近30日销售额 |
| 6 | tongbi | numeric(8,2) | YES |  | 同比 |
| 7 | rihuanbi | numeric(8,2) | YES |  | 日环比 |
| 8 | zhouhuanbi | numeric(8,2) | YES |  | 周环比 |
| 9 | yuehuanbi | numeric(8,2) | YES |  | 月环比 |
| 10 | created_time | timestamp without time zone | NO | CURRENT_TIMESTAMP |  |
| 11 | updated_time | timestamp without time zone | NO | CURRENT_TIMESTAMP |  |
| 12 | amount_per_week | numeric | YES |  |  |
| 13 | amount_per_month | numeric | YES |  |  |

## 二、Output 文件夹字段信息

读取范围：`Output/*.xlsx`；每个工作表取前 20 行中的第一行非空行作为字段行。

### kuaituantuan_customer_health_initial.xlsx（客户健康度初始表）

- 工作表：`客户健康度指标初始表`；字段行：1；数据行数上限：未统计；列数上限：未统计

共 12 个字段。

| 序号 | 字段名 |
|---:|---|
| 1 | 客户ID |
| 2 | 交易日期 |
| 3 | 当日拿货次数 |
| 4 | 近7日拿货次数 |
| 5 | 近30日拿货次数 |
| 6 | 周拿货次数 |
| 7 | 月拿货次数 |
| 8 | 当日拿货金额 |
| 9 | 近7日拿货金额 |
| 10 | 近30日拿货金额 |
| 11 | 周拿货金额 |
| 12 | 月拿货金额 |

### kuaituantuan_customer_list.xlsx（客户名单表）

- 工作表：`客户名单`；字段行：1；数据行数上限：174；列数上限：1

共 1 个字段。

| 序号 | 字段名 |
|---:|---|
| 1 | 团长 |

### kuaituantuan_customer_xiaoshou.xlsx（客户销售表）

- 工作表：`kuaituantuan_customer_xiaoshou`；字段行：1；数据行数上限：未统计；列数上限：未统计

共 7 个字段。

| 序号 | 字段名 |
|---:|---|
| 1 | 团长 |
| 2 | 支付日期 |
| 3 | 商品编码 |
| 4 | 商品编码数量总和 |
| 5 | 商品编码商品金额总和 |
| 6 | 支付日期总数量 |
| 7 | 支付日期总商品金额 |

### kuaituantuan_xiaoshou.xlsx（平台销售表）

- 工作表：`kuaituantuan_xiaoshou`；字段行：1；数据行数上限：452；列数上限：2

共 2 个字段。

| 序号 | 字段名 |
|---:|---|
| 1 | 支付日期 |
| 2 | 当日订单实际收款金额总额 |

### kuaituantuan_xiaoshou_metrics.xlsx（平台销售指标表）

- 工作表：`新增指标`；字段行：1；数据行数上限：452；列数上限：10

共 10 个字段。

| 序号 | 字段名 |
|---:|---|
| 1 | 支付日期 |
| 2 | 当日订单实际收款金额总额 |
| 3 | 近7日销售总额 |
| 4 | 近30日销售总额 |
| 5 | 同比 |
| 6 | 日环比 |
| 7 | 周环比 |
| 8 | 月环比 |
| 9 | 周销售额 |
| 10 | 月销售额 |
