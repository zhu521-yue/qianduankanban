# AI 客户经营看板前后端接口文档

> 对应效果稿：`前端页面效果预览.html`  
> 配套设计文档：`docs/AI客户经营看板前端工程化设计文档.md`  
> 接口版本：V1  
> Base URL：`/api/v1`  
> 编制日期：2026-08-04

---

## 1. 文档目标

本文档是 AI 客户经营看板 V1 的前后端数据契约，规定请求参数、响应字段、枚举、权限、错误码和联调顺序。前端和后端均应以本文档为准，禁止各自使用中文文案、数据库字段或页面临时字段作为另一套隐式协议。

V1 接口覆盖：

- 登录、会话和退出。
- 小组、平台和筛选元数据。
- 渠道总览和组别分析。
- 客户列表和客户详情。
- 销售数据上传、上传任务和上传记录。
- 数据最新日期。

当前 HTML 没有客户名单上传页面，因此本文档不定义客户名单上传端点。如果后续恢复该能力，应升级接口文档后再开发。

---

## 2. 当前后端现状和接口建设边界

当前 `8.4/src/backend/` 已具备以下基础：

- PostgreSQL 连接和仓储查询。
- 7 个平台的统一英文编码。
- 三个小组与平台归属。
- 主管及三个组长角色编码。
- 平台权限校验函数。
- 北京时间、昨日、自然周、自然月和自定义日期范围工具。
- 客户、销售、健康度和平台指标的部分 Repository 查询。

当前尚不具备可直接供浏览器调用的 HTTP API：

- `app.py` 当前返回 `BackendApp` 数据类，不是 ASGI/WSGI Web 应用。
- 没有 `/api/v1` Router、请求模型、响应模型和中间件。
- 没有登录会话实现。
- `DashboardService` 目前只返回原始列表，没有完成页面聚合 DTO。
- 客户列表 Service 尚未暴露跨平台筛选、排序、总数和页面指标聚合。
- 没有上传任务、文件解析、上传日志和任务查询实现。
- `payload.json_value()` 当前把 `Decimal` 转成 `float`，与本文档金额字符串契约不一致。

因此，本文档描述的是目标 HTTP 契约。后端需要在现有 Repository/Service 之上增加 Web Controller/API 层和页面聚合 Service，不建议让前端直接调用原始表查询结果。

---

## 3. 通用约定

### 3.1 协议

- 生产环境：HTTPS。
- 普通请求：`Content-Type: application/json; charset=utf-8`。
- 文件上传：`multipart/form-data`。
- 字符编码：UTF-8。
- API 前缀：`/api/v1`。
- 字段命名：JSON 使用 `snake_case`。

### 3.2 会话

推荐使用服务端会话 Cookie：

```text
Set-Cookie: ai_dashboard_session=<opaque-id>; HttpOnly; Secure; SameSite=Lax; Path=/
```

前端 Axios 必须配置 `withCredentials: true`。前端不得把账号密码或会话 ID 写入 localStorage。

若前后端同域部署，不需要 CORS。若开发期跨端口，后端只允许明确的前端开发 Origin，并允许 Credentials，不得使用 `Access-Control-Allow-Origin: *`。

### 3.3 通用请求头

| 请求头 | 必填 | 说明 |
|---|---:|---|
| `Content-Type` | 是 | JSON 请求或 multipart |
| `X-Request-ID` | 否 | 前端生成 UUID，便于联调追踪；后端没有收到时自行生成 |
| `Idempotency-Key` | 上传时是 | 防止同一次上传因网络重试创建多个任务 |

### 3.4 通用响应结构

成功和失败统一返回：

```json
{
  "code": "OK",
  "message": "success",
  "data": {},
  "errors": [],
  "request_id": "req_01k1z7d6q4b4c8p2"
}
```

字段：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `code` | string | 是 | 稳定业务码 |
| `message` | string | 是 | 面向用户或开发者的简短说明 |
| `data` | object/array/null | 是 | 成功数据；失败时为 `null` |
| `errors` | array | 是 | 结构化错误明细；无错误为空数组 |
| `request_id` | string | 是 | 请求追踪标识 |

### 3.5 结构化错误明细

