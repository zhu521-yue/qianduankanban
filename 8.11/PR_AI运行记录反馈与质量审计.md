# PR：AI 运行记录、反馈与质量审计

> 状态：待用户审查，尚未实施
> 功能批次：AI 智能看板第 4 个功能
> 前置功能：AI 经营洞察、AI 客户经营诊断、AI 全局问看板已实施
> 数据库：沿用 `DATABASE_URL` 指向的 PostgreSQL `weidian`，仅在 `public` Schema 新增两张 AI 审计表
> 产品定位：记录 AI 功能是否成功、是否降级、耗时和用户反馈；不记录明文 API Key、完整提示词或完整对话，不修改九个店铺 Schema 的业务数据

## 1. 本次结论

下一个模块确定为“AI 运行记录、反馈与质量审计”。

当前三个 AI 功能已经能够返回结果，但还不能系统回答以下问题：

- 哪个 AI 功能被使用得最多。
- 哪些请求使用了大模型，哪些使用规则摘要，哪些发生了降级。
- AI 请求成功率、失败率、P95 耗时分别是多少。
- 哪条结果被业务人员认为有帮助或没帮助。
- 页面出现错误时，如何通过 `request_id` 定位该次请求的范围、状态和证据摘要。

本模块先补齐这些生产能力，再继续扩大 AI 问数范围或开发多智能体。它不增加新的经营指标，不修改 AI 回答口径，也不执行自动业务操作。

## 2. 使用角色与页面入口

### 2.1 所有已登录业务用户

在以下 AI 结果下方提供“有帮助 / 没帮助”反馈：

- AI 经营洞察。
- AI 客户经营诊断。
- 客户助手中的 AI 追问回答。
- AI 全局问看板回答。

用户只能评价自己发起的 AI 请求。反馈成功后可修改选择，但同一用户对同一 `request_id` 只保留一条有效反馈。

### 2.2 主管账号

主管端“系统”导航增加“AI 质量”页面，默认查看最近 30 天：

- AI 请求总数。
- 大模型实际调用占比。
- 规则摘要占比。
- 降级率和失败率。
- 平均耗时与 P95 耗时。
- 有帮助反馈率。
- 按功能、状态和日期筛选的趋势与最近请求列表。

普通业务组账号不能打开质量页面，也不能查询其他用户的审计记录。

## 3. 本次实现范围

### 3.1 包含

1. 新建 `public.ai_request_log` 和 `public.ai_feedback`。
2. 记录已实现的四类 AI 请求：
   - `dashboard_insight`
   - `customer_analysis`
   - `customer_chat`
   - `dashboard_query`
3. 新增反馈提交接口。
4. 新增主管端质量汇总、请求列表和请求详情接口。
5. 新增通用前端反馈控件。
6. 新增主管端“AI 质量”页面。
7. 通过现有 `request_id` 关联 HTTP 响应、审计记录和用户反馈。

### 3.2 不包含

- 不恢复已经暂停的“AI 上传影响解读”；该功能未实施，因此本次不产生 `upload_explanation` 日志。
- 不保存用户完整问题、完整对话历史、完整提示词或模型完整原文。
- 不保存 API Key、`DATABASE_URL`、密码、Cookie 或模型供应商鉴权头。
- 不保存客户昵称、商品明细表、客户排行榜整表或问看板返回的整张表格。
- 不新增销售预测、客户流失概率、自动预警或多智能体。
- 不自动修改客户状态、健康规则、看板筛选、上传结果或任何业务表。
- 不在本 PR 内深化全局问看板的指标范围和自然语言能力。

## 4. 数据库连接与新增表

### 4.1 使用哪个数据库

本功能只使用项目根目录 `.env` 中现有的：

```text
DATABASE_URL=postgresql://.../weidian
```

前端不连接数据库。后端继续使用 `app.database.connection()` 和当前连接池，不创建第二套数据库配置。

新增表只位于：

```text
PostgreSQL 数据库：weidian
Schema：public
```

本功能不会向 `weidian`、`doudianChildren`、`doudianKocotree`、`kuaishouxiaodian`、`qijian`、`muyinqijian`、`kuaituantuan`、`alibaba`、`jushuitan` 等业务 Schema 写入数据。

### 4.2 迁移文件

新增：

```text
8.11/backend/migrations/004_ai_audit.sql
```

迁移使用 `CREATE TABLE IF NOT EXISTS` 和 `CREATE INDEX IF NOT EXISTS`，便于重复核验。主键由应用生成 UUID 字符串，不依赖数据库额外扩展。

