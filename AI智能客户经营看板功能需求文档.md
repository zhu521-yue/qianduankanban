# AI 智能客户经营看板功能需求文档

> 文档版本：V1.2
> 编制日期：2026-08-14
> 文档状态：评审稿
> 适用对象：产品、业务负责人、前端、后端、数据开发、测试
> 项目目录：`D:\实习\AI客户看板\8.11`
> 产品定位：面向公司内部业务部门，在现有客户经营看板基础上建设“数据可信、权限受控、结论可追溯”的 AI 智能经营看板；不承担客服回复或客户沟通职能。
> V1.1 修订：补充当前 PostgreSQL 数据库、Schema、业务表、各功能取数范围及具体实现路径。
> V1.2 修订：将数据库连接、具体表字段、接口、后端执行步骤和前端改造点直接写入各个待开发功能项。

---

## 1. 文档目的

本文档用于统一 AI 智能客户经营看板的产品目标、用户角色、功能范围、业务流程、AI 能力边界、数据口径、权限规则、接口方向、非功能要求和验收标准，可作为后续需求评审、研发排期、测试用例设计和上线验收的共同基线。

本文档中的功能状态分为：

| 状态 | 含义 |
| --- | --- |
| 已有 | 当前 `8.11` 工程中已经存在可运行的前后端能力 |
| 一期新增 | AI 智能看板 MVP 必须完成的能力 |
| 二期增强 | MVP 稳定后建设的受控自然语言问数能力 |
| 三期规划 | 数据、权限、审计成熟后再建设的多智能体协作能力 |
| 暂不建设 | 当前阶段明确不进入研发范围的能力 |

---

## 2. 产品背景与核心问题

### 2.1 当前基础

现有项目已具备以下业务基础：

- 主管、达人组、私域组、分销组四类账号角色。
- 登录、会话校验、退出登录及后端数据权限校验。
- 九个店铺及店铺、平台、小组、全渠道多级数据范围。
- 日、周、月、季度、半年五种统计粒度。
- 销售指标、销售趋势、客户健康、商品 Top、退款和部分店铺预售数据。
- 客户列表、客户检索、分页、健康度及客户详情。
- 客户详情中的 AI 对话入口。
- 分角色 AI 接口地址、密钥、模型名称配置及连接测试。
- 销售文件上传、业务预检、变更影响预览、确认入库和结果展示。
- 客户健康规则查看与组长范围内的规则编辑。

### 2.2 当前问题

现有看板可以展示数据，但仍主要依赖用户自行阅读图表并形成判断，存在以下问题：

1. 主管需要跨小组、跨平台浏览多个模块，才能得出“经营是否正常、变化来自哪里、下一步做什么”。
2. 组长能看到客户健康和销售数据，但缺少直接可执行的客户诊断、内部核查重点和跟进优先级。
3. 上传预览能够展示大量表级和周期级变化，但业务人员理解这些变化仍有成本。
4. 当前 AI 客户助手上下文较窄，主要使用客户基本信息和半年数据，尚未形成完整的证据链。
5. 用户无法使用自然语言询问看板数据，也无法把答案直接转成表格、图表和筛选后的客户清单。
6. 不同店铺的数据最新日期可能不同，部分客户健康快照与销售周期可能不一致，AI 若忽略这些问题会产生误导。

### 2.3 产品目标

AI 智能看板需要帮助用户完成三个层次的任务：

1. **看懂现状**：自动总结当前范围、当前日期下的经营表现和关键变化。
2. **找到原因**：从小组、店铺、客户、商品、退款等维度解释主要驱动因素。
3. **形成行动**：给出可核对、可执行但不自动执行的经营建议和客户跟进建议。

### 2.4 成功标准

- 主管进入首页后，无需逐块阅读即可在 1 分钟内获得经营概况、异常点和建议动作。
- 组长进入客户详情后，可在 30 秒内得到客户表现诊断、风险依据和内部跟进建议。
- 上传人员在正式入库前，可明确知道文件会影响哪些日期、指标和汇总范围。
- 所有 AI 结论均能展示数据范围、截止日期、关键指标和证据来源。
- AI 不得绕过账号权限，不得直接连接任意表执行无限制 SQL，不得自动提交上传或修改业务数据。

---

## 3. 产品原则

### 3.1 数据先于生成

关键金额、数量、比例、排名和周期变化必须由后端确定性计算产生。大模型负责理解问题、组织表达、解释数据和生成建议，不负责自行计算核心经营指标。

### 3.2 权限先于回答

AI 可访问的数据范围必须与当前登录账号一致。前端隐藏不等于权限控制，所有 AI 工具和接口均由后端再次校验角色、范围和店铺权限。

### 3.3 结论必须可追溯

每条经营结论至少包含：统计范围、统计截止日期、相关指标、比较窗口和数据来源。无法获得证据时，应明确回答“当前数据不足”，不得猜测。

### 3.4 建议不自动执行

AI 可以给出内部经营建议、核查事项和优先级，但一期、二期均不自动修改客户状态、不自动提交文件、不自动联系客户、不自动执行任意数据库写操作。

### 3.5 先单助手，后多智能体

一期优先建设稳定、简单、可验证的单一 AI 编排层。多智能体只在指标语义、工具权限、日志审计和验证机制成熟后建设。

---

## 4. 用户角色与权限

### 4.1 角色定义

| 角色 | 数据范围 | 核心任务 | AI 能力范围 |
| --- | --- | --- | --- |
| 主管 `manager` | 全部小组及九个店铺 | 查看全渠道经营、比较小组和店铺、识别主要风险 | 全局经营摘要、跨组对比、范围内问数、查看全部客户分析；只读健康规则 |
| 达人组长 `talent` | 微店、两家抖店、快手小店 | 管理达人渠道经营、上传数据、跟进客户 | 本组经营摘要、本组问数、客户分析、上传影响解释；可编辑本组健康规则 |
| 私域组长 `private` | 两家有赞店、快团团 | 管理私域经营、上传数据、跟进客户 | 本组经营摘要、本组问数、客户分析、上传影响解释；可编辑本组健康规则 |
| 分销组长 `distribution` | 阿里巴巴、聚水潭 | 管理分销经营、上传数据、跟进客户 | 本组经营摘要、本组问数、客户分析、上传影响解释；可编辑本组健康规则 |

### 4.2 权限规则

1. 用户登录后由后端返回角色和所属小组。
2. 主管可访问 `all`、三个小组及全部店铺范围。
3. 组长只能访问本组及本组所属平台、店铺范围。
4. 组长只能上传本组店铺数据。
5. AI 查询、AI 摘要和 AI 客户分析必须复用与看板一致的权限解析规则。
6. 用户在问题中指定无权访问的店铺、客户或范围时，系统返回“当前账号无权访问该范围”，不得由大模型自行解释或绕过。
7. API Key 仅由后端保存和调用，前端只显示掩码，不返回明文。

---

## 5. 信息架构

```text
登录
├── 主管端
│   ├── 整体经营概览
│   ├── 分销组 / 店铺
│   ├── 私域组 / 平台 / 店铺
│   ├── 达人组 / 平台 / 店铺
│   ├── 全局“问看板”入口
│   └── 主管端 AI 设置
├── 达人组长端
│   ├── 本组整体 / 平台 / 店铺看板
│   ├── 客户列表 / 客户详情 / AI 客户助手
│   ├── 数据上传 / AI 上传影响解释
│   ├── 全局“问看板”入口
│   └── 健康规则与 AI 设置
├── 私域组长端
│   └── 同组长通用结构
└── 分销组长端
    └── 同组长通用结构
```

### 5.1 三个 AI 入口

| 入口 | 所在位置 | 主要用途 | 建设阶段 |
| --- | --- | --- | --- |
| AI 经营洞察 | 每个经营看板顶部 | 自动总结经营表现、变化原因、风险和建议动作 | 一期新增 |
| AI 客户助手 | 客户详情页右侧 | 诊断单客户、解释健康状态、生成内部核查和跟进建议 | 已有入口，一期增强 |
| 问看板 | 全局侧边抽屉 | 使用自然语言查询权限范围内的经营数据 | 二期增强 |

---

## 6. 核心业务流程

### 6.1 主管查看经营概况

1. 主管登录并进入整体经营概览。
2. 系统按权限加载全部店铺的可比统计截止日期。
3. 页面展示确定性 KPI、趋势、客户健康、商品和退款数据。
4. AI 经营洞察根据同一份结构化数据生成摘要。
5. 主管可点击某条结论的“查看依据”，定位到对应图表或下钻到小组、店铺、客户列表。
6. 主管可通过“问看板”继续询问变化原因或获取对比表。

### 6.2 组长分析重点客户

1. 组长进入本组看板或客户列表。
2. 按客户 ID、健康状态、销售额或风险等级筛选客户。
3. 进入客户详情，查看日、周、月、季度、半年销售和商品数据。
4. AI 客户助手展示默认诊断摘要。
5. 用户可选择“最近表现”“风险原因”“主要商品”“店铺退款背景”“内部跟进建议”等快捷问题。
6. AI 返回结论、数据证据、建议动作和数据不足说明。

### 6.3 上传并理解数据影响

1. 组长在上传页选择有权限的店铺和文件。
2. 后端进行格式、字段、业务日期、重复数据和业务规则预检。
3. 页面展示新增、替换、跳过、退款重分类、周期汇总和表级变化。
4. AI 将结构化预览解释为业务摘要，提示主要影响和风险。
5. 用户确认无误后手动点击“确认写入数据库”。
6. 入库完成后系统展示确定性写入结果；AI 可生成结果摘要，但不得替代写入结果。

### 6.4 自然语言问数

1. 用户打开“问看板”并输入问题。
2. 系统识别指标、范围、时间和期望输出形式。
3. 信息不足时只追问缺失且会显著改变结果的条件。
4. 后端校验账号权限，调用白名单数据工具获取结构化结果。
5. 系统进行口径、合计和数据新鲜度校验。
6. 返回文字结论、关键数字、表格或图表、数据日期和依据。

---

## 7. 详细功能需求

### 7.0 待开发功能的数据库连接总表

本项目不需要分别连接九个独立数据库。所有待开发功能都通过 `8.11/backend/app/database.py` 的连接池，连接项目根目录 `.env` 中 `DATABASE_URL` 指向的同一个 PostgreSQL 数据库 `weidian`；“连接哪个数据库”在本项目中主要表现为“本次功能允许访问数据库内哪些 Schema 和表”。

| 待开发功能 | 连接的数据库 | 允许访问的 Schema / 表 | 是否写数据库 | 具体开发入口 |
| --- | --- | --- | --- | --- |
| AI 经营洞察 | PostgreSQL `weidian` | 当前权限范围内九个店铺 Schema 的销售、客户、商品、退款、健康、微店预售表 | 只读业务表；写 `public.ai_request_log` | 新增 `/api/v1/ai/dashboard-insight` |
| AI 客户经营诊断与内部跟进建议 | PostgreSQL `weidian` | 当前客户所属单店 Schema 的客户销售、客户商品、健康、映射表；读取对应 `public` 健康规则表 | 只读业务表；写 AI 日志和反馈 | 新增 `/api/v1/ai/customer-analysis`，增强 `/api/v1/ai/chat` |
| AI 上传影响解释 | PostgreSQL `weidian` | 不由 AI 重新查询；使用现有上传预览从目标店铺及汇总 Schema 生成的结构化结果 | AI 不写业务表；写 AI 日志 | 新增 `/api/v1/ai/upload-explanation` |
| 全局问看板 | PostgreSQL `weidian` | 按指标白名单读取九个店铺 Schema 的派生汇总表 | 只读业务表；写 AI 日志和反馈 | 新增 `/api/v1/ai/query` |
| AI 反馈与审计 | PostgreSQL `weidian` | `public.ai_request_log`、`public.ai_feedback` | 只写这两张新表 | 新增迁移和 `/api/v1/ai/feedback` |
| 多智能体 | PostgreSQL `weidian` | Agent 不直连数据库，只调用问看板的只读工具 | 只写统一 AI 日志 | 三期扩展现有 AI 编排服务 |

下文每个待开发功能继续给出精确表名、字段、后端步骤和前端改造点。

### 7.1 登录与会话

#### FR-AUTH-001 登录

**状态：已有，需保持。**

- 用户输入用户名和密码登录。
- 登录成功后后端创建会话 Cookie，并返回用户角色、所属小组和过期时间。
- 主管默认进入主管整体经营概览；组长默认进入本组整体经营概览。
- 登录失败时展示明确错误，不透露账号是否存在等敏感信息。

