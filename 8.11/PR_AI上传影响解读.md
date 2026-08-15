# PR：AI 上传影响解读——预览事实摘要、风险提示与人工核对项

> 状态：已暂停，未实施；用户决定第 3 个功能转向“全局问看板”
> 原计划批次：AI 智能看板第 3 个功能，现不进入开发
> 前置功能：AI 经营洞察、AI 客户经营诊断已实施
> 数据库：沿用 PostgreSQL `weidian`；AI 不新增 SQL，不读取上传文件二进制，只解释现有上传预览任务
> 实施范围：上传预览解释接口、确定性规则摘要、模型增强与降级、上传页解释卡片、测试和前后端重启验收

> 变更说明：用户确认当前方案的主要价值来自规则计算，AI 感知较弱，因此暂停本 PR。文件保留作为后续候选方案，不修改上传业务代码。

## 1. 功能目标

在业务人员完成“上传并预览”后，自动解释本次文件会怎样影响数据库和看板，包括：

1. 文件有效行、无效行、新增、替换、跳过或更新的规模。
2. 店铺销售额、退款额和预售数据的预计变化。
3. 平台、业务组和渠道汇总表的联动影响。
4. 变化最大的周期和需要优先核对的异常。
5. 是否存在已有日期覆盖、退款口径重算、负向销售变化或无有效变化。

本功能只帮助业务人员理解已经生成的确定性上传预览，不参与文件解析、不重新计算金额、不改变上传结果，也不自动执行数据库写入。

### 1.1 AI 配置行为

- 未配置 `api_key`：后端使用确定性规则生成完整解释。
- 已配置 `api_key`：模型只增强事实摘要的中文表达。
- 模型异常：自动降级为规则解释，原上传预览和“确认写入数据库”按钮保持可用。
- AI 返回内容不能修改 `commit_available`、上传模式、预计增删改数量或任何预览数字。

## 2. 当前上传能力

当前项目已经具备：

- `POST /api/v1/uploads/sales` 的 `preview` 和 `commit` 两种模式。
- 九个店铺分别解析原始 `.xlsx` / `.csv` 文件。
- 预览阶段返回 `UploadPreview`，包含行数、日期、客户、销售、退款、预售和汇总变化。
- 正式写入前再次完整解析文件，并在单个数据库事务内提交和刷新派生表。
- 每次预览生成 `upl_...` 任务 ID，任务保存在当前后端进程的 `upload.service.TASKS` 中。
- 前端已经展示详细预览和“确认写入数据库”按钮。

当前缺口：预览数据较多，业务人员需要逐项阅读后才能判断本次上传的主要影响和风险。

## 3. 本 PR 范围

### 3.1 本次实现

- 新增 `POST /api/v1/ai/upload-explanation`。
- 根据 `upload_id` 读取当前进程中的上传预览任务。
- 从预览结果构造经过字段白名单过滤的解释快照。
- 使用确定性代码计算事实摘要、主要影响、风险和人工核对项。
- 已配置模型时增强摘要表达，失败时返回规则解释。
- 上传预览成功后在当前店铺上传卡片内自动加载解释。
- 重新选择文件、重新预览或清除文件时取消旧请求并清除旧解释。
- AI 解释失败不影响上传预览和手工确认写入。
- 完成自动测试、安全重启和真实上传预览任务验收。

### 3.2 本次不实现

- 不读取或保存上传文件二进制。
- 不让模型查看原始行、客户样本或行级错误明细。
- 不在 AI 接口中调用任何 `committer.py`。
- 不通过 AI 自动提交上传。
- 不让 AI 修改 `commit_available`。
- 不新增上传任务数据库表；本期仍受当前进程内任务生命周期限制。
- 不新增 AI 请求日志和反馈表；审计与反馈继续作为独立功能建立后续 PR。
- 不实现全局问看板或多智能体。

## 4. 数据库及数据来源

### 4.1 数据库连接

本功能不建立新的数据库连接，继续使用项目根目录 `.env` 中 `DATABASE_URL` 指向的 PostgreSQL 数据库 `weidian`。

AI 解释接口本身不执行新的业务 SQL。数据链路为：