### 4.3 `public.ai_request_log`

| 字段 | 类型 | 是否可空 | 来源与用途 |
| --- | --- | --- | --- |
| `id` | `text` | 否 | 后端生成 UUID，主键 |
| `request_id` | `text` | 否 | HTTP `X-Request-ID`，唯一索引 |
| `user_id` | `text` | 否 | 登录会话中的 `UserContext.id` |
| `username` | `text` | 否 | 登录会话中的用户名，便于主管定位，不接受前端传入 |
| `role` | `text` | 否 | 登录会话中的角色 |
| `feature_type` | `text` | 否 | 四类 AI 功能白名单 |
| `scope_key` | `text` | 是 | 看板范围；客户功能可保存店铺范围 |
| `store_keys` | `jsonb` | 否 | 已通过权限校验的店铺 Key 数组 |
| `as_of` | `date` | 是 | 本次回答的数据截止日期 |
| `tool_calls` | `jsonb` | 否 | 工具名和脱敏参数摘要，不含 SQL |
| `evidence_summary` | `jsonb` | 否 | 最多 10 条关键证据摘要，不保存整表 |
| `model_name` | `text` | 是 | 实际配置的模型名称；规则模式为空 |
| `mode` | `text` | 否 | `ai` 或 `rule_summary` |
| `status` | `text` | 否 | `running/success/degraded/failed/timeout` |
| `duration_ms` | `integer` | 是 | 从接口开始到结果形成的耗时 |
| `input_tokens` | `integer` | 是 | 供应商明确返回时记录，否则为空，不估算 |
| `output_tokens` | `integer` | 是 | 供应商明确返回时记录，否则为空，不估算 |
| `error_code` | `text` | 是 | 失败时记录项目错误码，不保存异常堆栈 |
| `created_at` | `timestamptz` | 否 | 请求开始时间 |
| `finished_at` | `timestamptz` | 是 | 请求完成时间 |

索引：

```text
UNIQUE(request_id)
INDEX(created_at DESC)
INDEX(user_id, created_at DESC)
INDEX(feature_type, status, created_at DESC)
INDEX(role, created_at DESC)
```

### 4.4 `public.ai_feedback`

| 字段 | 类型 | 是否可空 | 来源与用途 |
| --- | --- | --- | --- |
| `id` | `text` | 否 | 后端生成 UUID，主键 |
| `request_id` | `text` | 否 | 外键关联 `ai_request_log.request_id` |
| `user_id` | `text` | 否 | 当前登录会话用户 ID |
| `helpful` | `boolean` | 否 | 有帮助或没帮助 |
| `reason` | `text` | 是 | 没帮助的受控原因 |
| `comment` | `text` | 是 | 可选补充，最多 500 字 |
| `created_at` | `timestamptz` | 否 | 首次反馈时间 |
| `updated_at` | `timestamptz` | 否 | 最近修改时间 |

约束与索引：

```text
FOREIGN KEY(request_id) REFERENCES public.ai_request_log(request_id) ON DELETE CASCADE
UNIQUE(request_id, user_id)
INDEX(user_id, created_at DESC)
INDEX(helpful, created_at DESC)
```

`reason` 首版仅允许：

```text
data_inaccurate
not_relevant
hard_to_understand
too_slow
data_outdated
other
```

### 4.5 数据保留

- 首版默认保留 90 天，但不会在应用请求过程中执行清理。
- 新增独立清理脚本，默认只显示将删除的数量；明确传入确认参数后才删除超过保留期的两张 AI 表记录。
- 清理顺序先删除反馈，再删除请求日志；不会访问任何业务表。
- 正式部署定时清理前仍需用户单独确认运行时间和保留周期。

## 5. 每个 AI 功能记录什么

| 功能 | `feature_type` | 范围字段 | 工具摘要 | 证据摘要 |
| --- | --- | --- | --- | --- |
| AI 经营洞察 | `dashboard_insight` | `scope_key/store_keys/as_of` | `dashboard_snapshot` | KPI Key、值、周期、来源；最多 10 条 |
| AI 客户诊断 | `customer_analysis` | 单店 `scope_key/store_keys/as_of` | `customer_snapshot`、分析类型 | 状态、周期销售和健康原因的受控证据；不保存昵称 |
| 客户追问 | `customer_chat` | 单店 `scope_key/store_keys/as_of` | 解析后的 `analysis_type` | 与回答实际使用的证据；不保存问题和历史正文 |
| AI 问看板 | `dashboard_query` | `scope_key/store_keys/as_of` | 指标 Key、粒度、分组、比较、行数上限 | 回答证据卡；不保存问题、表格行和图表序列 |

