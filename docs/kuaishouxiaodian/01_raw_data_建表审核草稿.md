# 快手小店第1张表审核草稿：`kuaishouxiaodian.raw_data`

> 状态：用户已确认，已建表，已上传并校验通过  
> 数据库：`weidian`  
> Schema：`kuaishouxiaodian`  
> 表序号：01 / 35

## 1. 表的作用

`raw_data`用于完整保存快手小店Excel原文件中的全部字段，不只保存数据分析所需字段。

- Excel原始字段：64个，字段名保持中文，不做英文映射。
- 数据库系统字段：`id`、`created_at`、`updated_at`。
- 表字段总数：67个。
- 本表不做销售、退款、客户归属等业务筛选。
- 原始文件中的预售字段继续保留；“不建立预售表”只针对后续衍生表。
- 当前数据已经验证为一张订单只有一个SKU，因此使用订单号作为业务唯一键。

## 2. 数据粒度与唯一性

- 一条记录代表一张快手订单及其唯一SKU。
- 主键：`id`。
- 业务唯一键：`订单号`。
- 后续上传文件中出现相同订单号时，不重复插入，而是更新该订单最新状态、售后状态及其他原始字段。
- 更新已有订单时保留原`created_at`，自动更新`updated_at`。

## 3. 完整字段设计