```text
PostgreSQL weidian
  → 现有上传预览 analyse_upload()
  → analysis_payload()
  → UploadService.TASKS[upload_id]
  → AI 字段白名单快照
  → 确定性解释 / 模型增强摘要
```

因此 AI 展示的金额和行数与用户页面上的原始上传预览来自同一份结构化结果，不维护第二套计算口径。

### 4.2 现有上传预览涉及的 Schema

| 店铺 Key | PostgreSQL Schema | 预览读取和对比的主要数据 |
| --- | --- | --- |
| `weidian` | `weidian` | `raw_data`、客户映射、销售/退款/预售周期表 |
| `doudian_children` | `doudianChildren` | `raw_data`、客户映射、销售/退款周期表 |
| `doudian_kocotree` | `doudianKocotree` | `raw_data`、客户映射、销售/退款周期表 |
| `kuaishou` | `kuaishouxiaodian` | `raw_data`、客户映射、销售/退款周期表 |
| `youzan_qijian` | `qijian` | `raw_data`、客户映射、销售/退款周期表 |
| `youzan_muying` | `muyinqijian` | `raw_data`、客户映射、销售/退款周期表 |
| `kuaituantuan` | `kuaituantuan` | `raw_data`、业务键、客户映射、销售/退款周期表 |
| `alibaba` | `alibaba` | `raw_data`、客户映射、销售/退款周期表 |
| `jushuitan` | `jushuitan` | `raw_data`、客户映射、销售/退款周期表 |

预览还会形成 `doudian`、`youzan`、`daren`、`siyu`、`fenxiao`、`qudao` 等上层汇总范围的预计变化。AI 只解释预览返回的汇总结果，不自行查询这些 Schema。

### 4.3 AI 允许读取的预览字段

```text
id / store_key / mode / status / commit_available
upload_strategy
total_rows / valid_rows / invalid_rows
new_date_rows / existing_date_rows / replacement_date_rows
skipped_existing_date_rows
rows_to_delete / rows_to_insert / update_rows / unchanged_rows
new_customer_rows
dates.file / dates.new / dates.existing / dates.replacement / dates.changed_existing
business_preview.source_classification
business_preview.store_period_changes
business_preview.aggregate_period_changes
refresh.store_tables / refresh.aggregate_schemas / refresh.aggregate_tables
```

明确禁止进入 AI 上下文的字段：

```text
上传文件内容
完整文件路径
changed_row_sample
new_customer_sample
errors 的行级原始内容
数据库连接字符串
API Key
其他上传任务或其他客户数据
```

## 5. 后端接口设计

### 5.1 请求

`POST /api/v1/ai/upload-explanation`

```json
{
  "upload_id": "upl_xxx"
}
```

请求模型只接受 `upl_` 开头、长度受控的任务 ID。

### 5.2 响应

```json
{
  "code": "OK",
  "data": {
    "mode": "rule_summary",
    "configured": false,
    "degraded": false,
    "empty": false,
    "headline": "本次预览将覆盖已有日期，并带来销售额负向变化",
    "summary": "文件共包含1000行，其中980行有效。预览涉及2个已有日期，店铺月销售预计下降12.5%，建议写入前核对覆盖日期和销售变化来源。",
    "facts": [
      {
        "key": "valid_ratio",
        "label": "有效行率",
        "value": "98.0%",
        "description": "1000行中有980行通过平台解析和业务校验。"
      }
    ],
    "impacts": [
      {
        "key": "largest_sales_change",
        "label": "最大销售影响",
        "value": "-12.5%",
        "period": "2026-08-01—2026-08-31",
        "scope": "当前店铺",
        "source": "business_preview.store_period_changes.months",
        "description": "该月预计销售额较当前数据库值下降12.5%。"
      }
    ],
    "warnings": ["预览将替换已有日期数据，写入前请核对文件日期范围。"],
    "checks": [
      {
        "priority": "high",
        "title": "核对已有日期覆盖",
        "description": "确认替换日期和文件导出范围符合本次上传目的。"
      }
    ],
    "can_commit": true,
    "upload_id": "upl_xxx",
    "store_key": "weidian",
    "generated_at": "2026-08-15T10:30:00+08:00",
    "request_id": "req_xxx"
  }
}
```

`can_commit` 必须直接复制上传任务的 `commit_available`，不能来自规则或模型判断。

## 6. 权限与安全流程

