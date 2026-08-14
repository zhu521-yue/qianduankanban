# AI 客户看板 Backend

本目录是 `8.11/frontend` 的独立后端，直接连接现有 PostgreSQL `weidian` 数据库。前端的销售、客户、商品、退款、预售、设置和 AI 客户上下文均已改为读取 `/api/v1`，不再使用静态业务快照。经营数据保持只读；客户状态规则保存会在同一事务中写入 public 配置表并同步本组客户健康度表。

## 架构

```text
现有 React UI
    │  /api/v1 + HttpOnly 签名 Cookie
    ▼
FastAPI（认证、数据范围、页面聚合）
    ▼
PostgreSQL weidian（现有多 schema 业务表）
```

后端不会创建新数据库，也不会写入演示数据。已执行 `migrations/001_customer_status_rules.sql` 创建三张客户状态规则配置表，并执行 `migrations/002_platform_health_rule_columns.sql` 为抖店平台级健康表补齐规则说明和跟进动作字段。当前读取的店铺 schema：

| 前端店铺 | PostgreSQL schema |
|---|---|
| 微店 | `weidian` |
| 儿童服饰旗舰店 | `doudianChildren` |
| Kocotree服饰配件店 | `doudianKocotree` |
| 快手小店 | `kuaishouxiaodian` |
| 有赞旗舰店 | `qijian` |
| 母婴旗舰店 | `muyinqijian` |
| 快团团 | `kuaituantuan` |
| 阿里巴巴 | `alibaba` |
| 聚水潭 | `jushuitan` |

查询直接使用已有的日/周/月/季度/半年销售表、客户销售表、客户商品表、退款表、预售表和客户健康度表。

## 运行环境

用户指定环境：

```text
D:\Anaconda\envs\AIFrontOutloook\python.exe
```

安装依赖：

```powershell
conda activate AIFrontOutloook
cd D:\实习\AI客户看板\8.11\backend
python -m pip install -r requirements.txt
```

在项目根目录复制并修改全项目唯一的环境配置：

```powershell
Copy-Item ..\..\.env.example ..\..\.env
```

后端、前端以及 `数据表建设/scripts` 下的数据库脚本都会读取这一个根目录 `.env`。至少需要：

```dotenv
DATABASE_URL=postgresql://<user>:<password>@127.0.0.1:5432/weidian
APP_ENCRYPTION_KEY=<Fernet key>
ACCOUNTS_FILE=config/accounts.json
```

本地开发时 `NEXT_PUBLIC_API_BASE_URL` 留空，前端会用 `NEXT_PUBLIC_API_PORT` 和浏览器当前主机名连接后端，确保登录 Cookie 不会因 `localhost` / `127.0.0.1` 混用而丢失。分离部署时再显式填写完整的 `NEXT_PUBLIC_API_BASE_URL`。

AI接口由四个固定登录角色在各自设置页维护。配置测试成功后，后端只更新根目录 `.env` 中当前角色对应的 `AI_MANAGER_*`、`AI_TALENT_*`、`AI_PRIVATE_*` 或 `AI_DISTRIBUTION_*`，并立即热加载；前端不保存密钥，后续AI对话也不会携带密钥。

生成签名密钥：

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

启动：

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

- API：`http://127.0.0.1:8000/api/v1`
- OpenAPI：`http://127.0.0.1:8000/api/docs`
- 健康检查：`http://127.0.0.1:8000/api/v1/health`

运行测试：

```powershell
python -m pytest -q
```

## API

| 方法 | 路径 | 用途 |
|---|---|---|
| `POST` | `/api/v1/auth/login` | 登录并签发 Cookie |
| `GET` | `/api/v1/auth/session` | 恢复登录状态 |
| `POST` | `/api/v1/auth/logout` | 退出 |
| `GET` | `/api/v1/meta/options` | 当前账号可访问范围 |
| `GET` | `/api/v1/dashboard` | 返回看板 KPI、趋势、健康度、商品、退款、预售 |
| `GET` | `/api/v1/customers` | 客户搜索、状态筛选、排序、分页 |
| `GET` | `/api/v1/customers/{store_key}/{customer_id}` | 客户详情和五种时间维度 |
| `GET` | `/api/v1/uploads/template` | 下载标准校验模板 |
| `POST` | `/api/v1/uploads/sales` | 九店销售文件预览及确认后的原子写入 |
| `GET` | `/api/v1/settings/health-rules` | 组账号读取本组固定 7 条规则；主管返回空组 |
| `PUT` | `/api/v1/settings/health-rules` | 组账号保存本组规则并事务同步组级、平台级、店铺级健康度表；主管禁止 |
| `GET` | `/api/v1/settings/ai` | 读取当前登录角色的AI配置状态和密钥掩码 |
| `POST` | `/api/v1/settings/ai/test` | 使用当前输入或已保存密钥测试当前角色的AI接口 |
| `PUT` | `/api/v1/settings/ai` | 复测成功后原子保存当前角色配置并热加载 |
| `POST` | `/api/v1/ai/chat` | 按当前登录角色的独立配置生成客户经营回复 |

