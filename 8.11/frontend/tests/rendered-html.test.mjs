import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  return worker.fetch(
    new Request("http://localhost/", { headers: { accept: "text/html" } }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

test("server-renders the backend-authenticated login shell", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /<title>AI客户看板<\/title>/i);
  assert.match(html, /登录客户看板/);
  assert.match(html, /正在连接后端/);
  assert.match(html, /账号由后端独立配置文件管理/);
  assert.doesNotMatch(html, /儿童服饰旗舰店|半年客户健康度|输入客户ID筛选/);
});

test("uses the backend API for authentication and every business data module", async () => {
  const [page, client, dimension] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/api.ts", import.meta.url), "utf8"),
    readFile(new URL("../app/CustomerDimensionPanel.tsx", import.meta.url), "utf8"),
  ]);
  for (const endpoint of ["/auth/login", "/auth/session", "/auth/logout", "/meta/options", "/dashboard?", "/customers?", "/settings/health-rules", "/settings/ai", "/settings/ai/test", "/ai/chat", "/uploads/sales"]) {
    assert.match(client, new RegExp(endpoint.replaceAll("/", "\\/")));
  }
  assert.match(client, /credentials: "include"/);
  assert.match(client, /window\.location\.hostname/);
  assert.match(client, /NEXT_PUBLIC_API_PORT/);
  assert.doesNotMatch(client, /http:\/\/127\.0\.0\.1:8000\/api\/v1/);
  assert.match(page, /api\.dashboard/);
  assert.match(page, /api\.customers/);
  assert.match(page, /api\.customer/);
  assert.match(page, /api\.chat/);
  assert.match(page, /api\.uploadPreview/);
  assert.match(page, /api\.healthRules/);
  assert.match(dimension, /customer\.dimensions\[grain\]/);
});

test("keeps all role route hierarchies while sourcing values from the API", async () => {
  const page = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");
  for (const route of [
    "#/talent/overall", "#/talent/weidian", "#/talent/doudian/children", "#/talent/doudian/kocotree", "#/talent/kuaishou", "#/talent/upload", "#/talent/settings",
    "#/private/overall", "#/private/youzan/overall", "#/private/youzan/qijian", "#/private/youzan/muyinqijian", "#/private/kuaituantuan", "#/private/upload", "#/private/settings",
    "#/distribution/overall", "#/distribution/alibaba", "#/distribution/jushuitan", "#/distribution/upload", "#/distribution/settings",
    "#/manager/overall", "#/manager/distribution/overall", "#/manager/private/overall", "#/manager/talent/overall", "#/manager/settings",
  ]) assert.match(page, new RegExp(route.replaceAll("/", "\\/")));
  assert.match(page, /有赞旗舰店/);
  assert.match(page, /title: "母婴旗舰店"/);
  assert.doesNotMatch(page, /有赞母婴旗舰店/);
  for (const moduleName of ["销售走势", "自然周客户健康度", "半年高频商品", "退款金额分析", "输入客户ID筛选", "客户分析助手"]) assert.match(page, new RegExp(moduleName));
});

test("contains no frontend account passwords or legacy static business snapshots", async () => {
  const page = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");
  assert.doesNotMatch(page, /Daren@2026|Siyu@2026|Fenxiao@2026|Manager@2026/);
  assert.doesNotMatch(page, /dateFactor|adjustKpiValue|privateCustomers|healthData|trendSets|refundSourceRecords|待同步对应平台客户/);
  for (const legacy of ["authConfig.ts", "dataSnapshots.ts", "customerDimensionSnapshots.ts", "PrivateGroupApp.tsx", "DistributionGroupApp.tsx", "SupervisorApp.tsx"]) {
    await assert.rejects(access(new URL(`../app/${legacy}`, import.meta.url)));
  }
});

test("keeps real-data date selection, customer drill-down and preview-before-commit upload", async () => {
  const [page, client] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/api.ts", import.meta.url), "utf8"),
  ]);
  assert.match(page, /type="date" value=\{selectedDate\}/);
  assert.match(page, /latest_data_date/);
  assert.match(page, /data\.customer_health\.period\.start/);
  assert.match(page, /data\.customer_health\.period\.end/);
  assert.match(page, /encodeURIComponent\(customer\.store_key\)/);
  assert.match(page, /encodeURIComponent\(customer\.customer_id\)/);
  assert.match(page, /先预览全部影响，确认后才会写入数据库/);
  assert.match(page, /确认写入数据库/);
  assert.match(page, /window\.confirm/);
  assert.match(client, /uploadCommit/);
  assert.match(client, /form\.set\("mode", "commit"\)/);
  assert.match(page, /数据由 weidian 数据库实时驱动/);
});

test("keeps customer health rule statuses fixed and saves through the backend", async () => {
  const [page, client] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/api.ts", import.meta.url), "utf8"),
  ]);
  assert.match(page, /\["高活跃", "活跃", "稳定", "观察", "风险", "流失预警", "流失"\] as const/);
  assert.match(page, /保存客户状态规则/);
  assert.match(page, /api\.updateHealthRules/);
  assert.match(page, /规则内容没有变化，无需同步客户健康度表/);
  assert.match(page, /changed_statuses\.join/);
  assert.match(page, /user\.role !== "manager"/);
  assert.match(page, /user\.role === "manager"/);
  assert.match(page, /主管端 AI 大模型相关设置/);
  assert.match(page, /测试连接/);
  assert.match(page, /保存配置/);
  assert.match(page, /当前账号独立配置/);
  assert.match(page, /api\.testAiSetting/);
  assert.match(page, /api\.updateAiSetting/);
  assert.match(client, /method: "PUT"/);
  assert.match(client, /customer_health_status/);
  assert.match(client, /follow_up_action/);
});
