# 快手小店第2张表审核草稿：`kuaishouxiaodian.customer_id_mapping`

> 状态：已确认、已增加`渠道 = '分销'`规则、已同步、已校验通过  
> 数据库：`weidian`  
> Schema：`kuaishouxiaodian`  
> 表序号：02 / 35  
> 上游表：`kuaishouxiaodian.raw_data`

## 1. 表的作用

`customer_id_mapping`用于从快手原始订单中解析并保存统一的客户ID和客户昵称，供后续所有客户维度销售表使用。

- 只处理`渠道`字段去除首尾空格后等于`分销`的原始记录。
- `自营`、空渠道和其他渠道记录不进入客户ID表。
- CPS达人ID有值时，客户ID使用CPS达人ID，客户昵称使用CPS达人昵称。
- CPS达人ID为空时，客户ID使用团长ID，客户昵称使用团长昵称。
- CPS达人ID和团长ID都为空时，客户ID使用快赚客ID，客户昵称使用快赚客昵称。
- CPS达人ID、团长ID和快赚客ID都为空时，该原始订单不进入客户ID表。
- 一个客户ID在本表中只能保留一条记录。
- 本表严格保留5个字段，不增加平台来源等其他字段。

## 2. 数据粒度

- 一条记录代表一个去重后的客户。
- 主键：`id`。
- 业务唯一键：`customer_id`。
- 当前`raw_data`可以保留重复订单，但不会造成客户ID表重复，因为本表按`customer_id`去重。

## 3. 字段设计

| 序号 | 字段 | PostgreSQL类型 | 是否必填 | 说明 |
|---:|---|---|---|---|
| 1 | `id` | `BIGINT` | 是 | 自增主键 |
| 2 | `customer_id` | `TEXT` | 是 | 按CPS达人ID、团长ID、快赚客ID的顺序选择 |
| 3 | `customer_nickname` | `TEXT` | 否 | 与最终选用的客户ID来源保持一致 |
| 4 | `created_at` | `TIMESTAMPTZ` | 是 | 首次插入数据库的北京时间 |
| 5 | `updated_at` | `TIMESTAMPTZ` | 是 | 最近更新数据库的北京时间 |

## 4. 当前原始数据核验结果

基于已经上传的213,351条`raw_data`记录：

- `分销`渠道原始记录：194,431条。
- `自营`渠道原始记录：18,920条，不进入客户ID表。
- 使用CPS达人ID的原始记录：191,917条。
- CPS达人ID为空、使用团长ID回退的原始记录：2,302条。
- CPS达人ID和团长ID都为空、使用快赚客ID回退的原始记录：212条。
- 分销渠道中三类客户ID都为空的原始记录：0条。
- 去重后的客户ID数量：1,252个。
- 完全没有昵称的客户：1个。
- 只有一个昵称的客户：1,197个。
- 历史上出现多个昵称的客户：54个。
- 单个客户ID出现的昵称变体最多为41个。

## 5. 客户ID解析逻辑

```sql
CASE
    WHEN NULLIF(BTRIM("CPS达人ID"), '') IS NOT NULL
        THEN BTRIM("CPS达人ID")
    WHEN NULLIF(BTRIM("团长ID"), '') IS NOT NULL
        THEN BTRIM("团长ID")
    ELSE NULLIF(BTRIM("快赚客ID"), '')
END AS customer_id
```

客户昵称必须与选中的ID来源一致：

```sql
CASE
    WHEN NULLIF(BTRIM("CPS达人ID"), '') IS NOT NULL
        THEN NULLIF(BTRIM("CPS达人昵称"), '')
    WHEN NULLIF(BTRIM("团长ID"), '') IS NOT NULL
        THEN NULLIF(BTRIM("团长昵称"), '')
    ELSE NULLIF(BTRIM("快赚客昵称"), '')
END AS customer_nickname
```

不能对三个昵称字段单独使用`COALESCE`，否则可能发生客户ID来自CPS达人、昵称却来自团长或快赚客的错误组合。客户昵称必须与实际选中的客户ID来源保持一致。

## 6. 同一客户多个昵称的处理

当前有54个客户ID出现过多个昵称。建议规则：

1. 优先选择非空昵称。
2. 多个非空昵称同时存在时，选择订单创建时间最新的一条。
3. 订单创建时间相同时，选择`raw_data.id`较大的一条。
4. 如果该客户所有历史记录的昵称都为空，则`customer_nickname`保存`NULL`。

该规则可以在达人修改昵称后自动保留最新昵称，同时不会增加表字段。

## 7. 拟执行建表SQL

```sql
BEGIN;

SET LOCAL TIME ZONE 'Asia/Shanghai';

CREATE TABLE kuaishouxiaodian.customer_id_mapping (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id TEXT NOT NULL,
    customer_nickname TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT customer_id_mapping_customer_id_uk UNIQUE (customer_id)
);

COMMIT;
```

## 8. 首次数据生成逻辑