所有业务响应使用统一结构：

```json
{
  "code": "OK",
  "message": "success",
  "data": {},
  "errors": [],
  "request_id": "req_xxx"
}
```

金额以两位小数字符串返回，比例以小数或 `null` 返回。前端只负责格式化，不重复计算业务口径。

## 看板范围参数

`GET /api/v1/dashboard` 参数示例：

```text
scope_key=talent.doudian.children
as_of=2026-07-28
trend_grain=month
refund_grain=half
```

可用范围包括 `talent`、`talent.weidian`、`talent.doudian`、`talent.doudian.children`、`private`、`private.youzan.qijian`、`distribution.alibaba`、`all` 等。后端从签名 Cookie 确定角色，组长越权访问会返回 403。

## 登录说明

为避免修改现有业务库，账号独立保存在 `config/accounts.json`，代码中不再内置账号；密码仅保存 scrypt 哈希，登录状态使用加密签名 Cookie，不需要新增用户表或 Session 表。该实际账号文件已经加入 `.gitignore`，`config/accounts.example.json` 只提供格式模板。

修改现有账号密码（交互式输入，不会把明文写入文件）：

```powershell
cd D:\实习\AI客户看板\8.11\backend
D:\Anaconda\envs\AIFrontOutloook\python.exe scripts\set_account_password.py <账号名>
```

账号显示名称、角色和分组可以直接编辑 `config/accounts.json`。合法角色为 `talent`、`private`、`distribution`、`manager`；除主管外，`group_key` 应与角色一致。修改完成后无需重启，下一次登录会重新读取文件。

## 上传边界

现有数据库每个平台的 `raw_data` 字段和订单口径不同。接口支持九个店铺对应的原始 CSV/XLSX 文件预览和`mode=commit`原子写入。上传前会校验店铺交易时间字段、业务必需字段以及`raw_data`列兼容性。抖店两店和快手按交易日期整日覆盖；微店、有赞两店、阿里巴巴和聚水潭跳过数据库已有日期；快团团按`子订单号 + 商品编码`增量更新。所有正式写入均在单一事务中联动原始表、客户名单、店铺派生表和上级汇总表，任一步失败整体回滚。

各店铺配置明确维护以下规则，修改平台导出格式或业务口径时必须同步复核：

- 原始列名映射；
- 订单唯一键与重复订单处理；
- 销售金额、退款金额和预售口径；
- 覆盖还是增量；
- 写入 `raw_data` 后需要刷新的汇总表。

逐平台规则确认后，应分别实现处理器，不能用一套通用猜测逻辑写所有 schema。

## 前端接入状态

1. 登录页调用 `/auth/login`，身份由 HttpOnly Cookie 保存，前端不保存账号密码。
2. 应用启动调用 `/auth/session`，上传页调用 `/meta/options` 获取账号权限内店铺。
3. 每个看板路由映射为一个 `scope_key`，KPI、趋势、健康度、商品、退款和预售均调用 `/dashboard`。
4. 客户表调用 `/customers`，搜索与分页由后端完成。
5. 客户详情调用 `/customers/{store_key}/{customer_id}`，读取五种时间维度；AI 助手调用 `/ai/chat`。
6. 上传页先调用`mode=preview`；仅对后端返回`commit_available=true`的店铺显示二次确认按钮，确认后调用`mode=commit`。
7. 三个业务组的设置页从 public 规则配置表读取并保存本组 7 条固定状态；保存与组级、平台级、店铺级健康度表同步处于同一事务。主管设置页完全不请求、也不展示客户健康度规则模块。

客户状态规则完整同步目标：

- 达人组：`daren.customer_health_detail`、`doudian.half_year_customer_health`、`weidian.customer_health_detail`、`doudianChildren.customer_health_detail`、`doudianKocotree.customer_health_detail`、`kuaishouxiaodian.customer_health_detail`；
- 私域组：`siyu.customer_health_detail`、`youzan.customer_health_detail`、`qijian.customer_health_detail`、`muyinqijian.customer_health_detail`、`kuaituantuan.customer_health_detail`；
- 分销组：`fenxiao.customer_health_detail`、`alibaba.customer_health_detail`、`jushuitan.customer_health_detail`。

分销组保存性能优化：

- 保存前先锁定并比较 public 当前规则，只同步文案真正变化的状态；
- 内容完全相同时不扫描任何健康度表；
- `fenxiao`、`alibaba` 的非“流失”状态使用部分索引定位，不再扫描约 677 万行；
- “流失”仍保持强一致物理同步，由于匹配约 1355 万条组级及店铺级记录，修改该状态时仍会明显较慢；
- 运维修复脚本 `scripts/sync_customer_status_rules.py` 使用显式强制同步，不受差异更新跳过机制影响。

完整页面—模块—数据库表映射见 `../前端模块与数据库表映射.md`。

开发期跨端口请求需携带 Cookie：`credentials: "include"`。生产环境建议同域反向代理 `/api`。