| 序号 | 数据库字段 | PostgreSQL类型 | 是否必填 | 来源/说明 |
|---:|---|---|---|---|
| 1 | `id` | `BIGINT` | 是 | 自增主键 |
| 2 | `订单号` | `TEXT` | 是 | Excel原字段；业务唯一键 |
| 3 | `赠品订单号` | `TEXT` | 否 | Excel原字段 |
| 4 | `活动订单编号` | `TEXT` | 否 | Excel原字段 |
| 5 | `订单创建时间` | `TIMESTAMPTZ` | 是 | Excel原字段；按北京时间解析 |
| 6 | `订单支付时间` | `TIMESTAMPTZ` | 否 | Excel原字段；按北京时间解析 |
| 7 | `预售定金支付时间` | `TIMESTAMPTZ` | 否 | Excel原字段；按北京时间解析 |
| 8 | `订单状态` | `TEXT` | 否 | Excel原字段，完整保留实际状态 |
| 9 | `实付款` | `NUMERIC(18,2)` | 否 | 去除人民币符号和千位分隔符 |
| 10 | `快递费` | `NUMERIC(18,2)` | 否 | 金额字段 |
| 11 | `店铺优惠` | `NUMERIC(18,2)` | 否 | 金额字段 |
| 12 | `平台补贴` | `NUMERIC(18,2)` | 否 | 金额字段 |
| 13 | `主播补贴` | `NUMERIC(18,2)` | 否 | 金额字段 |
| 14 | `混资活动优惠` | `NUMERIC(18,2)` | 否 | 金额字段 |
| 15 | `支付优惠` | `NUMERIC(18,2)` | 否 | 金额字段 |
| 16 | `支付方式` | `TEXT` | 否 | Excel原字段 |
| 17 | `成交数量` | `INTEGER` | 否 | 商品成交数量 |
| 18 | `买家留言` | `TEXT` | 否 | Excel原字段 |
| 19 | `账号类型` | `TEXT` | 否 | Excel原字段 |
| 20 | `账号明细` | `TEXT` | 否 | Excel原字段 |
| 21 | `订单备注` | `TEXT` | 否 | 完整保留；后续用于辅助识别部分退款 |
| 22 | `旗帜颜色` | `TEXT` | 否 | Excel原字段 |
| 23 | `售后状态` | `TEXT` | 否 | 完整保留实际售后状态 |
| 24 | `活动订单` | `TEXT` | 否 | Excel原字段 |
| 25 | `预售/承诺发货时间` | `TIMESTAMPTZ` | 否 | Excel原字段；按北京时间解析 |
| 26 | `订单载体` | `TEXT` | 否 | Excel原字段 |
| 27 | `国补类型` | `TEXT` | 否 | Excel原字段 |
| 28 | `商品名称` | `TEXT` | 否 | Excel原字段 |
| 29 | `商品ID` | `TEXT` | 否 | 作为标识符保存，避免数值精度或前导零丢失 |
| 30 | `商品规格` | `TEXT` | 否 | Excel原字段 |
| 31 | `SKU编码` | `TEXT` | 否 | 作为标识符保存；后续映射为`product_code` |
| 32 | `商品单价` | `NUMERIC(18,2)` | 否 | 金额字段 |
| 33 | `渠道` | `TEXT` | 否 | 当前实际值包括分销、自营等 |
| 34 | `CPS达人ID` | `TEXT` | 否 | 客户ID第一优先来源 |
| 35 | `CPS达人昵称` | `TEXT` | 否 | 客户昵称第一优先来源 |
| 36 | `预估推广佣金` | `NUMERIC(18,2)` | 否 | 金额字段 |
| 37 | `预估推广者分佣比例` | `NUMERIC(9,6)` | 否 | 例如30%保存为0.3 |
| 38 | `团长ID` | `TEXT` | 否 | CPS达人ID为空时的客户ID来源 |
| 39 | `团长昵称` | `TEXT` | 否 | CPS达人ID为空时的客户昵称来源 |
| 40 | `快赚客ID` | `TEXT` | 否 | Excel原字段 |
| 41 | `快赚客昵称` | `TEXT` | 否 | Excel原字段 |
| 42 | `授权推广者ID` | `TEXT` | 否 | Excel原字段 |
| 43 | `授权推广者昵称` | `TEXT` | 否 | Excel原字段 |
| 44 | `收货人姓名` | `TEXT` | 否 | Excel原字段 |
| 45 | `收货人电话` | `TEXT` | 否 | 使用文本保存，避免格式丢失 |
| 46 | `收货地址-省` | `TEXT` | 否 | Excel原字段 |
| 47 | `收货地址-市` | `TEXT` | 否 | Excel原字段 |
| 48 | `收货地址-区` | `TEXT` | 否 | Excel原字段 |
| 49 | `收货地址-街道` | `TEXT` | 否 | Excel原字段 |
| 50 | `收货地址` | `TEXT` | 否 | Excel原字段 |
| 51 | `发货时间` | `TIMESTAMPTZ` | 否 | Excel原字段；按北京时间解析 |
| 52 | `快递公司` | `TEXT` | 否 | Excel原字段 |
| 53 | `快递单号` | `TEXT` | 否 | 使用文本保存 |
| 54 | `物流信息` | `TEXT` | 否 | Excel原字段 |
| 55 | `集运类型` | `TEXT` | 否 | Excel原字段 |
| 56 | `直邮类型` | `TEXT` | 否 | Excel原字段 |
| 57 | `仓库名称` | `TEXT` | 否 | Excel原字段 |
| 58 | `仓库地址` | `TEXT` | 否 | Excel原字段 |
| 59 | `发货类型` | `TEXT` | 否 | Excel原字段 |
| 60 | `实名姓名` | `TEXT` | 否 | Excel原字段 |
| 61 | `服务门店ID` | `TEXT` | 否 | 使用文本保存 |
| 62 | `服务门店名称` | `TEXT` | 否 | Excel原字段 |
| 63 | `服务门店地址` | `TEXT` | 否 | Excel原字段 |
| 64 | `国补/类国补/消费券` | `NUMERIC(18,2)` | 否 | 金额字段 |
| 65 | `订单销售主体` | `TEXT` | 否 | Excel原字段 |
| 66 | `created_at` | `TIMESTAMPTZ` | 是 | 首次插入数据库的北京时间 |
| 67 | `updated_at` | `TIMESTAMPTZ` | 是 | 最近一次更新数据库的北京时间 |

## 4. 拟执行建表SQL