模型生成的长文本不写入审计表。主管质量页面只能看到结构化摘要，不能借此查看用户完整对话。

## 6. 后端具体实现

### 6.1 新增模块

```text
8.11/backend/app/ai_audit.py
```

包含：

- `AiAuditRepository`：只操作 `public.ai_request_log` 和 `public.ai_feedback`。
- `AiAuditService`：开始记录、完成记录、脱敏、反馈权限和主管汇总。
- `sanitize_tool_calls()`：只接受功能白名单字段。
- `sanitize_evidence()`：限制条数、字段和文本长度，删除昵称、问题正文和表格行。
- `safe_start_audit()` / `safe_finish_audit()`：审计写入失败时记录服务日志，但不让 AI 主功能失败。

### 6.2 记录生命周期

每个已登录 AI 请求按以下顺序执行：

```text
身份认证与请求参数校验
  → 生成/取得 request_id
  → start_request(status=running)
  → 原有权限校验、数据库查询和 AI/规则处理
  → 形成确定性证据和最终模式
  → finish_request(success/degraded/failed/timeout)
  → 返回原 AI 响应
```

实现要求：

1. 未登录和请求模型校验失败的请求不进入 AI 审计表。
2. `start_request()` 和 `finish_request()` 使用现有连接池中的短事务，不能长期占用业务查询连接。
3. AI 主功能抛出 `ApiError` 时，先以错误码完成审计，再重新抛出原错误。
4. 模型失败但规则摘要成功时记录 `status=degraded`，接口仍返回 `200`。
5. 未配置 API Key 且规则摘要成功时记录 `mode=rule_summary,status=success`，不错误地记为降级。
6. 审计写入异常不能覆盖 AI 主功能的结果或错误。
7. 不记录 SQL、数据库表完整内容、请求 Cookie、API Key 和提示词正文。

### 6.3 接入现有接口

修改：

```text
POST /api/v1/ai/dashboard-insight
POST /api/v1/ai/customer-analysis
POST /api/v1/ai/chat
POST /api/v1/ai/query
```

上述接口的业务查询、权限和返回数字保持原样，仅在外围增加审计生命周期。`/api/v1/ai/chat` 的 `data` 中补充 `request_id`，用于给每条助手回答提交反馈。

## 7. 新增接口

### 7.1 提交或修改反馈

```text
POST /api/v1/ai/feedback
```

请求：

```json
{
  "request_id": "req_xxx",
  "helpful": false,
  "reason": "data_inaccurate",
  "comment": "本月销售额与页面卡片不一致"
}
```

规则：

- 后端从会话读取 `user_id`，请求体不接受用户 ID。
- 请求日志必须存在且属于当前用户。
- `helpful=true` 时 `reason` 可为空。
- `helpful=false` 时必须选择受控原因；`comment` 可为空。
- 使用 `ON CONFLICT(request_id, user_id) DO UPDATE`，重复点击不会生成多条反馈。

响应：

```json
{
  "request_id": "req_xxx",
  "helpful": false,
  "reason": "data_inaccurate",
  "updated": true
}
```

### 7.2 查询单次请求摘要

```text
GET /api/v1/ai/requests/{request_id}
```

- 普通用户只能读取自己的请求。
- 主管可以读取全部请求，但只返回脱敏后的结构化摘要。
- 找不到返回 `404 AI_REQUEST_NOT_FOUND`。
- 无权查看返回 `403 AI_AUDIT_FORBIDDEN`。

### 7.3 主管质量汇总

```text
GET /api/v1/ai/audit/summary?days=30&feature_type=&status=
```

只允许主管调用，返回：

- 请求总数。
- AI、规则摘要、降级和失败数量及占比。
- 平均耗时、P95 耗时。
- 有帮助、没帮助和未反馈数量。
- 按天趋势。
- 按功能分布。

### 7.4 主管请求列表

```text
GET /api/v1/ai/audit/requests?days=30&feature_type=&status=&page=1&page_size=20
```

只允许主管调用。列表不返回完整问题、完整回答、客户昵称或证据明细，只返回定位和质量统计所需字段。

## 8. 前端具体实现

### 8.1 通用反馈控件