**验收标准：**

- 正确账号密码可登录并进入对应首页。
- 错误密码不可创建会话。
- 未登录访问业务接口返回 401；无权限访问返回 403。
- 页面刷新后可通过会话接口恢复登录状态，不出现“已登录但所有页面提示请先登录”的状态不一致。

#### FR-AUTH-002 退出和过期

- 用户点击退出后，后端清除会话，前端清空用户状态并返回登录页。
- 会话过期后，任意业务请求收到 401 时统一触发登录态失效处理。
- 网络错误、后端 500 和无权限 403 不得错误显示为“请先登录”。

---

### 7.2 基础经营看板

#### FR-DASH-001 数据范围

**状态：已有，需保持并增强数据日期说明。**

- 主管支持全渠道、小组、平台、店铺范围。
- 组长支持本组、平台、店铺范围。
- 页面切换范围后，所有 KPI、图表、列表和 AI 洞察使用同一 `scope_key`。

#### FR-DASH-002 时间范围

- 支持日、周、月、季度、半年五种统计粒度。
- 默认统计截止日期不得晚于数据库最新完整日期。
- 单店铺页面以该店铺最新完整日期为上限。
- 多店铺汇总页面一期建议以所选范围内“最小最新日期”作为可比截止日期，避免部分店铺数据尚未更新导致汇总失真。
- 若店铺最新日期不一致，页面显示“数据新鲜度提示”，列出落后店铺和相差天数。
- 任何 AI 回答必须继承当前页面日期，除非用户在问题中明确指定其他日期。

#### FR-DASH-003 KPI 与分析模块

保留并统一以下模块：

| 模块 | 核心内容 | 默认粒度/范围 |
| --- | --- | --- |
| 销售 KPI | 半年销售额、本月销售额、半年客户数、半年商品数 | 当前范围、当前截止日 |
| 销售趋势 | 最近 6 个周期的销售额 | 用户选择粒度 |
| 客户健康 | 七类客户健康状态、健康客户数及占比 | 当前业务周/有效健康快照 |
| 商品 Top | 按数量 Top5、按金额 Top5、双榜商品数 | 当前业务半年 |
| 退款 | 本期、上期、变化率和最近 6 个周期趋势 | 用户选择粒度 |
| 预售 | 预售金额、数量、商品数及 Top 商品 | 仅数据可用的店铺 |
| 客户列表 | 客户 ID、店铺、销售额、拿货次数、健康度、状态 | 当前业务半年 |

#### FR-DASH-004 状态处理

- 加载中展示骨架或明确加载提示。
- 范围内无数据时展示“暂无数据”，不得显示伪造的 0 趋势。
- 比率分母为 0 时展示“暂无”，不得显示无依据的 0%。
- 接口失败展示原始业务错误摘要和重试按钮。
- 数据不完整时展示警告，不得把不完整数据包装成完整结论。

---

### 7.3 AI 经营洞察

#### FR-AI-INSIGHT-001 自动摘要

**状态：一期新增，MVP 核心功能。**

##### 数据库连接与具体取数

本功能只连接当前项目已经配置的一个 PostgreSQL 数据库：

```text
连接配置：项目根目录 .env -> DATABASE_URL
后端连接入口：8.11/backend/app/database.py -> connection()
数据库名称：weidian
连接次数：每次接口请求复用连接池中的一个连接
连接权限：仅后端持有；前端和大模型均不能获得 DATABASE_URL
```

接口收到 `scope_key` 后，通过 `catalog.resolve_scope(current_user.role, scope_key)` 得到允许查询的店铺，再映射到以下 Schema：

| `scope_key` 示例 | 实际连接的 Schema |
| --- | --- |
| `all` | `weidian`、`doudianChildren`、`doudianKocotree`、`kuaishouxiaodian`、`qijian`、`muyinqijian`、`kuaituantuan`、`alibaba`、`jushuitan` |
| `talent` | `weidian`、`doudianChildren`、`doudianKocotree`、`kuaishouxiaodian` |
| `private` | `qijian`、`muyinqijian`、`kuaituantuan` |
| `distribution` | `alibaba`、`jushuitan` |
| 单店范围 | 只连接该店铺对应 Schema |

每个被选中的店铺 Schema 读取以下表：

| 洞察内容 | 表 | 读取字段 |
| --- | --- | --- |
| 最新完整日期 | `daily_sales` | `MAX(transaction_date)` |
| 本月/上月销售 | `monthly_sales` | `period_start`、`period_end`、`monthly_transaction_amount` |
| 当前/上个半年销售 | `half_year_sales` | `period_start`、`period_end`、`half_year_transaction_amount` |
| 最近趋势 | `daily_sales`、`weekly_sales`、`monthly_sales`、`quarterly_sales` 或 `half_year_sales` | 对应周期起止日期和金额字段 |
| 活跃客户数 | `customer_half_year_sales` | `customer_id`、`half_year_transaction_amount` |
| 健康分布 | `customer_weekly_sales` + `customer_health_detail` | `customer_id`、周期、`customer_health_status`、`updated_at` |
| 商品 Top | `half_year_product_sales` | `product_code`、`half_year_product_quantity`、`half_year_transaction_amount` |
| 退款趋势 | `weekly_refunds`、`monthly_refunds`、`quarterly_refunds`、`half_year_refunds` | 周期起止日期和对应退款金额字段 |
| 微店预售 | `weidian.monthly_product_presales`、`quarterly_product_presales`、`half_year_product_presales` | `product_code`、预售数量、预售金额、`is_presale` |

AI 经营洞察不读取 `raw_data`，也不直接读取 `doudian`、`youzan`、`daren`、`siyu`、`fenxiao`、`qudao` 汇总 Schema；一期继续以九个店铺事实 Schema 为唯一事实来源，避免汇总表命名和刷新时间不同造成数字不一致。

##### 后端具体实现

新增接口：

```text
POST /api/v1/ai/dashboard-insight
```

请求参数：

```json
{
  "scope_key": "talent",
  "as_of": "2026-08-11",
  "trend_grain": "month",
  "refund_grain": "month"
}
```

后端执行顺序：

1. `current_user()` 从加密 Cookie 恢复用户角色。
2. `resolve_scope()` 校验 `scope_key` 并返回允许访问的店铺集合。
3. 新增 `DashboardRepository.latest_data_dates(store_keys)`，逐个执行 `SELECT MAX(transaction_date) FROM <schema>.daily_sales`；多店汇总取最小日期作为完整截止日，同时返回各店日期供警告展示。
4. 调用现有 `DashboardService.dashboard()` 获取 KPI、趋势、健康、商品、退款和预售快照，不另写一套 AI SQL。
5. 新增 `DashboardRepository.scope_contribution()`，按同一周期逐店读取本期、上期销售额和退款额，返回贡献额、变化额和变化率。
6. 新增 `build_dashboard_evidence()`，把所有关键数字转成不可由模型修改的 `evidence[]`。
7. 新增规则分析器，先判断最大增减项、退款异常、健康异常和数据日期差异。
8. 将“规则结论 + 精简证据 JSON”发送给 `request_ai_completion()`；模型只生成解释和建议。
9. 模型返回后检查回答中引用的指标是否存在于 `evidence[]`；无法核对的数字从回答中移除或将本次请求降级为规则摘要。
10. 将请求信息写入 `public.ai_request_log`，返回前端。

代表性查询只能由后端白名单生成，例如：

```sql
SELECT COALESCE(SUM(monthly_transaction_amount), 0) AS amount
FROM <catalog白名单schema>.monthly_sales
WHERE period_start = %s AND period_end = %s;
```

其中 Schema 必须来自 `catalog.py` 的固定映射，禁止直接使用用户或模型传入的 Schema 名称。

##### 前端具体实现

1. 在 `8.11/frontend/app/api.ts` 增加 `DashboardInsightData` 类型和 `api.dashboardInsight()`。
2. 在 `DashboardPage` 的 `/dashboard` 请求成功后调用洞察接口。
3. 在 `8.11/frontend/app/page.tsx` 新增 `AiInsightPanel`，展示结论、证据、风险、动作、数据日期和降级模式。
4. `scope_key`、`as_of`、`trend_grain` 或 `refund_grain` 变化时取消旧请求并重新生成。
5. 洞察接口失败只影响 `AiInsightPanel`，不能覆盖基础看板数据或跳转登录页。

每个经营看板顶部增加“AI 经营洞察”卡片。首次进入页面或范围、截止日期发生变化后，系统基于当前结构化看板数据生成摘要。

摘要固定包含：

1. **经营结论**：一句话说明当前整体表现。
2. **关键变化**：列出 2—4 个最重要的上升、下降或异常指标。
3. **主要驱动**：指出贡献较大或拖累明显的小组、店铺、客户、商品或退款因素。
4. **风险提示**：数据新鲜度、客户健康异常、退款异常或数据不足。
5. **建议动作**：最多 3 条可执行建议，每条标注建议对象和依据。

#### FR-AI-INSIGHT-002 结论证据

每条洞察应附带：

- 相关指标名称和数值。
- 当前周期和对比周期。
- 统计范围。
- 数据截止日期。
- “查看依据”入口，点击后滚动到对应模块或跳转到下钻页面。

#### FR-AI-INSIGHT-003 生成规则

- 关键数字由后端结构化工具返回，不由大模型自行计算。
- 结论生成前检查数据新鲜度、分母为零、样本过小和状态快照是否有效。
- 外部 AI 未配置时，仍返回确定性模板摘要，并在页面提示“当前为规则摘要”。
- AI 调用失败时保留基础看板数据，洞察区域单独显示失败和重试，不影响其他模块。
- 同一范围、日期和数据版本的摘要可缓存，减少重复调用。

#### FR-AI-INSIGHT-004 用户反馈

**数据库与实现：**调用 `POST /api/v1/ai/feedback`，后端使用当前 `DATABASE_URL` 连接 PostgreSQL `weidian`，向新建的 `public.ai_feedback` 插入 `request_id`、当前会话 `user_id`、`helpful`、`reason`、`comment` 和 `created_at`。前端不能直接写数据库，也不能提交其他用户 ID。`request_id` 必须已存在于 `public.ai_request_log`。

- 每次 AI 洞察提供“有帮助 / 没帮助”反馈入口。
- “没帮助”可选原因：结论不准确、缺少依据、建议不可执行、内容太泛、其他。
- 反馈用于质量统计，不自动修改业务数据。

**验收标准：**

- 洞察中的金额、数量和变化率与页面模块一致。
- 切换范围或日期后不得沿用旧摘要。
- AI 未配置时仍有可用的规则摘要。
- 权限范围外的数据不得出现在摘要中。

---

### 7.4 客户列表与客户详情

#### FR-CUSTOMER-001 客户列表

**状态：已有，二期补充筛选。**

- 支持按客户 ID 或昵称搜索。
- 支持分页，每页默认 20 条。
- 默认按当前半年销售额降序。
- 二期增加健康状态、店铺、销售额区间筛选，以及销售额、拿货次数、健康分排序。
- 列表中客户 ID 可进入独立详情页。

#### FR-CUSTOMER-002 客户详情

**状态：已有。**

- 展示客户 ID、昵称、店铺、健康分、健康状态、风险原因和建议动作。
- 展示日、周、月、季度、半年五个维度的销售额、拿货次数和主要商品。
- 显示统计截止日期。
- 无商品名称时明确展示商品编码，不得由 AI 猜测商品名称、品类、毛利或库存。

---

### 7.5 AI 客户助手

#### FR-AI-CUSTOMER-001 默认诊断

**状态：已有对话入口，一期增强。**

##### 数据库连接与具体取数

该功能仍连接 `DATABASE_URL` 指向的 PostgreSQL 数据库 `weidian`，但每次只能连接当前客户所属的一个店铺 Schema，不允许跨店拼接同名客户。

