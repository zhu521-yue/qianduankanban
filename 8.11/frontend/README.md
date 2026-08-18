# 客户经营看板前端

本目录提供客户经营看板页面，包含登录、经营数据、客户详情、上传和健康规则设置。

## 运行

```bash
npm install
npm run dev
npm run build
npm run lint
```

开发服务器默认使用 `http://127.0.0.1:3011`。前端通过根目录 `.env` 中的 `NEXT_PUBLIC_API_PORT` 或 `NEXT_PUBLIC_API_BASE_URL` 连接后端。

## 页面结构

- `app/page.tsx`：登录、分组导航、经营看板、客户详情、上传和设置页面。
- `app/api.ts`：后端接口类型与请求封装。
- `app/CustomerDimensionPanel.tsx`：客户多周期数据详情。
- `app/globals.css`：页面样式和交互状态。

## 验证

生产构建会检查页面引用、类型和打包配置：

```bash
npm run build
```