```sql
BEGIN;

SET LOCAL TIME ZONE 'Asia/Shanghai';

CREATE TABLE kuaishouxiaodian.raw_data (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    "订单号" TEXT NOT NULL,
    "赠品订单号" TEXT,
    "活动订单编号" TEXT,
    "订单创建时间" TIMESTAMPTZ NOT NULL,
    "订单支付时间" TIMESTAMPTZ,
    "预售定金支付时间" TIMESTAMPTZ,
    "订单状态" TEXT,
    "实付款" NUMERIC(18,2),
    "快递费" NUMERIC(18,2),
    "店铺优惠" NUMERIC(18,2),
    "平台补贴" NUMERIC(18,2),
    "主播补贴" NUMERIC(18,2),
    "混资活动优惠" NUMERIC(18,2),
    "支付优惠" NUMERIC(18,2),
    "支付方式" TEXT,
    "成交数量" INTEGER,
    "买家留言" TEXT,
    "账号类型" TEXT,
    "账号明细" TEXT,
    "订单备注" TEXT,
    "旗帜颜色" TEXT,
    "售后状态" TEXT,
    "活动订单" TEXT,
    "预售/承诺发货时间" TIMESTAMPTZ,
    "订单载体" TEXT,
    "国补类型" TEXT,
    "商品名称" TEXT,
    "商品ID" TEXT,
    "商品规格" TEXT,
    "SKU编码" TEXT,
    "商品单价" NUMERIC(18,2),
    "渠道" TEXT,
    "CPS达人ID" TEXT,
    "CPS达人昵称" TEXT,
    "预估推广佣金" NUMERIC(18,2),
    "预估推广者分佣比例" NUMERIC(9,6),
    "团长ID" TEXT,
    "团长昵称" TEXT,
    "快赚客ID" TEXT,
    "快赚客昵称" TEXT,
    "授权推广者ID" TEXT,
    "授权推广者昵称" TEXT,
    "收货人姓名" TEXT,
    "收货人电话" TEXT,
    "收货地址-省" TEXT,
    "收货地址-市" TEXT,
    "收货地址-区" TEXT,
    "收货地址-街道" TEXT,
    "收货地址" TEXT,
    "发货时间" TIMESTAMPTZ,
    "快递公司" TEXT,
    "快递单号" TEXT,
    "物流信息" TEXT,
    "集运类型" TEXT,
    "直邮类型" TEXT,
    "仓库名称" TEXT,
    "仓库地址" TEXT,
    "发货类型" TEXT,
    "实名姓名" TEXT,
    "服务门店ID" TEXT,
    "服务门店名称" TEXT,
    "服务门店地址" TEXT,
    "国补/类国补/消费券" NUMERIC(18,2),
    "订单销售主体" TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT raw_data_order_number_uk UNIQUE ("订单号")
);

CREATE INDEX raw_data_order_created_at_idx
    ON kuaishouxiaodian.raw_data ("订单创建时间");

CREATE INDEX raw_data_order_status_idx
    ON kuaishouxiaodian.raw_data ("订单状态");

CREATE INDEX raw_data_aftersale_status_idx
    ON kuaishouxiaodian.raw_data ("售后状态");

CREATE INDEX raw_data_sku_code_idx
    ON kuaishouxiaodian.raw_data ("SKU编码");

CREATE INDEX raw_data_cps_id_idx
    ON kuaishouxiaodian.raw_data ("CPS达人ID");

CREATE INDEX raw_data_leader_id_idx
    ON kuaishouxiaodian.raw_data ("团长ID");

COMMIT;
```

## 5. 原始文件读取流程

1. 遍历`D:/实习/AI客户看板/data/快手小店/`中的全部`.xlsx`文件。
2. 遍历每个工作簿中的全部工作表。
3. 每个工作表第一行必须与64个原始字段匹配。
4. 忽略完全空白的数据行。
5. 不对订单状态、售后状态、渠道等字段进行业务过滤。
6. 将每一行按照原始字段名写入`raw_data`。

## 6. 数据格式转换规则

### 6.1 空值

以下内容统一写为数据库`NULL`：

```text
Excel空单元格、空字符串、-、--、—、/
```

### 6.2 金额

金额字段处理示例：

```text
¥1,299.90  →  1299.90
￥0        →  0.00
空白       →  NULL
```