```json
{
  "field": "end_date",
  "row": null,
  "code": "DATE_AFTER_YESTERDAY",
  "message": "结束日期不能晚于北京时间昨日",
  "raw_value": "2026-08-04"
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `field` | string/null | 请求字段或文件列名 |
| `row` | integer/null | 上传文件行号，非上传错误为 null |
| `code` | string | 具体错误原因码 |
| `message` | string | 可展示的错误说明 |
| `raw_value` | string/null | 可安全返回时提供原值 |

### 3.6 日期、时间和时区

- 业务时区：`Asia/Shanghai`。
- 日期：`YYYY-MM-DD`。
- 日期时间：ISO 8601 且带 `+08:00`。
- 默认参考日期：北京时间昨日。
- 最早业务日期：`2025-02-01`。
- 前端传入的 `start_date`、`end_date` 都是包含边界。
- 后端数据库查询统一转换为半开区间 `[start_date, end_date + 1 day)`。

### 3.7 金额、数量和比例

| 数据 | JSON 类型 | 示例 | 说明 |
|---|---|---|---|
| 金额 | string | `"88420.00"` | 两位小数十进制字符串，单位元 |
| 数量 | integer | `18` | 无小数的业务数量 |
| 可含小数数量 | string | `"18.50"` | 按源数据精度返回 |
| 比例 | number/null | `0.125` | 0.125 表示 12.5%；不可比较为 null |

后端不得把金额以二进制浮点数返回。前端不得使用 `Number` 重新参与金额业务计算，只做格式化展示。

### 3.8 分页

请求：

- `page`：从 1 开始，默认 1。
- `page_size`：默认 20，最大 100。

响应：

```json
{
  "page": 1,
  "page_size": 20,
  "total": 86,
  "total_pages": 5,
  "has_previous": false,
  "has_next": true
}
```

---

## 4. 统一枚举

### 4.1 小组

| `group_key` | 中文名 | 平台 |
|---|---|---|
| `private` | 私域组 | `youzan`, `kuaituantuan` |
| `influencer` | 达人组 | `doudian`, `kuaishouxiaodian`, `weidian` |
| `distribution` | 分销组 | `jushuitan`, `alibaba` |

注意：静态 HTML 使用的 `talent` 不进入正式 API；正式统一为 `influencer`。

### 4.2 平台

| `platform_key` | `display_name` |
|---|---|
| `youzan` | 有赞 |
| `kuaituantuan` | 快团团 |
| `doudian` | 抖店 |
| `kuaishouxiaodian` | 快手小店 |
| `weidian` | 微店 |
| `jushuitan` | 聚水潭线上平台 |
| `alibaba` | 阿里巴巴平台 |

### 4.3 角色

| `role` | 中文名 | 数据范围 |
|---|---|---|
| `supervisor` | 主管 | 全部小组和平台，只读看板，不可上传 |
| `private_leader` | 私域组组长 | 仅私域组和所属平台，可上传销售数据 |
| `influencer_leader` | 达人组组长 | 仅达人组和所属平台，可上传销售数据 |
| `distribution_leader` | 分销组组长 | 仅分销组和所属平台，可上传销售数据 |

### 4.4 时间维度

| `period` | 说明 | 必需日期参数 |
|---|---|---|
| `day` | 指定日 | `reference_date` |
| `week` | 参考日所在自然周 | `reference_date` |
| `month` | 参考日所在自然月 | `reference_date` |
| `custom` | 自定义日期范围 | `start_date`, `end_date` |

`reference_date` 省略时后端使用北京时间昨日。

### 4.5 活跃程度

当前效果稿使用以下 7 档。最终业务若改为 4 档健康等级，需要整体升级枚举，不得只改中文名。

| 编码 | 中文名 | 推荐主题 |
|---|---|---|
| `high_active` | 高活跃 | `success_strong` |
| `active` | 活跃 | `success` |
| `stable` | 稳定客户 | `primary` |
| `watch` | 观察客户 | `warning` |
| `risk` | 风险客户 | `danger` |
| `churn_warning` | 流失预警客户 | `danger_strong` |
| `churned` | 流失客户 | `neutral_dark` |

### 4.6 跟进状态

| 编码 | 中文名 |
|---|---|
| `pending` | 待跟进 |
| `processing` | 处理中 |
| `recorded` | 已记录 |
| `not_required` | 无需跟进 |

V1 只读，不提供修改跟进状态接口。

### 4.7 上传状态

| 编码 | 中文名 | 是否终态 |
|---|---|---:|
| `queued` | 等待处理 | 否 |
| `processing` | 处理中 | 否 |
| `success` | 成功 | 是 |
| `failed` | 失败 | 是 |

如果后续支持有效行入库、错误行跳过，再增加 `partial_success`。V1 在事务规则确认前不使用该状态。

### 4.8 模块状态

| 编码 | 说明 |
|---|---|
| `OK` | 有可用结果 |
| `NO_DATA` | 没有源数据，金额/数量可展示 0 |
| `PARTIAL` | 部分维度或指标可用 |
| `NO_COMPARABLE` | 无可比较数据 |
| `RULE_PENDING` | 业务规则尚未确认，不能计算 |

---

## 5. 接口总览

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| POST | `/auth/login` | 登录 | 未登录 |
| GET | `/auth/session` | 当前会话 | 已登录/未登录均可调用 |
| POST | `/auth/logout` | 退出 | 已登录 |
| GET | `/meta/options` | 组织、枚举和限制元数据 | 已登录 |
| GET | `/dashboard/overview` | 渠道总览 | 主管 |
| GET | `/groups/{group_key}/dashboard` | 组别分析 | 主管或对应组长 |
| GET | `/groups/{group_key}/customers` | 客户列表 | 主管或对应组长 |
| GET | `/groups/{group_key}/customers/{customer_name}` | 客户详情 | 主管或对应组长 |
| POST | `/groups/{group_key}/uploads/sales` | 创建销售上传任务 | 对应组长 |
| GET | `/uploads/{task_id}` | 查询上传任务 | 主管或任务创建人 |
| GET | `/upload-records` | 查询上传记录 | 按会话数据范围 |
| GET | `/data-freshness` | 查询数据库最新业务日期 | 按会话数据范围 |

---

## 6. 登录和会话

### 6.1 登录

`POST /api/v1/auth/login`

请求：

```json
{
  "username": "private_leader",
  "password": "example-password"
}
```

字段：

| 字段 | 类型 | 必填 | 规则 |
|---|---|---:|---|
| `username` | string | 是 | 去除首尾空格后非空 |
| `password` | string | 是 | 原样提交，不在前端日志记录 |

成功：HTTP 200，并设置会话 Cookie。

```json
{
  "code": "OK",
  "message": "登录成功",
  "data": {
    "user": {
      "user_id": "usr_private_leader",
      "display_name": "私域组组长",
      "role": "private_leader",
      "group_key": "private"
    },
    "permissions": [
      "group_dashboard:read",
      "customer:read",
      "sales_upload:create",
      "own_upload_record:read"
    ],
    "default_route": "/groups/private/analysis"
  },
  "errors": [],
  "request_id": "req_login_001"
}
```

失败：HTTP 401。

```json
{
  "code": "INVALID_CREDENTIALS",
  "message": "账号或密码错误",
  "data": null,
  "errors": [],
  "request_id": "req_login_002"
}
```

安全要求：无论账号不存在还是密码错误，都返回相同文案和状态码。

### 6.2 当前会话

`GET /api/v1/auth/session`

已登录成功示例：

```json
{
  "code": "OK",
  "message": "success",
  "data": {
    "authenticated": true,
    "user": {
      "user_id": "usr_supervisor",
      "display_name": "渠道主管",
      "role": "supervisor",
      "group_key": null
    },
    "permissions": [
      "overview:read",
      "all_group_dashboard:read",
      "customer:read",
      "all_upload_record:read"
    ],
    "default_route": "/overview"
  },
  "errors": [],
  "request_id": "req_session_001"
}
```

未登录返回 HTTP 200，便于应用启动判断：

```json
{
  "code": "OK",
  "message": "success",
  "data": {
    "authenticated": false,
    "user": null,
    "permissions": [],
    "default_route": "/login"
  },
  "errors": [],
  "request_id": "req_session_002"
}
```

### 6.3 退出

`POST /api/v1/auth/logout`

成功后使服务端会话失效并清除 Cookie。

```json
{
  "code": "OK",
  "message": "已退出登录",
  "data": null,
  "errors": [],
  "request_id": "req_logout_001"
}
```

---

## 7. 元数据

### 7.1 查询页面选项

`GET /api/v1/meta/options`

后端只返回当前用户可访问的小组和平台。主管返回全部；组长只返回所属范围。

成功示例（主管）：

```json
{
  "code": "OK",
  "message": "success",
  "data": {
    "groups": [
      {
        "key": "private",
        "display_name": "私域组",
        "platforms": [
          {"key": "youzan", "display_name": "有赞"},
          {"key": "kuaituantuan", "display_name": "快团团"}
        ]
      },
      {
        "key": "influencer",
        "display_name": "达人组",
        "platforms": [
          {"key": "doudian", "display_name": "抖店"},
          {"key": "kuaishouxiaodian", "display_name": "快手小店"},
          {"key": "weidian", "display_name": "微店"}
        ]
      },
      {
        "key": "distribution",
        "display_name": "分销组",
        "platforms": [
          {"key": "jushuitan", "display_name": "聚水潭线上平台"},
          {"key": "alibaba", "display_name": "阿里巴巴平台"}
        ]
      }
    ],
    "periods": [
      {"key": "day", "display_name": "日"},
      {"key": "week", "display_name": "周"},
      {"key": "month", "display_name": "月"},
      {"key": "custom", "display_name": "自定义日期"}
    ],
    "activity_levels": [
      {"key": "high_active", "display_name": "高活跃", "theme": "success_strong"},
      {"key": "active", "display_name": "活跃", "theme": "success"},
      {"key": "stable", "display_name": "稳定客户", "theme": "primary"},
      {"key": "watch", "display_name": "观察客户", "theme": "warning"},
      {"key": "risk", "display_name": "风险客户", "theme": "danger"},
      {"key": "churn_warning", "display_name": "流失预警客户", "theme": "danger_strong"},
      {"key": "churned", "display_name": "流失客户", "theme": "neutral_dark"}
    ],
    "follow_statuses": [
      {"key": "pending", "display_name": "待跟进"},
      {"key": "processing", "display_name": "处理中"},
      {"key": "recorded", "display_name": "已记录"},
      {"key": "not_required", "display_name": "无需跟进"}
    ],
    "date_limits": {
      "min_date": "2025-02-01",
      "max_date": "2026-08-03",
      "timezone": "Asia/Shanghai"
    },
    "upload_limits": {
      "allowed_extensions": ["csv", "xlsx"],
      "max_file_size_bytes": 52428800
    }
  },
  "errors": [],
  "request_id": "req_meta_001"
}
```

`max_date` 必须由后端动态按北京时间计算，不能由前端写死。

---

## 8. 看板接口

### 8.1 公共查询参数

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---:|---|---|
| `period` | enum | 否 | `day` | `day/week/month/custom` |
| `reference_date` | date | 否 | 北京时间昨日 | 非 custom 使用 |
| `start_date` | date | custom 是 | - | 自定义开始日期，包含 |
| `end_date` | date | custom 是 | - | 自定义结束日期，包含 |

约束：

- `custom` 时忽略 `reference_date`。
- 非 `custom` 时拒绝同时提交 `start_date/end_date`，避免参数含义不清。
- 日期不得晚于北京时间昨日。

### 8.2 渠道总览

`GET /api/v1/dashboard/overview`

权限：仅 `supervisor`。

请求示例：

```text
GET /api/v1/dashboard/overview?period=day&reference_date=2026-08-03
```

成功示例：

```json
{
  "code": "OK",
  "message": "success",
  "data": {
    "scope": {
      "level": "channel",
      "key": "all",
      "display_name": "渠道整体"
    },
    "query": {
      "period": "day",
      "reference_date": "2026-08-03",
      "start_date": "2026-08-03",
      "end_date": "2026-08-03",
      "timezone": "Asia/Shanghai"
    },
    "sales": {
      "status": "OK",
      "rows": [
        {
          "dimension_type": "channel",
          "dimension_key": "all",
          "display_name": "整体",
          "yesterday_amount": "88420.00",
          "near_7_days_amount": "527600.00",
          "near_30_days_amount": "2198400.00"
        },
        {
          "dimension_type": "group",
          "dimension_key": "private",
          "display_name": "私域组",
          "yesterday_amount": "28600.00",
          "near_7_days_amount": "168200.00",
          "near_30_days_amount": "760300.00"
        }
      ],
      "custom_summary": null,
      "message": ""
    },
    "trends": {
      "status": "OK",
      "items": [
        {
          "key": "year_over_year",
          "display_name": "销售同比",
          "value": 0.125,
          "comparable": true,
          "direction": "up",
          "reason": null,
          "current_amount": "88420.00",
          "comparison_amount": "78598.00"
        },
        {
          "key": "day_over_day",
          "display_name": "日环比",
          "value": 0.038,
          "comparable": true,
          "direction": "up",
          "reason": null,
          "current_amount": "88420.00",
          "comparison_amount": "85183.00"
        }
      ],
      "message": ""
    },
    "customer_distribution": {
      "status": "OK",
      "rows": [
        {
          "dimension_type": "channel",
          "dimension_key": "all",
          "display_name": "整体",
          "total_count": 360,
          "high_active_count": 86,
          "active_count": 128,
          "stable_count": 74,
          "watch_count": 42,
          "risk_count": 21,
          "churn_warning_count": 12,
          "churned_count": 7,
          "rule_version": "activity-v1-draft"
        }
      ],
      "message": ""
    },
    "generated_at": "2026-08-04T12:01:03+08:00"
  },
  "errors": [],
  "request_id": "req_overview_001"
}
```

说明：

- `sales.rows` 必须包含整体及三个小组，顺序由后端按元数据顺序返回。
- `trends.items` 只返回当前时间维度适用的指标。
- 无法比较时仍返回该指标，`value=null`、`comparable=false` 并提供 `reason`。
- 某规则未确认时，对应模块或指标返回 `RULE_PENDING`，不能使用模拟值。

自定义日期时 `sales.custom_summary`：

```json
{
  "start_date": "2026-07-01",
  "end_date": "2026-07-31",
  "rows": [
    {
      "dimension_type": "channel",
      "dimension_key": "all",
      "display_name": "整体",
      "amount": "2284200.00"
    },
    {
      "dimension_type": "group",
      "dimension_key": "private",
      "display_name": "私域组",
      "amount": "760300.00"
    }
  ]
}
```

### 8.3 组别分析

`GET /api/v1/groups/{group_key}/dashboard`

权限：主管可访问全部组；组长只可访问所属组。

请求示例：

```text
GET /api/v1/groups/private/dashboard?period=week&reference_date=2026-08-03
```

响应结构与渠道总览一致，差异如下：

- `scope.level = "group"`。
- `scope.key = "private"`。
- 销售和客户分布行包括“本组整体 + 本组平台”。
- 后端必须校验路径小组和会话授权范围。

示例片段：

```json
{
  "scope": {
    "level": "group",
    "key": "private",
    "display_name": "私域组"
  },
  "sales": {
    "status": "OK",
    "rows": [
      {
        "dimension_type": "group",
        "dimension_key": "private",
        "display_name": "整体",
        "yesterday_amount": "28600.00",
        "near_7_days_amount": "168200.00",
        "near_30_days_amount": "760300.00"
      },
      {
        "dimension_type": "platform",
        "dimension_key": "youzan",
        "display_name": "有赞",
        "yesterday_amount": "13200.00",
        "near_7_days_amount": "71200.00",
        "near_30_days_amount": "302400.00"
      }
    ]
  }
}
```

### 8.4 部分成功

如果销售可用但客户规则尚未生成，HTTP 仍返回 200，根 `code=PARTIAL`：

```json
{
  "code": "PARTIAL",
  "message": "部分模块暂不可用",
  "data": {
    "sales": {"status": "OK", "rows": [], "message": ""},
    "trends": {"status": "OK", "items": [], "message": ""},
    "customer_distribution": {
      "status": "RULE_PENDING",
      "rows": [],
      "message": "客户活跃程度规则尚未确认"
    }
  },
  "errors": [],
  "request_id": "req_overview_partial_001"
}
```

前端只在客户分布模块显示“规则待确认”，不得让整页失败。

---

## 9. 客户列表

### 9.1 查询客户列表

`GET /api/v1/groups/{group_key}/customers`

权限：主管或对应组长。

查询参数：

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---:|---|---|
| `period` | enum | 否 | `day` | 时间维度 |
| `reference_date` | date | 否 | 昨日 | 非 custom 使用 |
| `start_date` | date | custom 是 | - | 自定义开始日期 |
| `end_date` | date | custom 是 | - | 自定义结束日期 |
| `platform` | enum | 否 | - | 必须属于路径小组 |
| `activity_level` | enum | 否 | - | 活跃程度 |
| `follow_status` | enum | 否 | - | 跟进状态 |
| `keyword` | string | 否 | - | 客户名称模糊查询，最长 100 字符 |
| `sort_by` | enum | 否 | `period_amount` | 排序字段 |
| `sort_order` | enum | 否 | `desc` | `asc/desc` |
| `page` | integer | 否 | 1 | 从 1 开始 |
| `page_size` | integer | 否 | 20 | 最大 100 |

允许的 `sort_by`：

- `period_amount`
- `near_7_days_amount`
- `near_30_days_amount`
- `year_over_year`
- `day_over_day`
- `week_over_week`
- `month_over_month`
- `custom_previous_period`
- `quarter_over_quarter`
- `half_year_over_half_year`

请求示例：

```text
GET /api/v1/groups/private/customers?period=day&reference_date=2026-08-03&platform=youzan&activity_level=risk&sort_by=period_amount&sort_order=desc&page=1&page_size=20
```

成功示例：

```json
{
  "code": "OK",
  "message": "success",
  "data": {
    "query": {
      "group_key": "private",
      "period": "day",
      "reference_date": "2026-08-03",
      "start_date": "2026-08-03",
      "end_date": "2026-08-03",
      "platform": "youzan",
      "activity_level": "risk",
      "follow_status": null,
      "keyword": null,
      "sort_by": "period_amount",
      "sort_order": "desc"
    },
    "items": [
      {
        "customer_name": "杭州星选私域客户",
        "platform": {
          "key": "youzan",
          "display_name": "有赞"
        },
        "period_amount": "12860.00",
        "near_7_days_amount": "84230.00",
        "near_30_days_amount": "342100.00",
        "purchase_count": 18,
        "last_purchase_date": "2026-08-03",
        "year_over_year": {
          "value": 0.125,
          "comparable": true,
          "reason": null
        },
        "comparisons": {
          "day_over_day": {"value": 0.021, "comparable": true, "reason": null},
          "week_over_week": {"value": 0.068, "comparable": true, "reason": null},
          "month_over_month": {"value": 0.081, "comparable": true, "reason": null},
          "custom_previous_period": null,
          "quarter_over_quarter": null,
          "half_year_over_half_year": null
        },
        "activity": {
          "level": "risk",
          "display_name": "风险客户",
          "theme": "danger",
          "evaluated_at": "2026-08-03",
          "rule_version": "activity-v1-draft"
        },
        "follow_up": {
          "status": "pending",
          "display_name": "待跟进",
          "suggested_action": "销售连续下滑，建议业务复盘选品"
        }
      }
    ],
    "pagination": {
      "page": 1,
      "page_size": 20,
      "total": 1,
      "total_pages": 1,
      "has_previous": false,
      "has_next": false
    }
  },
  "errors": [],
  "request_id": "req_customers_001"
}
```

字段口径：

- `period_amount`：当前查询周期内销售额，不等同于固定“昨日金额”。
- `near_7_days_amount`、`near_30_days_amount`：均以查询参考日为结束日并包含该日。
- `purchase_count`：后端按最终业务口径计算。
- `comparisons` 中不适用的指标对象返回 `null`；适用但无可比数据时返回对象且 `value=null`。

### 9.2 空列表

HTTP 200，`code=NO_DATA`：

```json
{
  "code": "NO_DATA",
  "message": "没有符合当前条件的客户",
  "data": {
    "query": {},
    "items": [],
    "pagination": {
      "page": 1,
      "page_size": 20,
      "total": 0,
      "total_pages": 0,
      "has_previous": false,
      "has_next": false
    }
  },
  "errors": [],
  "request_id": "req_customers_empty_001"
}
```

### 9.3 参数错误

平台不属于小组时返回 HTTP 400，而不是静默忽略：

```json
{
  "code": "INVALID_PLATFORM_SCOPE",
  "message": "平台不属于当前小组",
  "data": null,
  "errors": [
    {
      "field": "platform",
      "row": null,
      "code": "PLATFORM_NOT_IN_GROUP",
      "message": "alibaba 不属于 private 小组",
      "raw_value": "alibaba"
    }
  ],
  "request_id": "req_customers_invalid_001"
}
```

---

## 10. 客户详情

### 10.1 查询客户详情

`GET /api/v1/groups/{group_key}/customers/{customer_name}`

`customer_name` 必须进行 URL 编码。第一版按“当前小组 + 客户名称”定位，后端需要精确匹配客户名称并校验小组范围。

查询参数与客户列表的时间参数一致：`period/reference_date/start_date/end_date`。

请求示例：

```text
GET /api/v1/groups/private/customers/%E6%9D%AD%E5%B7%9E%E6%98%9F%E9%80%89%E7%A7%81%E5%9F%9F%E5%AE%A2%E6%88%B7?period=day&reference_date=2026-08-03
```

成功示例：

```json
{
  "code": "OK",
  "message": "success",
  "data": {
    "query": {
      "group_key": "private",
      "period": "day",
      "reference_date": "2026-08-03",
      "start_date": "2026-08-03",
      "end_date": "2026-08-03"
    },
    "customer": {
      "customer_name": "杭州星选私域客户",
      "group": {"key": "private", "display_name": "私域组"},
      "platform": {"key": "youzan", "display_name": "有赞"},
      "cooperation_started_at": "2025-03-18",
      "activity": {
        "level": "high_active",
        "display_name": "高活跃",
        "theme": "success_strong",
        "evaluated_at": "2026-08-03",
        "rule_version": "activity-v1-draft"
      },
      "risk": {
        "has_risk": false,
        "primary_type": null,
        "primary_reason": "暂无明显风险",
        "triggered_rules": [],
        "suggested_action": "维持补货节奏，建议推荐新品组合"
      },
      "follow_up": {
        "status": "pending",
        "display_name": "待跟进"
      }
    },
    "sales": {
      "status": "OK",
      "period_amount": "12860.00",
      "near_7_days_amount": "84230.00",
      "near_30_days_amount": "342100.00",
      "average_purchase_amount": "19005.56",
      "purchase_count": 18,
      "year_over_year": {"value": 0.125, "comparable": true, "reason": null},
      "day_over_day": {"value": 0.021, "comparable": true, "reason": null},
      "week_over_week": {"value": 0.068, "comparable": true, "reason": null},
      "month_over_month": {"value": 0.081, "comparable": true, "reason": null}
    },
    "product_trends": {
      "status": "OK",
      "groups": [
        {
          "unit": "day",
          "display_name": "日拿货趋势",
          "items": [
            {
              "product_code": "SKU-001",
              "product_name": "冻干粉礼盒",
              "quantity": "120.00",
              "amount": "28600.00"
            }
          ]
        },
        {
          "unit": "week",
          "display_name": "周拿货趋势",
          "items": []
        },
        {
          "unit": "month",
          "display_name": "月拿货趋势",
          "items": []
        }
      ]
    },
    "generated_at": "2026-08-04T12:01:03+08:00"
  },
  "errors": [],
  "request_id": "req_customer_detail_001"
}
```

可空字段：

- `cooperation_started_at`
- `primary_reason`
- `suggested_action`
- `product_code`
- 比较指标的 `value`

这些字段缺失不应导致整个接口 500。模块无法生成时使用模块状态和空数组。

### 10.2 客户不存在

HTTP 404：

```json
{
  "code": "CUSTOMER_NOT_FOUND",
  "message": "客户不存在",
  "data": null,
  "errors": [],
  "request_id": "req_customer_detail_404"
}
```

### 10.3 客户重名

当前第一版按小组 + 客户名称定位。如果真实数据在同一小组出现重名，后端不得随机返回一条，应返回 HTTP 409：

```json
{
  "code": "AMBIGUOUS_CUSTOMER",
  "message": "客户名称无法唯一定位，请升级客户标识方案",
  "data": null,
  "errors": [],
  "request_id": "req_customer_ambiguous_001"
}
```

此时需要把路由和接口升级为稳定 `customer_id`，不能由前端自行选择第一条。

---

## 11. 销售数据上传

### 11.1 创建上传任务

`POST /api/v1/groups/{group_key}/uploads/sales`

权限：仅对应小组组长。主管调用返回 403。

请求头：

```text
Content-Type: multipart/form-data
Idempotency-Key: 6a8b7c9d-9f05-4d25-b237-1cce61c57c76
```

multipart 字段：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `platform` | string | 是 | 必须属于路径小组和用户权限 |
| `data_date` | date | 是 | 业务数据日期，不得晚于昨日 |
| `overwrite` | boolean | 否 | 默认 true；同组、同平台、同日期已有成功批次时覆盖 |
| `file` | binary | 是 | `.csv` 或 `.xlsx` |

`Idempotency-Key` 用于同一次点击的网络重试；`overwrite` 用于业务批次重复上传，两者含义不同。

处理顺序：

1. 验证会话、角色、小组和平台权限。
2. 验证日期、文件大小、扩展名、文件签名和可读取性。
3. 创建上传任务和上传记录。
4. 异步解析平台字段、校验数据并写入。
5. 成功后刷新相关汇总和规则结果。
6. 更新任务终态。

响应：HTTP 202。

```json
{
  "code": "OK",
  "message": "上传任务已创建",
  "data": {
    "task_id": "upl_01k1zb7d6q4b4c8p2",
    "status": "queued",
    "group": {"key": "private", "display_name": "私域组"},
    "platform": {"key": "youzan", "display_name": "有赞"},
    "data_date": "2026-08-03",
    "file_name": "youzan-sales-20260803.xlsx",
    "file_size_bytes": 183240,
    "operation": "insert_or_replace",
    "created_at": "2026-08-04T10:10:11+08:00",
    "poll_after_ms": 1500
  },
  "errors": [],
  "request_id": "req_upload_create_001"
}
```

幂等要求：

- 相同 `Idempotency-Key` 和相同请求内容重复提交，返回原任务，不创建新任务。
- 相同 `Idempotency-Key` 但文件或参数不同，返回 HTTP 409 `IDEMPOTENCY_CONFLICT`。
- 后端额外计算文件内容 SHA-256 用于审计和重复内容识别。
- 同组、同平台、同 `data_date` 的业务批次按 `overwrite` 规则处理，不以原始文件名作为唯一可靠依据。

### 11.2 查询上传任务

`GET /api/v1/uploads/{task_id}`

权限：任务创建人可查；主管可查所有任务。

处理中：

```json
{
  "code": "OK",
  "message": "任务处理中",
  "data": {
    "task_id": "upl_01k1zb7d6q4b4c8p2",
    "status": "processing",
    "stage": "validating_rows",
    "progress_percent": 65,
    "file_name": "youzan-sales-20260803.xlsx",
    "group": {"key": "private", "display_name": "私域组"},
    "platform": {"key": "youzan", "display_name": "有赞"},
    "data_date": "2026-08-03",
    "total_rows": 1200,
    "success_rows": 0,
    "failed_rows": 0,
    "error_summary": null,
    "errors": [],
    "created_at": "2026-08-04T10:10:11+08:00",
    "started_at": "2026-08-04T10:10:12+08:00",
    "finished_at": null,
    "poll_after_ms": 2000
  },
  "errors": [],
  "request_id": "req_upload_task_001"
}
```

成功：

```json
{
  "code": "OK",
  "message": "上传处理成功",
  "data": {
    "task_id": "upl_01k1zb7d6q4b4c8p2",
    "status": "success",
    "stage": "completed",
    "progress_percent": 100,
    "file_name": "youzan-sales-20260803.xlsx",
    "group": {"key": "private", "display_name": "私域组"},
    "platform": {"key": "youzan", "display_name": "有赞"},
    "data_date": "2026-08-03",
    "total_rows": 1200,
    "success_rows": 1200,
    "failed_rows": 0,
    "error_summary": null,
    "errors": [],
    "created_at": "2026-08-04T10:10:11+08:00",
    "started_at": "2026-08-04T10:10:12+08:00",
    "finished_at": "2026-08-04T10:10:28+08:00",
    "poll_after_ms": null
  },
  "errors": [],
  "request_id": "req_upload_task_002"
}
```

失败：任务查询本身成功，因此 HTTP 200；任务业务状态为 `failed`。

```json
{
  "code": "OK",
  "message": "上传处理失败",
  "data": {
    "task_id": "upl_01k1zb7d6q4b4c8p2",
    "status": "failed",
    "stage": "validating_rows",
    "progress_percent": 100,
    "file_name": "youzan-sales-20260803.xlsx",
    "total_rows": 1200,
    "success_rows": 0,
    "failed_rows": 2,
    "error_summary": "存在无法解析的日期和金额",
    "errors": [
      {
        "field": "订单创建日期",
        "row": 18,
        "code": "INVALID_DATE_VALUE",
        "message": "日期格式无法解析",
        "raw_value": "2026/13/01"
      },
      {
        "field": "订单实付金额",
        "row": 29,
        "code": "INVALID_AMOUNT_VALUE",
        "message": "金额必须为数值",
        "raw_value": "未知"
      }
    ],
    "created_at": "2026-08-04T10:10:11+08:00",
    "started_at": "2026-08-04T10:10:12+08:00",
    "finished_at": "2026-08-04T10:10:16+08:00",
    "poll_after_ms": null
  },
  "errors": [],
  "request_id": "req_upload_task_003"
}
```

错误明细最多内嵌前 100 条，超过时返回：

```json
{
  "returned_error_count": 100,
  "total_error_count": 362,
  "errors_truncated": true
}
```

V1 不提供历史源文件下载。是否提供错误清单下载需单独确认。

### 11.3 文件请求级错误

以下错误在创建任务前返回 4xx：

- 空文件。
- 文件超出限制。
- 扩展名或文件签名不支持。
- 平台不属于小组。
- 用户无上传权限。
- 日期非法。
- 幂等键冲突。

示例：HTTP 415。

```json
{
  "code": "UNSUPPORTED_FILE_TYPE",
  "message": "仅支持 CSV 或 XLSX 文件",
  "data": null,
  "errors": [
    {
      "field": "file",
      "row": null,
      "code": "UNSUPPORTED_FILE_TYPE",
      "message": "文件类型不支持",
      "raw_value": "sales.exe"
    }
  ],
  "request_id": "req_upload_invalid_001"
}
```

---

## 12. 上传记录

### 12.1 查询上传记录

`GET /api/v1/upload-records`

查询参数：

| 参数 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `group` | enum | 否 | 主管可筛选；组长忽略并固定为所属组 |
| `platform` | enum | 否 | 必须在授权范围 |
| `status` | enum | 否 | 上传状态 |
| `start_time` | datetime | 否 | 上传时间下限 |
| `end_time` | datetime | 否 | 上传时间上限 |
| `page` | integer | 否 | 默认 1 |
| `page_size` | integer | 否 | 默认 20 |

权限规则：

- 主管查看全部组记录。
- 组长只查看自己创建的记录。
- 组长提交其他 `group` 参数时返回 403，不静默扩大范围。
- 不返回服务器存储路径和历史文件下载地址。

成功示例：

```json
{
  "code": "OK",
  "message": "success",
  "data": {
    "items": [
      {
        "task_id": "upl_01k1zb7d6q4b4c8p2",
        "uploader": {
          "user_id": "usr_private_leader",
          "display_name": "私域组组长"
        },
        "uploaded_at": "2026-08-04T10:10:11+08:00",
        "group": {"key": "private", "display_name": "私域组"},
        "platform": {"key": "youzan", "display_name": "有赞"},
        "data_type": "sales",
        "data_date": "2026-08-03",
        "file_name": "youzan-sales-20260803.xlsx",
        "status": "success",
        "total_rows": 1200,
        "success_rows": 1200,
        "failed_rows": 0,
        "error_summary": null,
        "finished_at": "2026-08-04T10:10:28+08:00"
      }
    ],
    "pagination": {
      "page": 1,
      "page_size": 20,
      "total": 1,
      "total_pages": 1,
      "has_previous": false,
      "has_next": false
    }
  },
  "errors": [],
  "request_id": "req_upload_records_001"
}
```

记录保留期当前按 6 个月。过期清理是后端运维规则，不由前端删除。

---

## 13. 数据最新日期

### 13.1 查询数据新鲜度

`GET /api/v1/data-freshness`

查询参数：

| 参数 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `group` | enum | 否 | 主管可指定；组长固定所属组 |
| `platform` | enum | 否 | 可指定单个平台 |

成功示例：

```json
{
  "code": "OK",
  "message": "success",
  "data": {
    "items": [
      {
        "group": {"key": "private", "display_name": "私域组"},
        "platform": {"key": "youzan", "display_name": "有赞"},
        "latest_sales_date": "2026-08-03",
        "last_successful_upload_at": "2026-08-04T10:10:28+08:00"
      }
    ],
    "timezone": "Asia/Shanghai"
  },
  "errors": [],
  "request_id": "req_freshness_001"
}
```

该接口主要在销售上传页展示“数据库已更新到 YYYY-MM-DD”。看板页面按当前要求不展示数据更新时间。

---

## 14. HTTP 状态码和业务错误码

| HTTP | `code` | 场景 | 前端处理 |
|---:|---|---|---|
| 200 | `OK` | 请求成功 | 正常展示 |
| 200 | `NO_DATA` | 无业务数据 | 展示空状态或 0 |
| 200 | `PARTIAL` | 部分模块可用 | 成功模块展示，失败模块提示 |
| 202 | `OK` | 上传任务已创建 | 进入轮询 |
| 400 | `VALIDATION_ERROR` | 参数不合法 | 对应字段提示 |
| 400 | `INVALID_DATE` | 日期非法 | 时间控件提示 |
| 400 | `INVALID_PLATFORM_SCOPE` | 平台与小组不匹配 | 清理非法筛选并提示 |
| 401 | `UNAUTHENTICATED` | 会话缺失或失效 | 清空会话，跳转登录 |
| 401 | `INVALID_CREDENTIALS` | 登录失败 | 登录页提示 |
| 403 | `UNAUTHORIZED` | 无权限 | 跳转或展示 403 |
| 404 | `NOT_FOUND` | 资源不存在 | 404 状态 |
| 404 | `CUSTOMER_NOT_FOUND` | 客户不存在 | 客户不存在提示 |
| 409 | `AMBIGUOUS_CUSTOMER` | 客户名称不唯一 | 阻止展示并升级标识方案 |
| 409 | `IDEMPOTENCY_CONFLICT` | 幂等键内容冲突 | 生成新操作或提示重选文件 |
| 409 | `UPLOAD_BATCH_EXISTS` | 不允许覆盖且批次已存在 | 提示用户确认规则 |
| 413 | `FILE_TOO_LARGE` | 上传文件超限 | 文件控件提示 |
| 415 | `UNSUPPORTED_FILE_TYPE` | 文件类型不支持 | 文件控件提示 |
| 422 | `UPLOAD_VALIDATION_FAILED` | 文件结构/数据校验失败 | 展示行和字段错误 |
| 429 | `TOO_MANY_REQUESTS` | 请求过于频繁 | 按 `Retry-After` 重试 |
| 500 | `INTERNAL_ERROR` | 未知服务错误 | 展示请求 ID并允许重试 |
| 503 | `SERVICE_UNAVAILABLE` | 依赖不可用 | 模块提示、稍后重试 |

后端不得使用 HTTP 200 包装权限错误或参数错误。上传任务的“处理失败”是任务终态，查询任务接口本身仍返回 HTTP 200。

---

## 15. 权限校验矩阵

| 资源 | 主管 | 私域组长 | 达人组长 | 分销组长 |
|---|---:|---:|---:|---:|
| 渠道总览 | 读 | 禁止 | 禁止 | 禁止 |
| 私域组分析/客户 | 读 | 读 | 禁止 | 禁止 |
| 达人组分析/客户 | 读 | 禁止 | 读 | 禁止 |
| 分销组分析/客户 | 读 | 禁止 | 禁止 | 读 |
| 私域销售上传 | 禁止 | 创建 | 禁止 | 禁止 |
| 达人销售上传 | 禁止 | 禁止 | 创建 | 禁止 |
| 分销销售上传 | 禁止 | 禁止 | 禁止 | 创建 |
| 全部上传记录 | 读 | 禁止 | 禁止 | 禁止 |
| 自己上传记录 | 不适用 | 读 | 读 | 读 |

后端校验顺序：

1. 会话是否有效。
2. 角色是否允许访问资源类型。
3. 路径小组是否在授权范围。
4. 查询或表单平台是否属于小组且在授权范围。
5. 客户或上传任务是否属于授权范围。

为避免信息泄露，对越权客户和任务统一返回 403，不返回其真实字段。

---

## 16. 前端调用顺序

### 16.1 应用启动

```text
GET /auth/session
├── authenticated=false → /login
└── authenticated=true
    ├── GET /meta/options
    └── 进入 default_route