| 数据 | 表 | 过滤条件与字段 |
| --- | --- | --- |
| 客户身份 | `<store_schema>.customer_id_mapping` | `customer_id = %s`；读取店铺配置中的昵称字段 |
| 日销售 | `<store_schema>.customer_daily_sales` | `customer_id`、`transaction_date`、`transaction_amount` |
| 周销售 | `<store_schema>.customer_weekly_sales` | `customer_id`、周期、`weekly_transaction_amount`、`weekly_purchase_count` |
| 月销售 | `<store_schema>.customer_monthly_sales` | `customer_id`、周期、`monthly_transaction_amount`、`monthly_purchase_count` |
| 季度销售 | `<store_schema>.customer_quarterly_sales` | `customer_id`、周期、`quarterly_transaction_amount`、`quarterly_purchase_count` |
| 半年销售 | `<store_schema>.customer_half_year_sales` | `customer_id`、周期、`half_year_transaction_amount`、`half_year_purchase_count` |
| 客户商品 | `<store_schema>.customer_daily_product_sales`、`customer_monthly_product_sales`、`customer_quarterly_product_sales`、`customer_half_year_product_sales` | `customer_id`、`product_code`、数量、金额 |
| 客户健康 | `<store_schema>.customer_health_detail` | `customer_id`、`period_start <= as_of`；读取最新 `score/status/state_instructions/follow_up_action` |
| 生效规则 | `public.talent_customer_status_action`、`public.private_customer_status_action` 或 `public.distribution_customer_status_action` | 按客户所属组和健康状态读取 |
| 店铺退款背景 | `<store_schema>.weekly_refunds`、`monthly_refunds`、`quarterly_refunds`、`half_year_refunds` | 只允许说明店铺周期退款，不能写成客户本人退款 |

当前统一数据库没有 `customer_refunds` 表，因此一期不得实现“该客户退款了多少”。如果确实需要该功能，必须先针对九个平台建立统一客户退款派生表，并确认订单退款能够稳定关联到 `customer_id`。

##### 后端具体实现

接口保留现有对话接口，并新增默认诊断接口：

```text
POST /api/v1/ai/customer-analysis
POST /api/v1/ai/chat
```

默认诊断请求：

```json
{
  "store_key": "weidian",
  "customer_id": "客户ID",
  "as_of": "2026-08-11",
  "analysis_type": "overview"
}
```

后端执行顺序：

1. 使用 `allowed_stores(current_user.role)` 校验 `store_key`。
2. 使用现有 `CustomerRepository.get_customer()` 读取客户身份和健康快照。
3. 扩展 `CustomerService.detail()`：除当前周期外，再读取月、季度、半年的上一周期，用后端计算变化额和变化率。
4. 使用 `CustomerRepository.customer_products()` 读取当前月和半年 Top5 商品，并由后端计算 Top1/Top3 金额集中度。
5. 使用 `SettingsRepository.health_rules(group_key)` 读取当前生效健康规则。
6. 检查健康快照 `period_end` 是否早于销售截止日期；存在冲突时写入 `warnings[]`。
7. 构造 `customer_evidence[]`，至少包含本月/上月销售、半年销售、拿货次数、主要商品、健康分、状态和快照日期。
8. 调用模型增强内部经营诊断；模型不得获得其他客户数据，也不得生成面向客户的回复文本。
9. 未配置模型时，用确定性模板返回“销售表现 + 主要商品 + 健康规则 + 建议动作”。
10. 写入 `public.ai_request_log`；用户评价写入 `public.ai_feedback`。

##### 前端具体实现

1. 继续使用客户详情页右侧 `ai-panel`。
2. 客户详情加载完成后调用 `customerAnalysis()`，展示默认诊断。
3. 快捷问题统一携带当前 `store_key`、`customer_id`、`as_of`，前端不能只发送昵称。
4. 证据中的周期和数值以独立卡片展示，不从模型文字中正则提取。
5. 切换客户或返回列表时取消未完成请求，防止上一个客户的回答出现在新客户页面。

进入客户详情后，AI 助手默认生成客户诊断，包含：

- 客户当前健康状态及规则说明。
- 最近一月与当前半年销售、拿货表现。
- 与前一可比周期的变化。
- 主要商品及商品集中度。
- 风险原因或值得关注的异常。
- 建议跟进动作和优先级。

#### FR-AI-CUSTOMER-002 快捷问题

至少提供以下快捷入口：

- 最近表现
- 为什么是当前健康状态
- 主要商品
- 店铺退款情况（只能说明该客户所在店铺的周期汇总，当前不能归因到单个客户）
- 跟进建议
- 内部跟进建议

#### FR-AI-CUSTOMER-003 自由提问

- 用户可在当前客户上下文中连续提问。
- 对话上下文最多保留最近 10 轮有效消息，避免无限增长。
- 用户询问当前客户之外的数据时，系统提示使用“问看板”入口。
- 用户要求修改客户状态、联系客户或执行上传时，助手只提供内部业务说明，不执行操作。

#### FR-AI-CUSTOMER-004 内部跟进建议

内部跟进建议面向业务人员，必须明确展示：

- 跟进优先级：高、中、低。
- 触发依据：销售、拿货、健康状态、商品集中度或数据新鲜度。
- 核查事项：业务人员下一步应核对的数据或经营问题。

本项目不生成客户回复、沟通话术、营销文案或客服文本，也不连接外部消息平台。

#### FR-AI-CUSTOMER-005 回答结构

每次回答优先使用以下结构：

```text
结论
关键依据
建议动作
数据范围与截止日期
数据不足说明（如有）
```

**验收标准：**

- 回答中的客户、店铺、统计日期必须与当前详情页一致。
- 客户跨店铺同名时不得混用数据。
- AI 未配置时可返回结构化规则摘要，但要清楚标注模式。
- 风险原因和健康状态冲突时不得强行解释，必须提示数据快照可能不一致。

---

### 7.6 数据上传与 AI 影响解释

#### FR-UPLOAD-001 上传预检

**状态：已有。**

- 按账号权限展示可上传店铺。
- 支持 `.xlsx` 和 `.csv`，文件大小受后端配置限制。
- 上传分为“预览”和“确认写入”两步。
- 预览展示总行数、有效行、无效行、新增日期、已有日期、替换日期、跳过行、预计删除和写入行数。
- 展示销售、退款、预售分类及店铺、汇总范围的周期变化。
- 支持展示最多若干条行级错误，其余错误通过汇总说明体现。

#### FR-UPLOAD-002 AI 影响摘要

**状态：一期新增。**

##### 数据库连接与具体取数

AI 影响摘要不单独连接数据库执行新 SQL，而是复用现有上传预览已经从 PostgreSQL `weidian` 数据库取得的结构化结果。现有上传预览会根据店铺连接以下 Schema 和表：

| 店铺 | 主 Schema | 预览时读取 | 正式提交时写入及刷新 |
| --- | --- | --- | --- |
| 微店 | `weidian` | `raw_data`、`customer_id_mapping`、销售/退款/预售周期表 | `raw_data` + `customer_id_mapping` + 33 张派生表 + 3 张预售表，随后刷新 `daren`、`qudao` |
| 两家抖店 | `doudianChildren` / `doudianKocotree` | `raw_data`、`customer_id_mapping`、销售/退款周期表 | 对应店铺表，随后刷新 `doudian`、`daren`、`qudao` |
| 快手小店 | `kuaishouxiaodian` | 同上 | 店铺表，随后刷新 `daren`、`qudao` |
| 两家有赞店 | `qijian` / `muyinqijian` | 同上 | 对应店铺表，随后刷新 `youzan`、`siyu`、`qudao` |
| 快团团 | `kuaituantuan` | `raw_data`、业务键、客户映射和周期表 | 店铺表，随后刷新 `siyu`、`qudao` |
| 阿里巴巴 | `alibaba` | `raw_data`、客户映射和周期表 | 店铺表，随后刷新 `fenxiao`、`qudao` |
| 聚水潭 | `jushuitan` | 同上 | 店铺表，随后刷新 `fenxiao`、`qudao` |

AI 只使用预览结果中的这些字段：

```text
store_key
upload_strategy
total_rows / valid_rows / invalid_rows
rows_to_delete / rows_to_insert / update_rows / unchanged_rows
dates.file / dates.new / dates.existing / dates.replacement
business_preview.source_classification
business_preview.store_period_changes
business_preview.aggregate_period_changes
refresh.store_tables / refresh.aggregate_schemas / refresh.aggregate_tables
```

AI 不读取上传文件二进制、不直接查询 `raw_data`、不重新计算销售和退款金额，避免模型解释结果与正式预览不一致。

##### 后端具体实现

新增接口：

```text
POST /api/v1/ai/upload-explanation
```

请求参数：

```json
{
  "upload_id": "upl_xxx"
}
```

后端执行顺序：

1. 从当前登录会话取得用户角色和允许店铺。
2. 使用 `UploadService.task(upload_id, include_errors=True)` 读取当前上传预览任务。
3. 再次校验任务的 `store_key` 属于当前账号；主管可查看但不能提交，组长只能查看本组任务。
4. 新增 `build_upload_rules()`：用普通代码计算有效行率、金额绝对变化、退款变化、变化最大的周期和受影响 Schema 数量。
5. 规则命中“大额负变化、退款明显增加、有效行率过低、替换已有日期、无变化”等情况时写入 `warnings[]`。
6. 将预览摘要和 `warnings[]` 发送给模型转成业务解释。
7. 返回的 `can_commit` 必须直接复制原预览的 `commit_available`，模型输出不能改变该值。
8. 该接口代码中不导入任何 `committer.py`，从代码层保证 AI 解释接口无法执行提交。
9. 写入 `public.ai_request_log`，其中仅保存预览摘要和表名，不保存整份上传文件内容。

当前上传任务存放在进程内 `UploadService.TASKS`。如果后端使用多进程或需要重启后继续查看，必须先新增 `public.upload_task` 和 `public.upload_task_detail`；否则一期只能保证同一后端进程内解释当前预览。

##### 前端具体实现

1. `UploadCard` 在 `uploadPreview()` 成功并拿到 `preview.id` 后调用 `uploadExplanation(preview.id)`。
2. 在 `UploadBusinessPreview` 下方增加 `AiUploadExplanation`。
3. 展示“事实摘要、风险、需人工核对项”，并始终保留原始预览表。
4. AI 请求失败时不隐藏“确认写入数据库”按钮，也不改变预览状态。
5. 用户重新选择文件或重新预览后，清除旧解释并使用新的 `upload_id`。

预览完成后增加“AI 影响解读”，至少包含：

- 本次文件覆盖的店铺和日期范围。
- 新增、替换、跳过数据的规模。
- 对销售额、退款额、预售和汇总指标的主要影响。
- 变化最大的周期。
- 可能存在的异常：大额负向变化、退款重分类、日期断层、有效行比例过低、无数据变化。
- 是否建议业务人员继续人工核对；不得输出“自动通过”。

#### FR-UPLOAD-003 写入确认

- AI 摘要不改变 `commit_available` 的确定性判断。
- 用户必须手动点击确认写入。
- 任一写入或刷新步骤失败时整体回滚，并展示失败原因。
- 入库成功后显示原始数据变化、客户新增数、店铺表刷新数、汇总表刷新数和表级增删改数量。

**验收标准：**

- AI 描述与预览结构化数据一致。
- AI 服务不可用不影响预览和确认写入。
- 未登录、主管账号或跨组店铺不得提交上传。
- AI 不得调用写入接口。

---

### 7.7 全局“问看板”

#### FR-AI-QA-001 入口与上下文

**状态：二期增强。**

##### 数据库连接与指标表路由

问看板仍只连接 `DATABASE_URL` 指向的 PostgreSQL 数据库 `weidian`，不为 AI 建立第二个数据库连接。每次问题先转成指标 Key，再通过固定路由决定查询表：

| 指标 Key | 数据库 Schema | 表路由 | 允许维度 |
| --- | --- | --- | --- |
| `sales_amount` | `resolve_scope()` 返回的店铺 Schema | 日/周/月/季/半年对应 `*_sales` | 小组、平台、店铺、周期 |
| `sales_change_rate` | 同上 | 当前周期和 `previous_window()` 对应的 `*_sales` | 小组、平台、店铺 |
| `active_customer_count` | 同上 | 对应粒度 `customer_*_sales` | 小组、平台、店铺 |
| `customer_ranking` | 同上 | `customer_half_year_sales` + `customer_health_detail` + `customer_id_mapping` | 店铺、健康状态、客户 |
| `purchase_count` | 单店 Schema | 对应粒度 `customer_*_sales` | 客户、周期 |
| `top_product_amount` / `top_product_quantity` | 店铺 Schema | 对应粒度 `*_product_sales` | 店铺、商品、周期 |
| `customer_products` | 单店 Schema | `customer_*_product_sales` | 客户、商品、周期 |
| `refund_amount` | 店铺 Schema | `weekly_refunds`、`monthly_refunds`、`quarterly_refunds`、`half_year_refunds` | 小组、平台、店铺、周期 |
| `customer_health_count` | 店铺 Schema | `customer_weekly_sales` + `customer_health_detail` | 小组、店铺、健康状态 |
| `presale_amount` | 仅 `weidian` Schema | 三张 `*_product_presales` | 微店、商品、周期 |
| `data_freshness` | 店铺 Schema | `daily_sales.MAX(transaction_date)` | 店铺 |