新增：

```text
8.11/frontend/app/AiFeedbackControl.tsx
```

交互：

1. AI 结果成功出现后显示“这条分析有帮助吗？”。
2. 点击“有帮助”直接提交。
3. 点击“没帮助”展开原因选择和可选补充说明。
4. 成功后显示“反馈已记录”，仍允许修改。
5. 反馈接口失败只在控件内提示重试，不影响 AI 结果展示。
6. 控件只接收 `request_id`，不接收或发送 AI 回答正文。

接入：

- `AiInsightPanel.tsx`
- `CustomerAiAssistant.tsx`
- `AskDashboardDrawer.tsx`

### 8.2 主管“AI 质量”页面

新增：

```text
8.11/frontend/app/AiQualityPage.tsx
```

页面结构：

1. 顶部筛选：最近 7/30/90 天、功能类型、状态。
2. 指标卡：总请求、AI 调用率、降级率、失败率、有帮助率、P95 耗时。
3. 每日请求趋势图：成功、降级、失败使用同一日期轴。
4. 功能分布：经营洞察、客户诊断、客户追问、问看板。
5. 最近请求表：时间、请求 ID、账号、角色、功能、模式、状态、耗时、反馈。
6. 点击请求 ID 查看脱敏详情：范围、日期、工具摘要、证据摘要和错误码。

页面不提供“重新执行”“修改数据”“重放提示词”或导出完整对话功能。

### 8.3 路由与权限

- `PageKind` 增加 `ai-quality`。
- 仅主管页面列表增加 `#/manager/ai-quality`。
- 普通业务账号的前端导航不显示该入口。
- 即使普通账号手工修改 Hash，后端主管接口仍返回 `403`。

## 9. 安全与隐私边界

必须满足：

1. API Key 和连接字符串不得进入两张审计表、接口响应和前端状态。
2. 不保存完整自然语言问题、完整回答和对话历史。
3. 不保存模型系统提示词、供应商错误正文和异常堆栈。
4. 客户昵称、客户排行榜整表和商品明细不进入审计表。
5. `user_id`、`role`、范围和店铺全部来自后端登录会话与权限解析结果。
6. 前端传入的 `request_id` 只能用于定位，不能决定记录所属用户。
7. 普通用户不能枚举请求列表或查看他人请求。
8. 所有展示文本继续按普通 React 文本渲染，不使用 `dangerouslySetInnerHTML`。
9. 审计功能只能写 `public.ai_request_log` 和 `public.ai_feedback`。

## 10. 失败与降级处理

| 场景 | 行为 |
| --- | --- |
| 审计表尚未迁移 | AI 主功能继续返回；服务日志记录 `AI_AUDIT_UNAVAILABLE`；质量页提示审计未初始化 |
| 开始日志写入失败 | 继续执行 AI 主功能，不再次无限重试 |
| 完成日志写入失败 | 返回 AI 结果；保留服务日志用于排查 |
| AI Provider 失败、规则降级成功 | 请求返回 `200`，审计状态为 `degraded` |
| 业务查询或权限校验失败 | 保留原错误码，审计状态为 `failed` |
| 反馈目标不存在 | `404 AI_REQUEST_NOT_FOUND` |
| 用户评价他人请求 | `403 AI_FEEDBACK_FORBIDDEN` |
| 主管质量查询无数据 | 正常返回零值和空趋势，不伪造样例数据 |

## 11. 预计文件变更

新增：

```text
8.11/backend/migrations/004_ai_audit.sql
8.11/backend/app/ai_audit.py
8.11/backend/scripts/apply_ai_audit_migration.py
8.11/backend/scripts/prune_ai_audit.py
8.11/backend/tests/test_ai_audit.py
8.11/frontend/app/AiFeedbackControl.tsx
8.11/frontend/app/AiQualityPage.tsx
```

修改：

```text
8.11/backend/app/main.py
8.11/backend/app/schemas.py
8.11/frontend/app/api.ts
8.11/frontend/app/AiInsightPanel.tsx
8.11/frontend/app/CustomerAiAssistant.tsx
8.11/frontend/app/AskDashboardDrawer.tsx
8.11/frontend/app/page.tsx
8.11/frontend/app/globals.css
8.11/frontend/tests/rendered-html.test.mjs
8.11/backend/README.md
```

## 12. 测试计划

### 12.1 数据库