```sql
WITH resolved AS (
    SELECT
        CASE
            WHEN NULLIF(BTRIM("CPS达人ID"), '') IS NOT NULL
                THEN BTRIM("CPS达人ID")
            WHEN NULLIF(BTRIM("团长ID"), '') IS NOT NULL
                THEN BTRIM("团长ID")
            ELSE NULLIF(BTRIM("快赚客ID"), '')
        END AS customer_id,
        CASE
            WHEN NULLIF(BTRIM("CPS达人ID"), '') IS NOT NULL
                THEN NULLIF(BTRIM("CPS达人昵称"), '')
            WHEN NULLIF(BTRIM("团长ID"), '') IS NOT NULL
                THEN NULLIF(BTRIM("团长昵称"), '')
            ELSE NULLIF(BTRIM("快赚客昵称"), '')
        END AS customer_nickname,
        "订单创建时间" AS order_created_at,
        id AS raw_id
    FROM kuaishouxiaodian.raw_data
    WHERE BTRIM("渠道"::text) = '分销'
), ranked AS (
    SELECT
        customer_id,
        customer_nickname,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY
                (customer_nickname IS NOT NULL) DESC,
                order_created_at DESC,
                raw_id DESC
        ) AS row_number
    FROM resolved
    WHERE customer_id IS NOT NULL
)
INSERT INTO kuaishouxiaodian.customer_id_mapping (
    customer_id,
    customer_nickname
)
SELECT
    customer_id,
    customer_nickname
FROM ranked
WHERE row_number = 1;
```

## 9. 后续原始数据新增后的更新逻辑

每次`raw_data`增加新记录后，只从`渠道 = '分销'`的记录中重新解析最新客户映射，并根据`customer_id`更新：

```text
新客户ID → INSERT
已有客户ID、昵称未变化 → 不修改
已有客户ID、出现更新昵称 → 更新customer_nickname和updated_at
```

不会因为原始订单重复而增加重复客户。

## 10. 原子建表与上传逻辑

1. 开启PostgreSQL事务。
2. 创建`customer_id_mapping`表。
3. 从`raw_data`中筛选`渠道 = '分销'`的记录。
4. 解析客户ID和客户昵称，并排除客户ID为空的记录。
5. 按客户ID去重并写入1,252条客户记录。
6. 检查客户ID唯一性、空值和来源记录数。
7. 全部通过后提交；任一步失败则回滚建表和数据写入。

## 11. 建表后、上传前应展示的样例

至少展示以下样例：

- CPS达人ID和昵称直接映射的客户。
- CPS达人ID为空、使用团长ID和昵称的客户。
- CPS达人ID和团长ID都为空、使用快赚客ID和昵称的客户。
- 同一客户出现多个昵称、最终选取最新昵称的客户。
- 客户ID存在但客户昵称为空的客户。
- CPS达人ID、团长ID和快赚客ID都为空、被排除的原始记录。

## 12. 上传完成后的验证

- 客户ID表记录数应为1,252条。
- `customer_id`为空的记录数必须为0。
- 重复`customer_id`数量必须为0。
- 当前允许`customer_nickname`为空的客户数为1个。
- 正式表必须与`raw_data`中`渠道 = '分销'`的客户解析结果完全一致。
- 随机抽查至少10个客户，与`raw_data`解析结果逐条对照。

## 13. 用户审核确认结果

- [x] 确认表中只有5个字段。
- [x] 确认所有客户相关表只处理`渠道 = '分销'`的记录。
- [x] 确认客户ID优先级为CPS达人ID、团长ID、快赚客ID。
- [x] 确认无客户ID的原始订单不进入客户ID表。
- [x] 确认一个客户ID只保留一条记录。
- [x] 确认多个昵称时使用最新非空昵称。
- [x] 确认客户昵称允许为`NULL`。
- [x] 确认上述建表和数据生成逻辑可以执行。

## 14. 用户修改区

请直接在下方填写需要修改的内容：

```text
（待填写）
```

## 15. 实际执行与校验结果

执行时间：2026-08-10（北京时间）。

- 建表和首次数据写入在同一个PostgreSQL事务中完成并成功提交。
- 实际写入记录数：1,252条。
- 实际字段数：5个。
- 不同`customer_id`数量：1,252个。
- `customer_id`为空：0条。
- 重复`customer_id`：0条。
- `customer_nickname`为空：1条。
- 使用相同规则从`raw_data`重新计算，再与正式表逐条全量对比：差异0条。
- 主键约束与`customer_id`唯一约束均已生效。

三种来源均已抽查到有效记录：

| 来源 | 样例客户ID | 样例客户昵称 | 被选中记录的订单创建时间（北京时间） |
|---|---|---|---|
| CPS达人 | `415121040` | 小洛31号儿童营养加油站❤️ | 2026-07-28 23:55:58 |
| 团长回退 | `3110269899` | 品上品优选 | 2026-07-28 21:56:01 |
| 快赚客回退 | `3548264061` | 悠悠扬 | 2026-07-16 17:09:19 |

## 16. 分销渠道规则补充与数据库复核

补充执行时间：2026-08-10（北京时间）。

- 用户新增统一规则：所有与客户相关的表必须增加`BTRIM("渠道"::text) = '分销'`筛选条件。
- 已在单一PostgreSQL事务中，按分销渠道重新生成期望客户集合并同步正式表。
- 分销渠道记录：194,431条；自营渠道记录：18,920条。
- 当前所有能够解析出客户ID的记录本来就全部属于分销渠道，因此本次同步删除客户0个、修改客户0个、新增客户0个。
- 同步后正式表仍为1,252个客户，客户ID空值0条，昵称空值1条。
- 使用分销渠道规则重新全量计算后，与正式表对比差异0条。
- 该筛选规则已经加入首次生成逻辑和后续刷新逻辑，未来自营或其他渠道即使出现客户ID，也不会进入客户相关表。