### 6.3 百分比

```text
30.0%  →  0.300000
10.0%  →  0.100000
```

### 6.4 日期时间

- 所有时间按照`Asia/Shanghai`解释。
- Excel空白时间写为`NULL`。
- 不使用文件名推算订单日期，以每行`订单创建时间`为准。

### 6.5 标识符

订单号、商品ID、SKU编码、达人ID、团长ID、电话号码和快递单号全部按文本保存，避免科学计数法、精度损失或前导零丢失。

## 7. 新增与更新逻辑

以`订单号`判断记录是否已存在：

```text
订单号不存在 → INSERT
订单号已存在 → UPDATE全部64个原始字段，保留created_at，更新updated_at
```

这样可以处理未来重复导出同一订单时发生的状态变化，例如：

```text
待发货 → 已发货 → 已收货 → 交易成功
售后处理中 → 退款成功
```

## 8. 退款备注在本表中的处理

- `raw_data`只完整保存`订单备注`和`售后状态`，不在本表计算`refund_amount`。
- 后续生成退款表时，上传程序临时解析订单备注。
- 退款计算结果不会覆盖或修改原始订单备注。
- 无法识别金额的部分退款记录会在退款表上传前单独输出供审核。

## 9. 原子上传逻辑

1. 上传前先完成全部Excel文件读取和字段校验。
2. 开启一个PostgreSQL事务。
3. 批量新增或更新`raw_data`。
4. 执行记录数、唯一订单数、日期范围、金额格式校验。
5. 全部校验通过后提交事务。
6. 任意记录转换或写入失败，整张表回滚，不保留部分数据。

## 10. 建表后、上传前必须展示的样例

真正上传数据前，应先向用户展示不少于5条转换样例，至少覆盖：

- CPS达人订单。
- 团长回退订单。
- 自营且客户ID为空的订单。
- 交易关闭且退款成功的订单。
- 订单备注包含“退差价”或“小额打款金额”的订单。

样例需要同时展示Excel原值和准备写入数据库的值。

## 11. 上传完成后的验证

- 数据库记录数应等于全部Excel有效数据行数。
- `订单号`重复数量必须为0。
- 多SKU订单数量必须为0。
- `订单创建时间`为空数量必须为0。
- 核对最早和最晚订单创建时间。
- 分别统计订单状态、售后状态、渠道的数量。
- 随机抽查至少10条记录，与Excel原始内容逐字段对照。

## 12. 待用户审核确认

- [ ] 确认完整保留64个Excel原始字段。
- [ ] 确认`raw_data`总字段数为67个。
- [ ] 确认`订单号`作为业务唯一键。
- [ ] 确认重复订单号采用更新而不是重复插入。
- [ ] 确认金额字段使用`NUMERIC(18,2)`。
- [ ] 确认百分比保存为小数。
- [ ] 确认所有日期时间使用北京时间。
- [ ] 确认`raw_data`不负责计算退款金额。
- [ ] 确认上述建表SQL可以执行。

## 13. 用户修改区

请直接在下方填写需要修改的内容：

```text
（待填写）
```原先表说怎么样的就怎么上传，这里是上传原始数据，除了对空值/-等进行替换外，其余的记录啥的不需要考虑是否重复插入

## 14. 实际执行结果

- 执行状态：成功。
- 实际建表：`kuaishouxiaodian.raw_data`。
- 实际表字段数：67个。
- 导入Excel文件数：10个。
- 遍历工作表数：185个。
- 导入原始记录数：213,351条。
- 订单号唯一约束：未创建，允许后续原始记录重复插入。
- 当前源文件重复订单行数：0条，仅为当前数据事实，不作为数据库约束。
- 订单创建时间范围：2025-02-01 12:37:23至2026-07-28 23:55:58（北京时间）。
- 实付款合计：21,742,991.99元。
- 10条跨文件样例、每条64个原始字段逐字段对比：640项一致，0项差异。
- 数据库事务：建表、导入、行数校验、索引创建全部成功后一次性提交。