禁止问看板读取：

- 任意店铺 `raw_data`。
- 用户上传的任意表名或字段名。
- 模型自行生成的 SQL。
- 没有进入指标目录的字段。
- 权限范围外的 Schema。

##### 后端具体实现

新增接口：

```text
POST /api/v1/ai/query
```

请求参数：

```json
{
  "question": "本月哪个店铺销售额下降最多？",
  "context": {
    "scope_key": "all",
    "as_of": "2026-08-11",
    "grain": "month"
  }
}
```

后端执行顺序：

1. 限制问题长度，例如最多 1,000 个字符。
2. 模型第一次调用只做意图解析，输出受 Pydantic 校验的 JSON：`metric_key`、`scope_key`、`grain`、`as_of`、`group_by`、`filters`、`limit`、`output_type`。
3. `metric_key` 必须存在于代码维护的指标目录；不存在则返回 `AI_QUERY_UNSUPPORTED`。
4. `scope_key` 必须经过 `resolve_scope(current_user.role, scope_key)`；模型无权决定权限。
5. 新建 `AiToolRegistry`，根据 `metric_key` 调用固定工具函数；工具函数内部复用 `DashboardRepository` 和 `CustomerRepository`。
6. 工具参数使用 SQL 参数绑定；Schema 仅从 `STORES[store_key].schema_name` 取得并使用 `psycopg.sql.Identifier`。
7. 每个工具设置结果上限：客户明细默认 20、最大 100；商品默认 5、最大 20；趋势默认最多 24 个周期。
8. `EvidenceValidator` 检查明细合计、变化率、日期范围和数据新鲜度。
9. 第二次模型调用只接收验证后的结果，负责生成文字；表格和图表数据直接来自工具结果。
10. 写入 `public.ai_request_log`，记录指标、工具、范围、耗时和状态。

建议新增文件：

```text
8.11/backend/app/ai_metric_catalog.py   # 指标到工具的固定目录
8.11/backend/app/ai_tools.py            # 只读工具
8.11/backend/app/ai_orchestrator.py     # 意图、权限、工具、验证、生成
8.11/backend/app/ai_audit.py            # 日志与反馈
```

##### 前端具体实现

1. 在 `api.ts` 增加 `AiQueryRequest`、`AiQueryResult` 和 `api.aiQuery()`。
2. 在 `page.tsx` 的应用外壳中增加全局 `AskDashboardDrawer`，使所有有登录态的页面都能打开。
3. 打开时自动带入当前 `scopeKey`、`asOf` 和 `grain`，并在抽屉顶部可见展示。
4. `answer` 只负责文字，`evidence` 渲染数字卡，`table` 渲染表格，`chart` 渲染折线或柱状图。
5. “在看板中查看”根据后端返回的 `target` 和 `filters` 更新现有页面状态，而不是把模型文字当作路由。
6. 401 统一返回登录页；403 显示无权限；422 显示支持的问题范围；502 只显示 AI 服务异常。

- 桌面端在页面右上角提供固定“问看板”按钮，打开右侧抽屉。
- 默认继承当前页面的范围、店铺、统计截止日期和时间粒度。
- 用户可在抽屉中查看并修改当前查询范围，但只能选择有权限的范围。

#### FR-AI-QA-002 支持的问题类型

二期首批问数范围只支持已登记指标和维度：

- 查询单一指标：“本月销售额是多少？”
- 周期对比：“本月比上月下降了多少？”
- 范围对比：“哪个小组半年销售额最高？”
- 趋势查询：“最近 6 个月销售趋势怎么样？”
- 客户查询：“列出半年销售额最高的 20 个风险客户。”
- 商品查询：“当前半年金额 Top5 商品是什么？”
- 退款查询：“本季度哪个店铺退款额最高？”
- 解释型问题：“本月销售下降主要来自哪些店铺？”

暂不支持：

- 任意 SQL。
- 未登记指标的自由计算。
- 预测销售额、库存或利润。
- 对数据库执行新增、修改、删除。
- 生成或直接发送任何面向客户的消息。

#### FR-AI-QA-003 受控查询流程

系统必须按以下顺序执行：

1. 识别意图、指标、范围、时间、维度和输出形式。
2. 校验指标是否在白名单中。
3. 校验范围是否属于当前账号权限。
4. 调用确定性业务工具，不向模型暴露数据库连接和任意 SQL 能力。
5. 对返回结果执行合计、口径、日期和空值校验。
6. 生成文字、表格或图表，并附数据依据。

#### FR-AI-QA-004 澄清与拒答

- 缺少时间且当前页面有明确时间时，沿用页面时间。
- 缺少范围且当前页面有明确范围时，沿用页面范围。
- “最近”“表现好”“重点客户”等词无法唯一映射时，应展示实际采用的定义。
- 问题超出指标白名单时，说明当前支持的指标范围并给出可改问的示例。
- 查询结果为空时说明范围和时间，不生成虚构原因。

#### FR-AI-QA-005 输出形式

回答支持：

- 简短结论。
- 关键数字卡片。
- 明细表格，默认最多 20 行。
- 趋势折线图或范围对比柱状图。
- 数据范围、截止日期、指标口径和查询依据。
- “在看板中查看”按钮，将问题转成页面筛选或定位到对应模块。

**验收标准：**

- 相同范围、日期和指标的问数结果与看板展示一致。
- 任意问题均不能返回无权限店铺或客户的数据。
- 明细超过上限时必须分页或提示缩小范围。
- 生成图表时，图表数据与回答表格使用同一结果集。

---

### 7.8 健康规则设置

#### FR-RULE-001 规则查看与编辑

**状态：已有。**

- 健康状态固定为高活跃、活跃、稳定、观察、风险、流失预警、流失七类。
- 主管只读查看三个小组规则。
- 组长只能编辑本组的状态说明和建议跟进动作。
- 保存前展示变更项；保存后展示受影响状态和更新行数。

#### FR-RULE-002 AI 使用规则

- AI 解释客户健康状态时，必须读取当前生效规则，而不是使用模型内置常识。
- AI 回答必须区分“规则定义”和“客户实际数据”。
- 客户健康快照日期与销售截止日期不一致时显示提示。

---

### 7.9 AI 设置

#### FR-SETTING-001 分角色配置

**状态：已有。**

- 四个角色分别配置 `base_url`、`api_key`、`model_name`。
- 配置相互隔离，组长不能读取或修改其他角色配置。
- `api_key` 保存后只返回掩码。
- 支持先测试连接再保存。

#### FR-SETTING-002 配置状态

- 页面区分未配置、配置不完整、连接测试成功、连接测试失败、已保存五种状态。
- 未配置时，AI 功能使用确定性规则摘要，并明确标注非大模型模式。
- 配置更新后，新请求使用新配置；正在进行的请求不强制中断。

---

### 7.10 AI 记录、反馈与审计

#### FR-AUDIT-001 调用记录

**状态：一期新增。**

##### 数据库连接和新增表

本功能连接同一个 PostgreSQL 数据库 `weidian`，在 `public` Schema 新建两张表。建议迁移文件：

```text
8.11/backend/migrations/004_ai_request_log.sql
```

表一：`public.ai_request_log`。

```text
id                uuid/text 主键
request_id        text 唯一，对应 HTTP X-Request-ID
user_id           text
role              text
feature_type      text  # dashboard_insight/customer/upload/query
scope_key         text
store_keys        jsonb
as_of             date
tool_calls        jsonb
evidence          jsonb
model_name        text
mode              text  # ai/rule_summary
status            text  # success/failed/timeout
duration_ms       integer
input_tokens      integer，可空
output_tokens     integer，可空
error_code        text，可空
created_at        timestamptz
```

建议索引：

```text
UNIQUE(request_id)
INDEX(created_at DESC)
INDEX(user_id, created_at DESC)
INDEX(feature_type, status, created_at DESC)
```

表二：`public.ai_feedback`。

```text
id          uuid/text 主键
request_id  text，外键关联 ai_request_log.request_id
user_id     text
helpful     boolean
reason      text，可空
comment     text，可空
created_at  timestamptz
```

AI 日志只能写这两张新表，不能写九个店铺 Schema 的任何业务表。

##### 具体实现

1. 新增 `AiAuditRepository`，使用当前请求已经取得的数据库连接写日志。
2. AI 请求开始时记录计时；完成、降级、超时或失败后统一调用 `finish_request()`。
3. `tool_calls` 只保存工具名和脱敏参数，不保存 `DATABASE_URL`、API Key、完整提示词或上传文件。
4. `evidence` 只保存回答使用的关键指标和日期；客户昵称等非必要字段不保存。
5. 新增 `POST /api/v1/ai/feedback`，后端从会话取得 `user_id`，不能使用前端传入的其他用户 ID。
6. 反馈接口先确认 `request_id` 存在且当前用户有权反馈，再插入 `ai_feedback`。
7. AI 日志写入失败不能导致基础看板失败；但应记录服务日志并返回原 AI 结果。
8. 数据保留周期在业务未确认前建议为 90 天，定期清理只清理 AI 日志，不清理业务数据。

每次 AI 请求记录以下信息，但不得记录明文 API Key：

- 请求 ID、时间、用户 ID、角色。
- 功能类型：经营洞察、客户助手、上传解释、问看板。
- 数据范围、店铺、统计日期。
- 调用的工具名称和参数摘要。
- 模型名称、执行状态、耗时、输入输出字符数或 Token 数（供应商可返回时）。
- 使用的数据版本或数据最新日期。
- 错误代码和用户反馈。

#### FR-AUDIT-002 内容留存

- 默认不长期保存完整客户对话正文；如业务需要留存，应另行确认保存周期和访问权限。
- 日志中的客户 ID 可按现有业务需求保留，客户昵称和其他敏感字段应尽量最小化。
- 提供按请求 ID 定位问题的能力。

---

### 7.11 多智能体协作

#### FR-AGENT-001 智能体组成

**状态：三期规划，不进入 MVP。**

##### 数据库连接与实现边界

多智能体不建立新的业务数据库，也不允许每个 Agent 自己连接 PostgreSQL。所有 Agent 只能通过二期已经验证的 `AiToolRegistry` 调用后端工具：

| Agent | 间接读取的 Schema / 表 | 禁止行为 |
| --- | --- | --- |
| 经营分析 Agent | 九个店铺 Schema 的 `*_sales`、`*_product_sales` | 直接 SQL、读取 `raw_data` |
| 客户 Agent | 单店 `customer_*_sales`、`customer_*_product_sales`、`customer_health_detail`、`customer_id_mapping` | 跨店搜索同名客户、修改客户状态 |
| 退款 Agent | 店铺 `weekly/monthly/quarterly/half_year_refunds` | 将店铺退款归因给单客户 |
| 数据质量 Agent | 店铺 `daily_sales` 最新日期、健康快照日期、工具返回的覆盖信息 | 修改或补齐业务数据 |
| 验证 Agent | 只接收其他工具已经返回的 `evidence` | 再次查询任意表或改写证据 |
| 协调 Agent | 不连接数据库 | 决定权限、执行工具之外的操作 |

具体实现步骤：

1. `/api/v1/ai/query` 判断问题是否同时涉及两个以上专题；简单问题仍由单一编排器完成。
2. 协调器把问题拆成结构化子任务，例如“销售变化”“退款贡献”“客户风险”。
3. 每个子任务携带同一个已经校验过的 `scope_key`、`store_keys` 和 `as_of`。
4. 专项 Agent 调用固定只读工具，返回 `facts[]`、`evidence[]`、`warnings[]`，不返回自由 SQL。
5. 验证器检查各子任务日期和范围一致、金额能够核对后，协调器才合并文字答案。
6. 全部子调用以同一个父 `request_id` 写入 `public.ai_request_log.tool_calls`，不为每个 Agent 新建业务表。
7. 任一子任务失败时只返回已验证部分，并标注未完成专题。

在受控工具和审计机制成熟后，可增加以下专项智能体：

| 智能体 | 职责 | 允许调用的工具 |
| --- | --- | --- |
| 经营分析 Agent | 汇总整体表现、识别主要驱动 | 销售、范围对比、商品工具 |
| 客户 Agent | 分析客户、生成跟进建议 | 客户详情、客户商品、健康规则工具 |
| 退款 Agent | 分析退款变化与店铺贡献 | 退款分析工具 |
| 数据质量 Agent | 检查新鲜度、缺失、快照冲突 | 数据质量与元数据工具 |
| 验证 Agent | 核对数字、范围、日期和结论依据 | 只读验证工具 |
| 协调 Agent | 拆解问题、分配任务、合并答案 | 不直接访问数据库 |

