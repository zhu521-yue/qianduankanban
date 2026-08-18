# 客户经营看板后端

本目录是 `8.11/frontend` 的独立后端，连接现有 PostgreSQL `weidian` 数据库，提供登录、经营看板、客户、上传和健康规则能力。

## 架构

```text
前端页面
    │ /api/v1 + HttpOnly Cookie
    ▼
FastAPI（认证、权限、聚合、上传）
    ▼
PostgreSQL weidian（多 schema 业务表）
```

经营数据保持只读；健康规则保存会在同一事务中更新配置表和对应健康度表。后端不创建演示数据。

## 运行环境

项目使用 `AIFrontOutloook` 虚拟环境运行：

```powershell
conda activate AIFrontOutloook
cd D:\Python Project\model\qianduankanban\8.11\backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8011
```

根目录 `.env` 至少需要数据库、Cookie、账号文件、上传大小和加密密钥配置。请从 `.env.example` 复制模板；不要提交 `.env`。

## API

| 方法 | 路径 | 用途 |
|---|---|---|
| `POST` | `/api/v1/auth/login` | 登录并签发 Cookie |
| `GET` | `/api/v1/auth/session` | 恢复登录状态 |
| `POST` | `/api/v1/auth/logout` | 退出 |
| `GET` | `/api/v1/meta/options` | 当前账号可访问范围 |
| `GET` | `/api/v1/dashboard` | KPI、趋势、健康度、商品、退款和预售 |
| `GET` | `/api/v1/customers` | 客户搜索、排序和分页 |
| `GET` | `/api/v1/customers/{store_key}/{customer_id}` | 客户详情和五种时间维度 |
| `GET` | `/api/v1/uploads/template` | 下载上传模板 |
| `POST` | `/api/v1/uploads/sales` | 文件预览或确认写入 |
| `GET` | `/api/v1/settings/health-rules` | 读取健康规则 |
| `PUT` | `/api/v1/settings/health-rules` | 保存健康规则并同步健康度表 |

所有业务响应使用统一结构，金额返回两位小数字符串，周期和权限由后端确定。

## 测试

```powershell
cd D:\Python Project\model\qianduankanban\8.11\backend
python -m pytest -q
```