- 迁移重复执行不会创建重复表或索引。
- 两张表只创建在 `public` Schema。
- `request_id` 唯一约束有效。
- 同一用户同一请求只能有一条反馈。
- 删除请求日志时关联反馈按约束清理。
- 清理脚本默认不删除数据，确认模式只删除超过保留期的审计记录。

### 12.2 后端记录

- 四类 AI 接口成功时写入正确的功能类型、范围、模式和耗时。
- 未配置 API Key 的规则摘要记录为 `success`，不是 `degraded`。
- Provider 异常并成功降级时记录 `degraded`。
- 受控查询拒绝、权限拒绝和业务查询失败记录原错误码。
- 审计写入失败不改变原接口状态码和结果。
- 日志不包含 API Key、连接字符串、完整提示词、问题正文、客户昵称或表格明细。

### 12.3 权限与反馈

- 登录用户可以评价自己的请求并修改反馈。
- 普通用户不能评价或查看他人请求。
- 普通用户不能调用主管汇总和请求列表接口。
- 主管可以查看脱敏汇总、列表和单次请求摘要。
- 非法原因、超长评论和不存在的请求被拒绝。

### 12.4 前端

- 三个 AI 组件均显示反馈入口。
- 客户追问回答携带对应 `request_id`，反馈不会串到上一条回答。
- 反馈失败不隐藏 AI 结果。
- 只有主管导航显示“AI 质量”。
- 筛选变化会取消旧请求，旧响应不能覆盖新条件。
- 无数据时显示空状态，不显示伪造图表。
- 新增组件定向 ESLint、前端构建和渲染测试通过。

### 12.5 回归

- 现有 AI 经营洞察、客户诊断、客户追问和全局问看板结果不变。
- 登录、权限、设置、上传和原业务看板不受影响。
- 后端完整测试通过。
- 前端构建和完整渲染测试通过。

## 13. 开发、迁移、重启与验收顺序

1. 用户审查并批准本 PR。
2. 实现迁移、Repository、Service 和单元测试。
3. 接入四个现有 AI 接口并验证脱敏边界。
4. 实现反馈接口和主管质量查询接口。
5. 接入三个前端 AI 组件和客户追问反馈。
6. 实现主管“AI 质量”页面。
7. 运行后端完整测试、前端构建、渲染测试和定向 ESLint。
8. 执行迁移前先只读核对目标表不存在或结构兼容。
9. 执行 `004_ai_audit.sql`，只创建 `public` 下的两张审计表。
10. 安全重启前后端。
11. 用四类真实登录角色验证反馈权限，用主管账号验证质量页面。
12. 保持前后端运行，交由用户审查页面效果。

## 14. 验收标准

- 四类现有 AI 请求都能形成唯一审计记录。
- 规则成功、AI 成功、AI 降级和失败状态可以准确区分。
- 用户可以评价自己的 AI 结果且可修改反馈。
- 主管可以查看 7/30/90 天质量指标、趋势和脱敏请求列表。
- 普通业务账号不能查看全局质量数据。
- 审计表中不存在 API Key、连接字符串、完整问题、完整回答、提示词或客户昵称。
- 审计系统异常不影响原 AI 功能和业务看板。
- 只向 `public.ai_request_log` 和 `public.ai_feedback` 写入，不写九个业务 Schema。
- 自动测试、真实数据库验证和重启健康检查通过。
- 用户完成页面效果审查。

## 15. 回滚方案

1. 前端移除“AI 质量”导航和反馈控件，不影响原 AI 结果显示。
2. 后端停用反馈、质量查询和审计外围调用，原四类 AI 接口恢复现有执行路径。
3. 两张审计表不参与任何业务计算，停用后不会影响销售、退款、客户、商品、上传和健康规则。
4. 如用户明确要求删除审计表，必须另行备份并确认后执行；本 PR 的普通回滚不自动删除已记录数据。

## 16. 用户审查重点

1. 是否同意第 4 个功能确定为“AI 运行记录、反馈与质量审计”。
2. 是否同意只在 PostgreSQL `weidian.public` 新建 `ai_request_log` 和 `ai_feedback` 两张表。
3. 是否同意不保存完整问题、完整回答、完整对话和客户昵称，只保存脱敏结构化证据。
4. 是否同意普通用户只能评价自己的请求，主管可以查看全局脱敏质量数据。
5. 是否同意默认保留 90 天，但定时清理部署仍需后续单独确认。
6. 是否同意本次不扩大问看板能力、不恢复上传解释，也不开发预测或多智能体。