#### FR-AGENT-002 编排原则

- 只有复杂跨主题问题才触发多个 Agent。
- 权限校验由确定性后端代码完成，不交给 Agent 决定。
- Agent 之间传递结构化结果和证据，不传递数据库账号。
- 最终答案必须通过验证 Agent 或统一验证器检查。
- 任何一个 Agent 失败时，系统应返回已完成部分和失败说明，不伪装成完整结果。

---

## 8. AI 业务架构要求

### 8.1 总体架构

```text
前端看板 / 客户详情 / 上传页 / 问看板
                    │
                    ▼
            登录会话与权限校验
                    │
                    ▼
              AI 编排服务
        ┌───────────┼───────────┐
        ▼           ▼           ▼
     意图识别    指标语义层    工具路由
                                │
          ┌──────────┬──────────┼──────────┐
          ▼          ▼          ▼          ▼
       销售工具   客户工具   退款工具   上传影响工具
          └──────────┴──────────┴──────────┘
                                │
                                ▼
                    证据校验与结构化输出
                                │
                                ▼
                     大模型生成解释与建议
```

### 8.2 白名单工具

建议优先提供以下只读工具：

| 工具 | 用途 | 关键参数 |
| --- | --- | --- |
| `get_dashboard_snapshot` | 获取当前看板完整快照 | `scope_key`, `as_of` |
| `get_sales_comparison` | 获取销售额、趋势和周期对比 | `scope_key`, `grain`, `as_of` |
| `get_scope_contribution` | 获取小组或店铺贡献及变化 | `scope_key`, `dimension`, `grain`, `as_of` |
| `get_customer_profile` | 获取单客户基础、健康和多周期销售 | `store_key`, `customer_id`, `as_of` |
| `get_customer_products` | 获取客户主要商品 | `store_key`, `customer_id`, `grain`, `as_of` |
| `get_customer_ranking` | 获取筛选后的客户排名 | `scope_key`, `filters`, `sort`, `limit` |
| `get_refund_analysis` | 获取退款本期、上期、趋势和贡献 | `scope_key`, `grain`, `as_of` |
| `get_upload_impact` | 获取上传预览或写入结果 | `upload_id` |
| `get_data_freshness` | 获取各店铺最新业务日期和缺口 | `scope_key` |
| `run_approved_metric` | 执行指标目录中已批准的查询 | `metric_key`, `filters`, `group_by` |

### 8.3 禁止能力

- 不向模型提供数据库连接字符串。
- 不提供任意 SQL 执行工具。
- 不允许模型选择任意 Schema 或表名。
- 不允许 AI 工具执行 `INSERT`、`UPDATE`、`DELETE`、DDL 或文件提交。
- 不允许前端传入角色覆盖后端会话角色。

---

## 9. 指标语义层

### 9.1 目标

将现有代码中的销售、客户、商品、退款表映射扩展为统一指标目录，使看板、AI 摘要、问数和验收使用同一口径。

### 9.2 指标定义字段

每个指标至少包含：

| 字段 | 说明 |
| --- | --- |
| `metric_key` | 稳定唯一标识 |
| `label` | 页面中文名称 |
| `description` | 业务含义 |
| `source_spec` | 对应仓储或服务查询定义 |
| `date_field` | 统计日期字段 |
| `value_field` | 金额、数量或分数字段 |
| `aggregation` | SUM、COUNT DISTINCT、AVG 等 |
| `supported_grains` | 支持日、周、月、季、半年中的哪些粒度 |
| `allowed_dimensions` | 小组、平台、店铺、客户、商品等允许维度 |
| `comparison_rule` | 同比、环比或上一周期定义 |
| `null_rule` | 空值和分母为零处理 |
| `permission_scope` | 可访问角色与范围 |
| `freshness_rule` | 数据完整日期和延迟规则 |
| `display_format` | 金额、整数、比例等格式 |

### 9.3 首批指标目录

| 指标 Key | 名称 | 类型 | 主要维度 |
| --- | --- | --- | --- |
| `sales_amount` | 销售额 | 核心结果 | 小组、平台、店铺、客户、商品、周期 |
| `sales_change_rate` | 销售额变化率 | 变化 | 范围、周期 |
| `active_customer_count` | 有销售客户数 | 规模 | 小组、平台、店铺、周期 |
| `purchase_count` | 拿货次数 | 深度 | 店铺、客户、周期 |
| `product_count` | 有销售商品数 | 商品结构 | 小组、平台、店铺、周期 |
| `top_product_amount` | 商品销售额 Top | 商品结构 | 范围、商品、周期 |
| `top_product_quantity` | 商品数量 Top | 商品结构 | 范围、商品、周期 |
| `refund_amount` | 退款额 | 风险 | 小组、平台、店铺、周期 |
| `refund_change_rate` | 退款额变化率 | 风险变化 | 范围、周期 |
| `customer_health_count` | 各健康状态客户数 | 客户质量 | 小组、店铺、状态、快照日期 |
| `healthy_customer_ratio` | 健康客户占比 | 客户质量 | 小组、店铺、快照日期 |
| `presale_amount` | 预售交易额 | 补充指标 | 支持预售的店铺、商品、周期 |

### 9.4 口径约束

- 金额统一使用数据库确定性聚合结果，展示时保留两位小数。
- 变化率为 `(本期 - 上期) / 上期`；上期为 0 时返回空值。
- 健康客户默认指高活跃、活跃、稳定三类之和。
- 商品名称、类目、库存、毛利当前并非稳定数据字段，AI 只能使用商品编码和已有数量、金额。
- 多店铺对比必须同时展示或说明各店铺数据截止日期。

---

## 10. 数据质量与可信度要求

### 10.1 数据新鲜度

- 每个 AI 输出显示“数据截至 YYYY-MM-DD”。
- 多店铺范围展示每个店铺最新日期和范围内完整截止日期。
- 店铺数据延迟超过推荐阈值时，AI 洞察顶部展示警告。
- 阈值默认建议为 1 天，最终值需业务确认。

### 10.2 健康状态一致性

已发现部分店铺健康状态快照与当前销售周期可能不一致。上线 AI 健康解释前必须：

1. 确认健康表使用的快照日期字段。
2. 确认健康评分覆盖的是自然周还是业务半年。
3. 校验“当前有销售但健康状态为流失”等冲突。
4. 冲突未修复时，AI 只描述原始状态并展示风险提示，不推导原因。

### 10.3 上传数据质量

- 预览阶段必须区分格式错误、字段缺失、无日期、无效业务值、重复业务键和规则不支持。
- AI 只能解释预检结果，不能隐藏或改写原始错误。
- 写入前后表级数量、周期金额和汇总金额应可核对。

### 10.4 回答验证

AI 输出前至少检查：

- 权限范围是否正确。
- `scope_key`、店铺和客户是否一致。
- 时间粒度和截止日期是否一致。
- 卡片、表格、图表和文字中的数字是否一致。
- 合计与明细是否可解释。
- 数据为空或不完整时是否已明确提示。

---

## 11. 接口需求建议

现有接口保持兼容，在此基础上新增 AI 智能看板接口。

### 11.1 已有接口

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| POST | `/api/v1/auth/login` | 登录 |
| GET | `/api/v1/auth/session` | 恢复会话 |
| POST | `/api/v1/auth/logout` | 退出 |
| GET | `/api/v1/meta/options` | 获取权限范围、店铺、粒度和上传限制 |
| GET | `/api/v1/dashboard` | 获取看板数据 |
| GET | `/api/v1/customers` | 获取客户列表 |
| GET | `/api/v1/customers/{store_key}/{customer_id}` | 获取客户详情 |
| POST | `/api/v1/uploads/sales` | 上传预览或确认入库 |
| GET/PUT | `/api/v1/settings/health-rules` | 健康规则查看或编辑 |
| GET/PUT | `/api/v1/settings/ai` | AI 配置查看或保存 |
| POST | `/api/v1/settings/ai/test` | 测试 AI 连接 |
| POST | `/api/v1/ai/chat` | 当前客户问答 |

### 11.2 建议新增接口

| 方法 | 路径 | 用途 | 阶段 |
| --- | --- | --- | --- |
| POST | `/api/v1/ai/dashboard-insight` | 生成当前看板经营洞察 | 一期 |
| POST | `/api/v1/ai/customer-analysis` | 生成客户默认诊断或专题分析 | 一期 |
| POST | `/api/v1/ai/upload-explanation` | 解释上传预览或写入结果 | 一期 |
| POST | `/api/v1/ai/query` | 受控自然语言问数 | 二期 |
| POST | `/api/v1/ai/feedback` | 保存 AI 反馈 | 一期 |
| GET | `/api/v1/ai/requests/{request_id}` | 查询请求状态及证据摘要 | 二期 |

### 11.3 AI 统一返回结构

```json
{
  "request_id": "uuid",
  "mode": "ai | rule_summary",
  "answer": "文字结论",
  "scope": {
    "scope_key": "talent",
    "store_keys": ["weidian"],
    "as_of": "2026-08-11"
  },
  "evidence": [
    {
      "metric_key": "sales_amount",
      "label": "本月销售额",
      "value": "100000.00",
      "period": "2026-08-01 至 2026-08-11"
    }
  ],
  "actions": [
    {
      "label": "查看风险客户",
      "target": "customer_list",
      "filters": {"status": "风险"}
    }
  ],
  "warnings": [],
  "generated_at": "2026-08-14T10:00:00+08:00"
}
```

### 11.4 错误处理

| 错误码 | 场景 | 前端处理 |
| --- | --- | --- |
| `AUTH_REQUIRED` | 未登录或会话过期 | 清除本地登录态并回登录页 |
| `SCOPE_FORBIDDEN` | 无权访问范围 | 显示无权限，不清除登录态 |
| `AI_CONFIG_INCOMPLETE` | AI 配置不完整 | 提示前往设置或使用规则摘要 |
| `AI_PROVIDER_ERROR` | 外部模型调用失败 | 保留页面数据，支持重试 |
| `AI_QUERY_UNSUPPORTED` | 问题超出白名单 | 展示支持范围和改问示例 |
| `DATA_INCOMPLETE` | 数据不完整 | 展示警告并说明影响 |
| `DATA_NOT_FOUND` | 范围内无数据 | 展示空状态，不生成结论 |

---

## 12. 页面与交互要求

### 12.1 AI 经营洞察卡片

- 位于页面标题和基础 KPI 之间。
- 默认展开“一句话结论 + 关键变化 + 建议动作”，证据详情可折叠。
- 切换范围或日期时显示重新分析状态。
- 生成期间不阻塞基础看板加载。
- 提供刷新、复制、反馈和查看依据操作。

### 12.2 AI 客户助手

- 保持客户详情页右侧布局。
- 顶部固定展示当前客户、店铺、状态和数据日期。
- 对话区域与输入框独立滚动。
- 移动端改为客户数据下方的完整模块，不使用过窄双栏。

### 12.3 问看板抽屉

- 桌面端宽度建议为视口的 36%—42%，最小宽度 440px。
- 顶部展示当前范围和日期。
- 回答中的表格支持横向滚动，图表支持悬停查看数值。
- 提供示例问题和最近问题，但不默认保存长期对话。

### 12.4 可访问性

- 所有按钮提供明确中文可访问名称。
- 颜色不能作为健康或风险状态的唯一表达，必须配合文字。
- AI 生成、失败和完成状态应被屏幕阅读器识别。
- 键盘可完成打开、提问、查看证据和关闭抽屉等操作。

---

## 13. 非功能需求

### 13.1 性能

- 基础看板接口在正常数据库负载下 P95 响应时间目标不超过 3 秒。
- AI 首次可见反馈不超过 1 秒，应先显示“正在分析”而非空白。
- AI 完整回答目标 P95 不超过 15 秒；超过时展示持续状态和取消入口。
- 客户列表默认单页 20 条；问数明细默认最多 20 条，最大不超过 100 条。
- 对同一用户、范围、日期和数据版本的 AI 经营摘要可进行短期缓存。

### 13.2 可用性

- 外部 AI 服务不可用时，基础看板、客户数据、上传预览和入库必须继续可用。
- AI 功能失败不得造成整页错误。
- 所有长耗时请求支持超时和重试，但写入操作不得自动重试。