```

### 16.2 看板页面

```text
路由进入
→ 解析并校验 Query
→ GET overview 或 group dashboard
→ 按模块 status 渲染
→ 条件变化时取消旧请求并发起新请求
```

### 16.3 客户列表到详情

```text
GET customer list
→ 点击 customer_name
→ encodeURIComponent(customer_name)
→ GET customer detail
→ 返回时恢复列表 Query、页码和滚动位置
```

### 16.4 上传

```text
GET /data-freshness
→ 选择平台、日期、文件
→ POST /groups/{group}/uploads/sales
→ 202 返回 task_id
→ 按 poll_after_ms GET /uploads/{task_id}
→ success/failed 停止轮询
→ 刷新上传记录和 data-freshness
```

---

## 17. 后端实现映射建议

此节只用于把目标接口映射到现有代码，不改变接口契约。

| 目标能力 | 现有可复用代码 | 需要补充 |
|---|---|---|
| 平台元数据 | `core/platform_catalog.py` | 序列化为 API DTO |
| 角色权限 | `core/permissions.py` | 会话用户接入、HTTP 403 映射 |
| 日期规则 | `core/time_window.py` | API 参数模型、包含结束日转换 |
| 客户基础列表 | `repositories/customer_repository.py` | 跨平台指标 JOIN、筛选排序分页 Service |
| 销售汇总 | `repositories/sales_repository.py` | 渠道/小组聚合和页面 DTO |
| 平台指标 | `repositories/metrics_repository.py` | 同比环比状态和可比原因 |
| 客户健康 | `repositories/health_repository.py` | 等级、风险、规则版本和聚合 |
| JSON 转换 | `core/payload.py` | Decimal 改为金额字符串 |
| HTTP 应用 | 无 | Web 应用、Router、中间件、异常处理 |
| 登录会话 | 无 | 用户存储、密码哈希、会话 Cookie |
| 上传任务 | 无 | 文件校验、任务表、解析服务、状态查询 |
| 上传记录 | 无 | 记录表、权限查询、6 个月清理 |

### 17.1 页面聚合接口原则

看板接口应由 Service 一次组装页面模块，避免前端为一个页面请求几十个原始表接口。Service 可以并行或分阶段查询，但返回统一 DTO。

### 17.2 数据库字段隔离

以下数据库字段不得直接暴露给前端：

- `customID`
- `dealTime`
- `customAmount`
- `goodCustomAmount`
- `near_7_days`
- 各 schema/table 名称

Repository 先转为 Python 语义字段，页面 Service 再转为本文档 DTO。

### 17.3 金额序列化调整

当前代码把 `Decimal` 转成 float。目标行为：

```python
def decimal_string(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f")
```

数量字段按其业务精度单独处理，不能全部强制两位金额格式。

---

## 18. 联调验收用例

### 18.1 登录

- 正确主管账号返回主管权限和 `/overview`。
- 三个组长分别返回正确 `group_key`。
- 错误账号和错误密码返回相同 `INVALID_CREDENTIALS`。
- 会话失效后受保护接口返回 401。

### 18.2 权限

- 主管可查询三个小组，但上传返回 403。
- 私域组长请求达人组返回 403。
- 私域组长在私域路径提交 `platform=alibaba` 返回 400/403，不能查询数据。
- 修改客户名称和上传任务 ID不能读取越权数据。

### 18.3 时间

- 不传日期时使用北京时间昨日。
- 当天和未来日期返回 `INVALID_DATE`。
- 2025-02-01 以前返回 `INVALID_DATE`。
- 自定义开始日期晚于结束日期返回 400。
- API 结束日期包含当日，数据库不丢失结束日数据。

### 18.4 看板

- 渠道总览金额等于三个小组的同口径合计。
- 组别整体金额等于所属平台合计。
- 0 金额返回 `"0.00"`。
- 无可比数据返回 `value=null`，不返回 0。
- 规则未确认返回 `RULE_PENDING`，不返回模拟数字。

### 18.5 客户

- 筛选、排序和分页由后端执行。
- `total` 与相同筛选条件下总记录数一致。
- 页码超出范围建议返回空页和正确 `total_pages`，或统一校正为最后一页；前后端必须选定一种。V1 建议返回空页，不静默修改请求页码。
- 客户详情与列表同条件下的金额一致。
- 中文、空格和特殊字符客户名称可正确 URL 编解码。

### 18.6 上传

- CSV/XLSX 正常文件创建任务并最终成功。
- 文件过大、类型错误、空文件在创建任务前拒绝。
- 字段和行错误可返回行号、字段和原因。
- 同一次请求重试不重复创建任务。
- 同平台同日期覆盖遵循 `overwrite`。
- 任务成功后数据最新日期和上传记录更新。
- 主管无上传权限，组长不能上传其他组平台。

---

## 19. 接口变更规则

- V1 内新增可空字段属于向后兼容变更。
- 删除字段、改字段类型、改枚举值或改业务含义属于不兼容变更，必须升级版本。
- 中文 `display_name` 可以在业务确认后调整，但英文编码不可在 V1 内随意改变。
- 新增活动等级、跟进状态或上传状态前，前后端必须同时升级映射和测试。
- 数据库字段变化不应直接导致 API 字段变化，应由 Repository/Mapper 隔离。

---

## 20. 联调前必须确认

以下问题尚无最终业务答案，接口已预留状态表达，但不能用模拟逻辑替代：

1. 活跃程度使用 7 档还是健康度 4 档。
2. 比较指标最终算法和自定义周期适用范围。
3. 跟进状态真实来源和枚举是否与效果稿一致。
4. 合作开始时间、主要产品、风险原因和建议动作的数据源。
5. 同一小组客户重名时的稳定 ID迁移方案。
6. 上传覆盖是整批事务替换还是增量合并。
7. 文件校验失败时是否整批回滚；本文档 V1 默认整批失败。
8. 上传错误是否需要下载完整清单。
9. 主管上传记录入口是否作为 V1 必验页面。
10. 客户名单上传是否重新进入范围；当前不包含。

联调前至少应固定第 1、2、3、6、7 项，否则对应模块只能返回 `RULE_PENDING` 或暂停验收。