1. 接口必须经过现有 `current_user` 登录校验。
2. 使用 `UploadService.task(upload_id, include_errors=False)` 读取任务。
3. 非主管账号只能读取其角色允许店铺的任务。
4. 主管可以查看任务解释，但不能通过本接口提交文件。
5. 找不到任务时返回现有 `UPLOAD_NOT_FOUND`，并提示任务可能因后端重启失效。
6. 只从任务复制白名单字段，不能把完整任务对象直接发送给模型。
7. AI 路由和解释服务不得导入上传提交器。
8. 模型提示词明确要求只做内部数据解释，不得判断“自动通过”或要求自动写入。
9. 所有文本由 React 普通文本节点渲染，不执行模型 HTML。

## 7. 确定性规则解释

后端新增 `build_upload_explanation(snapshot)`，所有数值、风险和核对优先级由普通代码生成。

### 7.1 事实计算

- 有效行率：`valid_rows / total_rows`。
- 无效行率：`invalid_rows / total_rows`。
- 新增、更新、不变、跳过、替换和预计删除行数。
- 文件覆盖日期范围及已有日期数量。
- 当前店铺各周期销售、退款预计变化额和变化率。
- 预售行数、数量和金额，仅在预览包含预售字段时展示。
- 受影响店铺表数量、上层 Schema 数量和汇总表数量。
- 按绝对变化额选择销售和退款影响最大的周期。

### 7.2 初始风险规则

| 规则 | 条件 | 输出 |
| --- | --- | --- |
| 有效行偏低 | 无效行率 `>= 5%` | 提醒核对文件格式和错误行 |
| 有效行严重偏低 | 无效行率 `>= 20%` | 高优先级，建议先处理数据质量问题 |
| 覆盖已有日期 | `replacement_date_rows > 0` 或替换日期不为空 | 提醒核对覆盖范围 |
| 商品明细更新 | `update_rows > 0` | 说明将更新现有业务键记录 |
| 数据被跳过 | `skipped_existing_date_rows > 0` | 说明已有日期不会重复写入 |
| 销售明显下降 | 任一周期预计销售额相对当前值下降 `>= 10%` | 提醒核对文件完整性和覆盖范围 |
| 退款明显上升 | 任一周期预计退款额相对当前值上升 `>= 10%` | 提醒核对退款分类和口径 |
| 退款口径重算 | `refund_rule_reclassification_amount != 0` | 单独说明重分类金额 |
| 无实际影响 | 增删改均为零且周期金额无变化 | 说明本次预览没有可写入变化 |
| 数据不足 | 当前值为零，无法计算可靠变化率 | 展示金额变化，不生成虚假百分比 |

阈值只负责提示人工核对，不改变 `commit_available`，也不会自动禁止写入。

### 7.3 模型增强

- 模型只接收确定性结果中的 `headline`、`summary`、`facts`、`impacts`、`warnings` 和 `checks`。
- 模型只能增强 `summary`，不得修改其他字段。
- 输出限制为2至4句中文纯文本、300字以内。
- 模型调用失败时返回规则结果并设置 `degraded=true`。

## 8. 前端设计

新增 `AiUploadExplanation.tsx`，放在原始上传预览下方、写入按钮上方。

页面结构：

- 标题：“AI 上传影响解读”。
- 模式标签：`规则解读` / `AI 解读` / `已降级`。
- 核心结论和摘要。
- 关键事实：有效行率、日期处理方式、预计增删改、受影响表数量。
- 主要影响：变化最大的销售/退款周期及上层汇总范围。
- 风险提示和人工核对项。
- 未配置 AI 时显示“当前使用后端规则解读”和设置入口。
- 固定说明：“AI 只解释预览，不会自动写入数据库”。

### 8.1 请求生命周期

1. `uploadPreview()` 成功并返回 `preview.id` 后自动请求解释。
2. 组件请求必须携带 `AbortController`。
3. 重新选择文件、清除文件、重新预览或组件卸载时取消旧请求。
4. 响应的 `upload_id` 必须与当前 `preview.id` 一致才展示。
5. 正式写入完成后展示现有 `UploadCommitResult`，不把预览解释当作实际写入结果。
6. AI 解释加载或失败期间，原预览和手动提交按钮保持独立可用。