### 13.3 安全

- API Key 不进入前端日志、浏览器存储、错误正文和 AI 审计日志。
- 所有外部 AI 请求只发送回答所需的最小数据。
- 不向模型发送数据库连接信息、账号密码和无关客户数据。
- 对用户输入做长度限制和基础提示注入防护；模型提示中的指令不能覆盖后端权限和工具白名单。
- AI 返回内容按普通文本或安全 Markdown 渲染，禁止执行脚本。

### 13.4 可观测性

- 每个前后端请求携带请求 ID。
- 监控 AI 成功率、超时率、平均耗时、规则摘要降级率和用户反馈。
- 监控各店铺数据最新日期及健康快照一致性。
- 记录工具级错误，能够区分数据库错误、权限错误、模型错误和数据不足。

### 13.5 兼容性

- 支持主流桌面浏览器最新两个稳定版本。
- 核心看板和 AI 客户助手适配平板与手机宽度。
- 保持现有 Next.js 前端和 FastAPI 后端接口风格，不在一期引入独立复杂运行平台。

---

## 14. 埋点与效果指标

### 14.1 使用指标

| 指标 | 定义 |
| --- | --- |
| AI 洞察曝光率 | 打开看板后成功展示洞察的会话数 / 看板会话数 |
| AI 洞察查看依据率 | 点击查看依据的洞察次数 / 洞察曝光次数 |
| 客户助手使用率 | 使用客户 AI 的详情页会话数 / 客户详情会话数 |
| 问数成功率 | 返回有效结构化答案的问题数 / 总问题数 |
| 建议动作点击率 | 点击 AI 建议下钻入口次数 / 展示建议动作次数 |
| 上传解释使用率 | 查看 AI 上传影响解读的预览次数 / 上传预览次数 |

### 14.2 质量指标

| 指标 | 目标方向 |
| --- | --- |
| 数字一致率 | AI 证据数字与页面/接口结果一致，目标 100% |
| 权限泄漏事件 | 目标 0 |
| 有帮助反馈率 | 持续提升，一期上线后建立基线 |
| AI 调用成功率 | 目标不低于 95%，不含主动降级 |
| 无依据结论率 | 目标 0 |
| P95 AI 响应时长 | 不超过 15 秒 |

---

## 15. 分阶段建设范围

### 15.1 一期：AI 智能看板 MVP

目标：在不改变现有数据查询主链路的前提下，让看板、客户详情和上传页具备可靠的 AI 解释能力。

必须完成：

1. 统一首批指标定义和数据日期规则。
2. AI 经营洞察卡片。
3. AI 客户经营诊断、风险解释和内部跟进建议。
4. AI 上传影响解释。
5. 外部 AI 未配置或失败时的规则摘要降级。
6. AI 证据结构、请求日志和用户反馈。
7. 健康状态与销售日期冲突提示。

不包含：全局自由问数、多 Agent、预测、自动执行操作。

### 15.2 二期：受控自然语言问数

目标：让用户在权限范围内用自然语言查询已批准的经营指标。

必须完成：

1. 指标语义层和指标白名单。
2. 全局问看板抽屉。
3. 意图识别、权限校验和工具路由。
4. 表格、图表、摘要和看板下钻。
5. 查询结果验证、成本限制和完整审计。

### 15.3 三期：轻量多智能体

目标：处理跨销售、客户、退款和数据质量的复杂分析问题。

进入条件：

- 二期问数结果稳定。
- 主要指标均有统一语义定义。
- AI 权限、审计、证据和验证机制已上线。
- 已积累足够真实问题，可证明单助手存在明显瓶颈。

---

## 16. 研发拆分建议

### 16.1 后端

- 建立指标目录和 AI 白名单工具层。
- 为经营洞察、客户分析和上传解释提供结构化上下文。
- 增加统一 AI 编排、降级、超时、日志和反馈服务。
- 为 AI 结果增加证据、范围、数据日期和警告字段。
- 增加健康快照与销售日期一致性检查。

### 16.2 前端

- 新增 AI 经营洞察卡片及状态管理。
- 增强客户助手快捷问题、证据和建议动作展示。
- 在上传预览后展示 AI 影响解释。
- 二期新增问看板抽屉、表格/图表结果和页面下钻。
- 统一处理 401、403、业务错误和 AI 独立错误，避免全部错误被显示为“请先登录”。

### 16.3 数据

- 确认九个店铺的最新完整业务日期规则。
- 统一销售、客户、商品、退款和预售指标口径。
- 修复或解释健康状态快照与销售周期冲突。
- 补充商品名称、类目、库存、毛利等数据前，不开放相关 AI 问题。

### 16.4 测试

- 建立确定性指标回归用例。
- 建立角色、范围、店铺和客户权限矩阵。
- 为 AI 准备标准问题集、期望证据和拒答问题集。
- 验证 AI 服务失败时基础业务不受影响。
- 验证提示注入、超长输入、跨权限询问和虚构字段等异常场景。

---

## 17. 核心验收场景

| 编号 | 场景 | 预期结果 |
| --- | --- | --- |
| AC-001 | 主管登录进入全局看板 | 展示全部有权范围及 AI 经营洞察，数字与看板一致 |
| AC-002 | 组长尝试访问其他小组 AI 摘要 | 后端返回 403，AI 不生成答案 |
| AC-003 | AI 未配置 | 看板、客户和上传功能正常，AI 返回规则摘要并标注模式 |
| AC-004 | 切换店铺或日期 | 原摘要失效，新摘要使用新范围和日期 |
| AC-005 | 客户健康与销售快照冲突 | AI 明确提示冲突，不猜测风险原因 |
| AC-006 | 上传文件包含替换日期 | 预览和 AI 解读均说明替换范围、金额影响和核对建议 |
| AC-007 | 用户问“本月哪个店铺销售最高” | 返回权限范围内排名、数值、日期和指标口径 |
| AC-008 | 用户要求查询无权店铺 | 明确拒绝，不泄漏店铺明细或聚合数字 |
| AC-009 | 用户要求执行 SQL 或删除数据 | 明确拒绝并说明只支持已批准的只读指标查询 |
| AC-010 | 外部 AI 超时 | AI 区域显示失败或降级，基础页面不崩溃 |
| AC-011 | 问数结果生成图表 | 图表、表格和文字使用相同结果集并可核对 |
| AC-012 | 用户上传后不点击确认 | 数据库不发生写入，AI 不得自动确认 |

---

## 18. 风险、依赖与待确认项

### 18.1 当前关键风险

1. 四个角色当前尚未完成可用的外部 AI 模型配置，AI 真正调用前需要配置并测试。
2. 九个店铺最新业务日期不同，汇总页面必须先确认可比截止日期规则。
3. 部分店铺健康数据存在“当前仍有销售但状态集中为流失”等一致性风险。
4. 商品目前主要只有编码、数量和金额，无法可靠回答品类、库存、毛利和商品名称问题。
5. 当前缺少完整的 AI 请求审计、证据留存、用户反馈和成本监控。
6. 任意自然语言转 SQL 风险较高，不应作为一期实现方式。

### 18.2 需要业务确认

| 编号 | 待确认问题 | 建议默认方案 |
| --- | --- | --- |
| TBD-001 | 多店铺汇总的默认截止日期 | 使用范围内最小最新日期，优先保证可比性 |
| TBD-002 | 数据延迟多少天触发警告 | 默认超过 1 天触发 |
| TBD-003 | AI 对话正文是否留存 | 默认不长期保存，只保留请求元数据和反馈 |
| TBD-005 | AI 洞察默认自动生成还是点击生成 | 经营看板自动生成，客户详细问答按需调用 |
| TBD-006 | 问数明细最大导出范围 | 二期默认页面最多 100 条，暂不提供 AI 直接导出 |
| TBD-007 | 健康状态解释使用哪个快照口径 | 由业务确认自然周或业务半年后固化 |

---

## 19. 参考项目与采用原则

本方案参考以下开源项目的产品思想，但不直接整体迁入现有工程：

| 项目 | 可借鉴能力 | 本项目采用方式 |
| --- | --- | --- |
| [Chat2DB](https://github.com/OtterMind/Chat2DB) | AI SQL 生成、解释、图表和多数据源交互 | 借鉴问数交互，不开放任意 SQL |
| [Vanna](https://github.com/vanna-ai/vanna) | 自然语言到 SQL、表格、图表和摘要；用户权限感知 | 借鉴答案呈现和权限上下文；注意仓库已归档风险 |
| [PandasAI](https://github.com/sinaptik-ai/pandas-ai) | 自然语言数据分析和图表 | 借鉴分析体验，不在生产环境执行无约束代码 |
| [DB-GPT](https://github.com/eosphoros-ai/DB-GPT) | 数据 Agent、工作流、报表和多模型 | 借鉴工具化与任务编排，不一期引入完整平台 |
| [WrenAI](https://github.com/Canner/WrenAI) | 语义层、受控 Text-to-SQL、可治理指标 | 重点借鉴指标语义层和查询治理 |
| [OpenAI Swarm](https://github.com/openai/swarm) | Agent 与 handoff 的轻量协作模式 | 仅作为三期多 Agent 设计参考；生产实现需采用受维护的编排方案 |

综合采用原则：

- 产品体验参考 Vanna 的“问题—表格—图表—摘要”链路。
- 数据治理重点参考 WrenAI 的语义层思想。
- 数据工具和复杂任务拆分参考 DB-GPT。
- 多 Agent 只借鉴 Swarm 的职责划分和交接思想，不把实验性框架作为一期依赖。

---

## 20. 结论

本项目最适合的 AI 化方向不是让大模型自由读取全部数据库，而是在现有看板和服务层之上增加“受控 GenBI + 专项分析助手”：

1. 先统一指标、日期和权限。
2. 再完成经营摘要、客户诊断和上传解释三个高频、低风险功能。
3. 然后建设基于指标白名单和确定性工具的自然语言问数。
4. 最后根据真实复杂问题决定是否引入多智能体。

这一顺序能够复用当前工程的看板、客户、上传和 AI 配置能力，较快形成可用结果，同时控制数字幻觉、越权访问、任意 SQL 和复杂架构带来的风险。

---

## 21. 功能、数据库与实现明细

本章将前文功能逐项对应到当前项目的真实数据源和实现路径。除外部大模型接口外，所有业务数据继续使用当前 PostgreSQL 实例，不新增第二套业务数据库。

### 21.1 当前数据库全景

#### 21.1.1 数据库实例

| 项目 | 当前值 | 用途 |
| --- | --- | --- |
| 数据库类型 | PostgreSQL | 存储订单原始数据、销售、客户、商品、退款、健康度和各级汇总 |
| 数据库名称 | `weidian` | 当前后端 `DATABASE_URL` 连接的业务数据库 |
| 连接位置 | 项目根目录 `.env` 中的 `DATABASE_URL` | 只由后端读取，不能返回前端或发送给大模型 |
| 数据访问层 | `8.11/backend/app/repositories.py` | 当前看板与客户查询的确定性 SQL |
| 店铺与权限目录 | `8.11/backend/app/catalog.py` | 将角色、范围、店铺和 Schema 建立白名单映射 |

#### 21.1.2 九个店铺 Schema

| 业务组 | 店铺 Key | 页面名称 | PostgreSQL Schema |
| --- | --- | --- | --- |
| 达人组 | `weidian` | 微店 | `weidian` |
| 达人组 | `doudian_children` | 儿童服饰旗舰店 | `doudianChildren` |
| 达人组 | `doudian_kocotree` | Kocotree 服饰配件店 | `doudianKocotree` |
| 达人组 | `kuaishou` | 快手小店 | `kuaishouxiaodian` |
| 私域组 | `youzan_qijian` | 有赞旗舰店 | `qijian` |
| 私域组 | `youzan_muying` | 母婴旗舰店 | `muyinqijian` |
| 私域组 | `kuaituantuan` | 快团团 | `kuaituantuan` |
| 分销组 | `alibaba` | 阿里巴巴 | `alibaba` |
| 分销组 | `jushuitan` | 聚水潭 | `jushuitan` |

以上九个 Schema 是当前看板和客户查询的主要事实来源。它们采用基本一致的表名，使后端可以通过店铺白名单切换 Schema，并复用同一套查询逻辑。

#### 21.1.3 汇总与规则 Schema

| 层级 | Schema | 数据范围 | 主要用途 |
| --- | --- | --- | --- |
| 公共规则 | `public` | 全系统 | 三个业务组的客户健康状态说明和跟进动作 |
| 平台汇总 | `doudian` | 两家抖店 | 抖店销售、退款、客户健康和高频商品汇总 |
| 平台汇总 | `youzan` | 两家有赞店 | 有赞销售、退款、客户健康和高频商品汇总 |
| 小组汇总 | `daren` | 达人组 | 达人组销售、退款、健康和高频商品汇总 |
| 小组汇总 | `siyu` | 私域组 | 私域组销售、退款、健康和高频商品汇总 |
| 小组汇总 | `fenxiao` | 分销组 | 分销组销售、退款、健康和高频商品汇总 |
| 渠道汇总 | `qudao` | 全部业务 | 全渠道销售和退款汇总 |

当前看板的 `DashboardRepository` 直接汇总九个店铺 Schema，保证单店、跨店和客户明细使用同一事实来源；上述平台、小组和渠道汇总表主要由上传链路联动刷新，可用于结果核对和后续性能优化，但不能与店铺事实表混用后造成口径不一致。

### 21.2 店铺 Schema 的通用表族

#### 21.2.1 原始数据与客户映射

| 表名 | 用途 | 主要使用功能 |
| --- | --- | --- |
| `raw_data` | 保存各平台上传的原始订单或商品明细 | 上传预览、差异比较、正式入库和派生表刷新 |
| `customer_id_mapping` | 统一客户 ID 与平台昵称/账号映射 | 客户列表、客户详情、AI 客户助手 |

`raw_data` 的字段在不同平台并不相同，因此上传解析必须继续使用各平台独立配置，不建设跨平台统一原始字段解析器。

#### 21.2.2 销售汇总表

| 粒度 | 表名 | 金额字段 |
| --- | --- | --- |
| 日 | `daily_sales` | `transaction_amount` |
| 周 | `weekly_sales` | `weekly_transaction_amount` |
| 月 | `monthly_sales` | `monthly_transaction_amount` |
| 季度 | `quarterly_sales` | `quarterly_transaction_amount` |
| 半年 | `half_year_sales` | `half_year_transaction_amount` |

这些表用于基础 KPI、销售趋势、周期对比、AI 经营洞察和问看板中的销售问题。

#### 21.2.3 客户销售表

| 粒度 | 看板读取表 | 金额字段 | 拿货次数字段 |
| --- | --- | --- | --- |
| 日 | `customer_daily_sales` | `transaction_amount` | 当前按明细行计数 |
| 周 | `customer_weekly_sales` | `weekly_transaction_amount` | `weekly_purchase_count` |
| 月 | `customer_monthly_sales` | `monthly_transaction_amount` | `monthly_purchase_count` |
| 季度 | `customer_quarterly_sales` | `quarterly_transaction_amount` | `quarterly_purchase_count` |
| 半年 | `customer_half_year_sales` | `half_year_transaction_amount` | `half_year_purchase_count` |

店铺中还存在 `daily_customer_sales`、`weekly_customer_sales`、`monthly_customer_sales`、`quarterly_customer_sales`、`half_year_customer_sales` 等上传刷新过程表；当前客户页面最终读取的是上表列出的 `customer_*_sales` 表。

#### 21.2.4 商品销售表

| 粒度 | 范围商品表 | 客户商品表 |
| --- | --- | --- |
| 日 | `daily_product_sales` | `customer_daily_product_sales` |
| 周 | `weekly_product_sales` | 当前没有统一的 `customer_weekly_product_sales` 读取规格 |
| 月 | `monthly_product_sales` | `customer_monthly_product_sales` |
| 季度 | `quarterly_product_sales` | `customer_quarterly_product_sales` |
| 半年 | `half_year_product_sales` | `customer_half_year_product_sales` |

范围商品表用于商品数量 Top5、金额 Top5 和商品数量；客户商品表用于 AI 客户助手解释客户主要商品。当前统一字段只有 `product_code`、数量和金额，因此 AI 不得补写商品名称、品类、库存和毛利。

#### 21.2.5 退款、健康与预售表

| 数据类型 | 表名 | 使用范围 |
| --- | --- | --- |
| 退款 | `weekly_refunds`、`monthly_refunds`、`quarterly_refunds`、`half_year_refunds` | 店铺/平台/小组/全渠道退款分析，不支持单客户退款归因 |
| 客户健康 | `customer_health_detail` | 客户健康分、状态、状态说明、建议动作和健康分布 |
| 微店预售 | `monthly_product_presales`、`quarterly_product_presales`、`half_year_product_presales` | 仅 `weidian` Schema 的预售金额、数量、商品数和 Top 商品 |

#### 21.2.6 健康规则表

| 业务组 | `public` 表名 | 同步目标 |
| --- | --- | --- |
| 达人组 | `public.talent_customer_status_action` | `daren` 及达人组四个店铺的 `customer_health_detail` |
| 私域组 | `public.private_customer_status_action` | `siyu`、`youzan` 及私域组三个店铺的 `customer_health_detail` |
| 分销组 | `public.distribution_customer_status_action` | `fenxiao` 及分销组两个店铺的 `customer_health_detail` |

#### 21.2.7 当前实际汇总表

| Schema | 当前实际表 |
| --- | --- |
| `doudian` | `daily_sales_summary`、`weekly_sales_summary`、`monthly_sales_summary`、`quarterly_sales_summary`、`half_year_sales_summary`；对应四种周期的 `*_refunds_summary`；`half_year_customer_health`、`half_year_high_frequency_products` |
| `youzan` | `daily_sales`、四种周期的 `*_sales` 和 `*_refunds`、`customer_health_detail`、`half_year_product_frequency` |
| `daren` | `daily_sales`、四种周期的 `*_sales` 和 `*_refunds`、`customer_health_detail`、`half_year_high_frequency_products` |
| `siyu` | `daily_sales`、四种周期的 `*_sales` 和 `*_refunds`、`customer_health_detail`、`half_year_high_frequency_products` |
| `fenxiao` | `daily_sales`、四种周期的 `*_sales` 和 `*_refunds`、`customer_health_detail`、`half_year_high_frequency_products` |
| `qudao` | `daily_sales`、四种周期的 `*_sales` 和 `*_refunds` |

注意：`doudian` 的表名带 `_summary`，与其他汇总 Schema 不完全相同，后续 AI 工具不能仅拼接统一表名读取汇总层。推荐继续以九个店铺 Schema 为 AI 主事实来源，由确定性代码适配特殊汇总表，仅将汇总层用于上传联动核对或性能优化。

### 21.3 功能与数据库总映射

| 功能 | 读取的 Schema / 表 | 写入位置 | 实现结论 |
| --- | --- | --- | --- |
| 登录与会话 | 不读取 PostgreSQL | 不写数据库 | 账号来自 `config/accounts.json`，会话存于加密 Cookie |
| 基础经营看板 | 九个店铺 Schema 的销售、客户、商品、退款、健康和微店预售表 | 无 | 当前已实现 |
| AI 经营洞察 | 与基础看板完全相同；优先复用 `/dashboard` 的结构化结果 | 新增 `public.ai_request_log`，可选缓存表 | 一期可实现 |
| 客户列表/详情 | `customer_id_mapping`、`customer_*_sales`、`customer_*_product_sales`、`customer_health_detail` | 无 | 当前已实现 |
| AI 客户助手 | 客户详情所用表；店铺级退款可读取 `*_refunds` | 新增 AI 请求日志；反馈写 `public.ai_feedback` | 一期增强可实现 |
| 上传预览 | 目标店铺 `raw_data`、`customer_id_mapping`、周期销售/退款表及对应汇总 Schema | 预览模式不写数据库，任务当前存在后端进程内存 | 当前已实现 |
| 上传确认 | 目标店铺 `raw_data`、`customer_id_mapping`、33 张派生表；微店额外 3 张预售表；平台/组/渠道汇总表 | 同左，单事务提交 | 当前已实现 |
| AI 上传影响解释 | 直接使用上传预览返回的结构化 `business_preview`、`refresh` 和 `table_changes` | 只写 AI 请求日志和反馈 | 一期可实现 |
| 问看板 | 九个店铺 Schema 的白名单指标表；必要时读取汇总表做核对 | AI 请求日志、反馈；不写业务表 | 二期可实现 |
| 健康规则设置 | `public.*_customer_status_action` | 公共规则表及对应健康明细表 | 当前已实现 |
| AI 设置 | 不读取 PostgreSQL | 项目根目录 `.env` 的分角色配置项 | 当前已实现 |
| AI 审计与反馈 | 新建 `public.ai_request_log`、`public.ai_feedback` | 同左 | 一期需要新增 |
| 多智能体 | 与问看板相同，只能调用白名单只读工具 | AI 日志，不写业务表 | 三期可实现 |

### 21.4 AI 经营洞察的数据库与实现

#### 21.4.1 使用数据库

根据当前 `scope_key`，从一个或多个店铺 Schema 读取：

- 销售：`daily_sales`、`weekly_sales`、`monthly_sales`、`quarterly_sales`、`half_year_sales`。
- 客户规模：对应粒度的 `customer_*_sales`。
- 健康分布：`customer_weekly_sales` 与 `customer_health_detail`。
- 商品：`half_year_product_sales`。
- 退款：`weekly_refunds`、`monthly_refunds`、`quarterly_refunds`、`half_year_refunds`。
- 预售：仅 `weidian.monthly_product_presales`、`weidian.quarterly_product_presales`、`weidian.half_year_product_presales`。

#### 21.4.2 实现方式

1. 前端在 `DashboardPage` 获取 `/api/v1/dashboard` 成功后，将 `scope_key`、`as_of`、趋势粒度和退款粒度提交给 `/api/v1/ai/dashboard-insight`。
2. 新接口不能直接让模型查数据库，而是调用现有 `DashboardService.dashboard()` 生成确定性快照。
3. 新增 `InsightContextBuilder`，从快照中提取本期值、上期值、变化率、Top 商品、健康分布和退款趋势。
4. 对跨店铺问题增加 `get_scope_contribution` 查询，逐店读取相同周期的销售和退款结果，计算贡献和拖累排名。
5. 后端验证数字、日期和范围后，再把精简 JSON 上下文发送到 `request_ai_completion()`。
6. 模型只生成“结论、依据、风险、建议”文字；返回中的 `evidence` 由后端结构化数据直接生成。
7. 未配置 AI 或模型调用失败时，由确定性规则生成摘要，例如“本月销售较上月下降 X%，主要下降来自 A 店铺”。
8. 前端展示洞察，并把每条证据映射到现有销售、健康、商品或退款模块。

#### 21.4.3 建议代码位置

| 层级 | 建议位置 | 职责 |
| --- | --- | --- |
| 前端 API | `8.11/frontend/app/api.ts` | 增加 `dashboardInsight()` 类型和请求 |
| 前端页面 | `8.11/frontend/app/page.tsx` | 新增洞察卡片、加载/降级/反馈状态 |
| HTTP 接口 | `8.11/backend/app/main.py` | 增加 `/api/v1/ai/dashboard-insight` |
| 业务服务 | 新建 `8.11/backend/app/ai_orchestrator.py` | 构建上下文、调用模型、降级和组装证据 |
| 数据工具 | 新建 `8.11/backend/app/ai_tools.py` | 包装现有 Service/Repository 的只读查询 |
| 模型调用 | `8.11/backend/app/ai_provider.py` | 继续复用 OpenAI 兼容的 `/chat/completions` 调用 |

### 21.5 AI 客户助手的数据库与实现

#### 21.5.1 使用数据库

针对单个 `store_key + customer_id`，只读取该店铺 Schema：

- 身份与昵称：`customer_id_mapping`。
- 多周期销售和拿货：`customer_daily_sales`、`customer_weekly_sales`、`customer_monthly_sales`、`customer_quarterly_sales`、`customer_half_year_sales`。
- 多周期主要商品：`customer_daily_product_sales`、`customer_monthly_product_sales`、`customer_quarterly_product_sales`、`customer_half_year_product_sales`。
- 健康状态：`customer_health_detail`。
- 当前规则说明：客户所在组对应的 `public.*_customer_status_action`。
- 店铺退款背景：对应周期的 `*_refunds`，只能说明店铺总体退款，不能说成该客户退款。

#### 21.5.2 实现方式

1. 保留现有 `/api/v1/ai/chat` 和客户详情权限校验。
2. 将当前仅使用半年销售的上下文扩展为结构化客户快照，包括月、季、半年销售、拿货次数、Top 商品、健康快照日期和生效规则。
3. 后端先计算最近周期变化、商品集中度和数据是否缺失，再交给模型解释。
4. “为什么是当前健康状态”必须同时返回健康表中的原始状态、状态说明、快照日期和可核对指标。
5. “内部跟进建议”只读取诊断结果，由后端按证据确定优先级，不生成客户回复或扩大数据库范围。
6. 若用户问单客户退款，当前版本明确回答“数据库只有店铺周期退款汇总，无法归因该客户”，可补充店铺级背景但必须标注层级。
7. 客户助手不能调用上传、规则保存或任何数据库写工具。

### 21.6 AI 上传影响解释的数据库与实现

#### 21.6.1 店铺与联动 Schema

| 上传店铺 | 主写 Schema | 联动汇总 Schema | 已配置策略 |
| --- | --- | --- | --- |
| 微店 | `weidian` | `daren` → `qudao` | 已有日期默认跳过；额外刷新 3 张预售表 |
| 儿童服饰旗舰店 | `doudianChildren` | `doudian` → `daren` → `qudao` | 已有日期整日替换 |
| Kocotree 服饰配件店 | `doudianKocotree` | `doudian` → `daren` → `qudao` | 已有日期整日替换 |
| 快手小店 | `kuaishouxiaodian` | `daren` → `qudao` | 已有日期整日替换 |
| 有赞旗舰店 | `qijian` | `youzan` → `siyu` → `qudao` | 已有日期默认跳过 |
| 母婴旗舰店 | `muyinqijian` | `youzan` → `siyu` → `qudao` | 已有日期默认跳过 |
| 快团团 | `kuaituantuan` | `siyu` → `qudao` | 按“子订单号 + 商品编码”增量插入/更新 |
| 阿里巴巴 | `alibaba` | `fenxiao` → `qudao` | 已有日期跳过 |
| 聚水潭 | `jushuitan` | `fenxiao` → `qudao` | 已有日期默认跳过 |

#### 21.6.2 正式上传涉及的表

每个店铺通用刷新 33 张表：

```text
daily_sales
daily_product_sales
daily_customer_sales
weekly_sales / weekly_refunds / weekly_product_sales / weekly_customer_sales
monthly_sales / monthly_refunds / monthly_product_sales / monthly_customer_sales
quarterly_sales / quarterly_refunds / quarterly_product_sales / quarterly_customer_sales
half_year_sales / half_year_refunds / half_year_product_sales / half_year_customer_sales
daily_sales_metrics / weekly_sales_metrics / monthly_sales_metrics
customer_daily_sales / customer_daily_sales_metrics
customer_weekly_sales / customer_monthly_sales
customer_quarterly_sales / customer_half_year_sales
customer_daily_product_sales / customer_monthly_product_sales
customer_quarterly_product_sales / customer_half_year_product_sales
customer_health_detail
```

此外还写入或更新：

- 当前店铺 `raw_data`。
- 当前店铺 `customer_id_mapping`。
- 微店的 3 张预售表。
- 对应平台、小组和渠道汇总表。

#### 21.6.3 AI 解释实现

1. 上传预览仍由现有平台配置、`analyse_upload()` 和各平台 `preview.py` 完成。
2. AI 不再次读取上传文件，也不重新计算金额；直接读取预览结果中的 `business_preview`、`dates`、`refresh`、`rows_to_insert`、`rows_to_delete` 和 `table_changes`。
3. 后端先用规则标记大额下降、退款增加、有效行比例过低、日期断层和无变化文件。
4. 模型将规则结果转成业务语言，并列出需人工核对的项目。
5. AI 返回值不能修改 `commit_available`，也不能调用 `mode=commit`。
6. 正式写入仍由各店铺 `committer.py` 在同一事务中写 `raw_data`、客户映射、店铺派生表和各级汇总；任一步失败全部回滚。
7. 当前上传任务只保存在后端进程内 `TASKS` 字典中。若需要重启后仍能查看历史记录，应新增 `public.upload_task` 和 `public.upload_table_change`，但这不是 AI 解释功能上线的前置条件。

### 21.7 全局问看板的数据库与实现

#### 21.7.1 指标到表的白名单

| 问题类型 | 指标工具 | 允许读取的表 |
| --- | --- | --- |
| 销售额与趋势 | `get_sales_comparison` | `daily_sales`、`weekly_sales`、`monthly_sales`、`quarterly_sales`、`half_year_sales` |
| 小组/店铺贡献 | `get_scope_contribution` | 同粒度销售表，按 `catalog.py` 白名单逐店查询 |
| 客户数量与排名 | `get_customer_ranking` | `customer_*_sales`、`customer_health_detail`、`customer_id_mapping` |
| 商品 Top | `get_top_products` | `*_product_sales` |
| 客户主要商品 | `get_customer_products` | `customer_*_product_sales` |
| 退款趋势 | `get_refund_analysis` | `weekly_refunds`、`monthly_refunds`、`quarterly_refunds`、`half_year_refunds` |
| 健康分布 | `get_health_distribution` | `customer_weekly_sales`、`customer_health_detail` |
| 数据新鲜度 | `get_data_freshness` | 各店铺 `daily_sales.MAX(transaction_date)` |
| 预售 | `get_presale_summary` | 仅微店 3 张 `*_product_presales` |

#### 21.7.2 实现方式

1. 前端把问题和当前页面上下文提交给 `/api/v1/ai/query`。
2. 后端从加密会话获取真实角色，不能接收前端自定义角色。
3. 意图识别只输出 `metric_key`、`scope_key`、`grain`、`as_of`、`group_by`、`filters` 和输出形式。
4. `scope_key` 必须通过 `resolve_scope()` 转成允许的店铺集合。
5. 工具层根据指标目录选择固定 Repository 方法，不接受模型生成的表名、列名或 SQL。
6. 对多店铺结果使用同一完整截止日期，并返回各店铺数据新鲜度。
7. 后端将查询结果转换成统一证据结构，完成合计和变化率校验。
8. 模型基于结构化证据生成摘要；表格和图表直接使用查询结果，不从模型文本解析数字。
9. 超出白名单的问题拒答，并展示当前可查询指标。

#### 21.7.3 查询示例

用户问题：`本月哪个店铺销售额下降最多？`

```text
页面上下文
  scope_key = all
  as_of = 当前完整数据日期

意图结果
  metric_key = sales_amount
  grain = month
  group_by = store
  comparison = previous_period

工具执行
  resolve_scope(manager, all) -> 九个店铺
  逐店读取 monthly_sales 当前月和上月
  后端计算变化额和变化率并排序

返回
  一句话结论 + 店铺对比表 + 柱状图 + 数据日期 + 指标口径
```

### 21.8 健康规则、AI 配置和登录的存储方式

#### 21.8.1 健康规则

健康规则使用 PostgreSQL：

1. 页面通过 `/api/v1/settings/health-rules` 读取 `public` 中对应组规则表。
2. 组长保存后，后端事务更新公共规则表。
3. 后端按健康状态同步更新对应店铺、平台或小组的 `customer_health_detail.state_instructions` 和 `follow_up_action`。
4. AI 客户助手读取当前数据库规则，避免把旧提示词中的固定文案当成生效规则。

#### 21.8.2 AI 配置

AI 配置当前不使用数据库：

- `base_url`、`api_key`、`model_name` 保存在项目根目录 `.env`。
- 分别使用 `AI_MANAGER_*`、`AI_TALENT_*`、`AI_PRIVATE_*`、`AI_DISTRIBUTION_*` 四组配置。
- `app/settings.py` 负责读取和原子替换配置。
- 前端只能读取 `api_key_masked`，不能读取明文。

#### 21.8.3 登录与会话

登录当前不使用数据库：

- 账号及密码哈希读取 `8.11/backend/config/accounts.json`。
- 密码使用 scrypt 哈希验证。
- 用户、角色、所属组和过期时间写入加密会话 Cookie。
- PostgreSQL 业务接口依据解密后的角色执行 `resolve_scope()` 权限校验。

### 21.9 AI 审计需要新增的数据表

一期要实现可追溯和反馈，建议在同一个 `weidian` 数据库的 `public` Schema 新增以下表，不新增独立数据库：

#### 21.9.1 `public.ai_request_log`

| 字段 | 建议类型 | 说明 |
| --- | --- | --- |
| `id` | UUID / text | AI 请求 ID |
| `user_id` | text | 当前账号 ID |
| `role` | text | 请求时角色 |
| `feature_type` | text | dashboard/customer/upload/query |
| `scope_key` | text | 数据范围 |
| `store_keys` | jsonb | 实际访问店铺列表 |
| `as_of` | date | 统计截止日期 |
| `tool_calls` | jsonb | 已调用工具及参数摘要 |
| `evidence` | jsonb | 关键指标证据，不保存数据库凭据 |
| `model_name` | text | 实际模型 |
| `mode` | text | ai/rule_summary |
| `status` | text | success/failed/timeout |
| `duration_ms` | integer | 耗时 |
| `error_code` | text | 失败代码 |
| `created_at` | timestamptz | 创建时间 |

#### 21.9.2 `public.ai_feedback`

| 字段 | 建议类型 | 说明 |
| --- | --- | --- |
| `id` | UUID / text | 反馈 ID |
| `request_id` | UUID / text | 关联 AI 请求 |
| `user_id` | text | 反馈账号 |
| `helpful` | boolean | 是否有帮助 |
| `reason` | text | 不准确、缺少依据、不可执行、太泛等 |
| `comment` | text | 可选补充说明 |
| `created_at` | timestamptz | 创建时间 |

#### 21.9.3 可选缓存

如模型调用成本或速度成为问题，可增加 `public.ai_summary_cache`，缓存键至少包含：

```text
feature_type + user_role + scope_key + as_of + data_version + prompt_version
```

数据上传成功或规则变更后，通过 `data_version` 变化使旧缓存自然失效，不直接复用旧摘要。

### 21.10 实施顺序与代码改造范围

#### 第一步：统一只读数据工具

- 将 `DashboardService` 和 `CustomerService` 的查询包装为 AI 可调用的只读工具。
- 工具内部继续使用 `catalog.py`、`repositories.py` 和 `periods.py`。
- 不复制一套 AI 专用 SQL，防止看板与 AI 数字不一致。

#### 第二步：实现一期三个 AI 功能

1. `/ai/dashboard-insight`：复用看板快照。
2. `/ai/customer-analysis`：扩展客户多周期上下文。
3. `/ai/upload-explanation`：直接解释上传预览结构。

同时新增 AI 请求日志、反馈和规则摘要降级。

#### 第三步：完成数据质量前置检查

- 为九个店铺读取 `daily_sales.MAX(transaction_date)`。
- 多店铺查询按业务确认的完整截止日期执行。
- 核对 `customer_health_detail` 的快照日期和销售周期。
- 未解决的冲突进入 `warnings`，不得交给模型自行补全。

#### 第四步：实现二期问看板

- 建立指标目录和工具参数 Schema。
- 实现意图解析、工具选择、权限校验、证据验证和结构化回答。
- 表格与图表直接绑定工具结果。
- 只支持已登记指标，不提供自由 SQL。

#### 第五步：评估多智能体

- 只有当单次问题确实需要销售、客户、退款和数据质量多个专题并行分析时，才启用多个 Agent。
- 多 Agent 共享同一工具白名单和日志表，不建设各自独立数据库。
- 权限和结果验证始终由后端确定性代码控制。

### 21.11 当前能够实现与暂不能可靠实现的边界

| 能力 | 当前数据是否支持 | 说明 |
| --- | --- | --- |
| 经营摘要、趋势和周期对比 | 支持 | 已有销售汇总表 |
| 小组、平台和店铺贡献分析 | 支持 | 可按九个店铺 Schema 聚合 |
| 客户销售、拿货和主要商品分析 | 支持 | 已有客户销售和客户商品表 |
| 客户健康解释 | 有条件支持 | 需先解决部分快照与销售周期不一致问题 |
| 店铺退款分析 | 支持 | 周、月、季、半年退款表齐全 |
| 单客户退款归因 | 暂不支持 | 当前统一模型没有客户退款表 |
| 微店预售分析 | 支持 | 仅微店有统一预售表 |
| 其他店铺预售分析 | 暂不支持 | 缺少统一预售数据源 |
| 商品名称、品类、库存、毛利分析 | 暂不支持 | 当前统一商品数据主要只有编码、数量和金额 |
| 销售预测 | 暂不建议 | 尚无预测口径、训练和验证体系 |
| 自由 SQL | 禁止 | 存在越权、口径不一致和数据库风险 |
| 自动提交上传、修改规则、发客户消息 | 禁止 | AI 只解释和建议，不执行高风险操作 |