## 9. 预计修改文件

- `8.11/backend/app/schemas.py`：新增 `UploadExplanationRequest`。
- `8.11/backend/app/services.py`：增加预览快照过滤、规则解释和模型提示词。
- `8.11/backend/app/main.py`：新增 `/api/v1/ai/upload-explanation`。
- `8.11/backend/tests/test_upload_explanation.py`：新增规则、权限、字段过滤和降级测试。
- `8.11/frontend/app/api.ts`：新增上传解释类型和请求方法。
- `8.11/frontend/app/AiUploadExplanation.tsx`：新增解释组件。
- `8.11/frontend/app/page.tsx`：在 `UploadCard` 中接入解释组件。
- `8.11/frontend/app/globals.css`：增加事实、影响、风险和核对项样式。
- `8.11/frontend/tests/rendered-html.test.mjs`：增加接口、组件和“不自动提交”边界测试。

原则上不修改 `upload/committer.py`、上传解析器和数据库迁移文件。

## 10. 测试计划

### 10.1 后端

- 未登录返回 `AUTH_REQUIRED`。
- 无权店铺任务返回 `UPLOAD_FORBIDDEN`。
- 不存在或重启失效任务返回 `UPLOAD_NOT_FOUND`。
- 规则解释与预览中的行数、日期和金额一致。
- 上一期为零时不生成虚假变化率。
- 有效行率、覆盖日期、销售下降、退款上升和无变化规则正确。
- `can_commit` 与 `commit_available` 完全一致。
- 解释接口不能调用上传提交器或产生数据库写入。
- 模型上下文不包含文件二进制、行级样本、数据库凭据和 API Key。
- 未配置 AI 时不调用模型。
- 模型失败时返回规则解释。

### 10.2 前端

- 上传预览成功后自动请求解释。
- 解释卡片和原始预览同时存在。
- 规则、AI 和降级模式正确展示。
- 风险和人工核对项分区展示。
- 重新选择文件会取消旧请求并清除旧解释。
- AI 失败不隐藏或禁用手工提交按钮。
- 页面不出现“自动通过”或自动写入行为。
- 窄屏布局不溢出。

### 10.3 回归

- 九店铺上传预览和正式写入流程不变。
- 主管仍不能提交上传。
- AI 经营洞察和客户助手不受影响。
- 后端完整测试、前端构建、渲染测试和新增组件 lint 通过。

## 11. 重启与验收流程

1. 用户审查并批准本 PR。
2. 只开发本 PR 范围内的上传影响解读。
3. 完成定向测试和完整回归测试。
4. 检查3000和8000端口监听进程及项目路径。
5. 只停止确认属于当前项目的前后端进程。
6. 重启后端并请求 `http://127.0.0.1:8000/api/v1/health`。
7. 重启前端并确认 `http://localhost:3000` 返回200。
8. 使用实际上传预览任务验证规则模式，不执行正式写入。
9. 保持前后端运行，等待用户页面审查。

## 12. 用户审查重点

1. 是否同意第3个功能确定为“AI 上传影响解读”。
2. 是否同意 AI 只解释预览，不读取文件原文、不重新计算金额、不自动提交。
3. 是否同意 `can_commit` 完全复制现有 `commit_available`。
4. 是否同意本次继续使用进程内上传任务，不新增上传任务表。
5. 是否同意审计与反馈仍作为独立后续 PR，不夹带到本功能。
6. 是否同意初始风险阈值：无效行率5%/20%、销售下降10%、退款上升10%。

## 13. 验收标准

- 上传预览后自动出现结构化影响解读。
- 所有数字均能在当前 `UploadPreview` 中复核。
- 未配置 AI 时规则解释可用。
- 模型失败不影响预览和手动提交。
- AI 不读取文件原文、不调用提交器、不改变提交资格。
- 跨组任务和匿名请求不可访问。
- 后端、前端测试通过。
- 前后端安全重启并保持运行。
- 用户完成页面效果审查。

## 14. 回滚方案

本功能新增独立解释接口和前端组件，不修改上传解析、提交事务或数据库结构。出现问题时移除 `AiUploadExplanation` 的页面接入并停用 `/api/v1/ai/upload-explanation` 即可，原上传预览和正式写入流程不受影响。
