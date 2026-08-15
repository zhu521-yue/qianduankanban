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
  const [page, client, dimension, customerAssistant] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/api.ts", import.meta.url), "utf8"),
    readFile(new URL("../app/CustomerDimensionPanel.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/CustomerAiAssistant.tsx", import.meta.url), "utf8"),
  ]);
  for (const endpoint of ["/auth/login", "/auth/session", "/auth/logout", "/meta/options", "/dashboard?", "/customers?", "/settings/health-rules", "/settings/ai", "/settings/ai/test", "/ai/dashboard-insight", "/ai/customer-analysis", "/ai/query", "/ai/chat", "/uploads/sales"]) {
    assert.match(client, new RegExp(endpoint.replaceAll("/", "\\/")));
  }
  assert.match(client, /credentials: "include"/);
  assert.match(client, /window\.location\.hostname/);
  assert.match(client, /NEXT_PUBLIC_API_PORT/);
  assert.doesNotMatch(client, /http:\/\/127\.0\.0\.1:8000\/api\/v1/);
  assert.match(page, /api\.dashboard/);
  assert.match(page, /api\.customers/);
  assert.match(page, /api\.customer/);
  assert.match(customerAssistant, /api\.chat/);
  assert.match(customerAssistant, /api\.customerAnalysis/);
  assert.match(page, /api\.uploadPreview/);
  assert.match(page, /api\.healthRules/);
  assert.match(dimension, /customer\.dimensions\[grain\]/);
});

test("adds an independent source-backed AI business insight panel with rule fallback", async () => {
  const [page, client, insight] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/api.ts", import.meta.url), "utf8"),
    readFile(new URL("../app/AiInsightPanel.tsx", import.meta.url), "utf8"),
  ]);
  assert.match(page, /<AiInsightPanel/);
  assert.match(page, /onOpenSettings=\{openSettings\}/);
  assert.match(client, /dashboardInsight/);
  assert.match(client, /method: "POST"/);
  assert.match(client, /signal/);
  for (const label of ["AI 经营洞察", "规则摘要", "AI 分析", "已降级", "数据库证据", "建议动作", "前往 AI 设置", "不自动执行"]) {
    assert.match(insight, new RegExp(label));
  }
  assert.match(insight, /controller\.abort\(\)/);
  assert.match(insight, /api\.dashboardInsight/);
});

test("adds an internal customer operating assistant with source evidence and rule fallback", async () => {
  const [page, client, assistant] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/api.ts", import.meta.url), "utf8"),
    readFile(new URL("../app/CustomerAiAssistant.tsx", import.meta.url), "utf8"),
  ]);
  assert.match(page, /<CustomerAiAssistant/);
  assert.match(page, /onOpenSettings=\{openSettings\}/);
  assert.match(client, /customerAnalysis/);
  assert.match(client, /analysis_type: CustomerAnalysisType/);
  for (const label of ["客户经营助手", "仅供业务内部分析", "综合诊断", "最近表现", "健康依据", "主要商品", "店铺退款", "内部跟进", "数据库证据", "内部跟进建议", "内部数据问答", "规则诊断", "AI 诊断", "已降级", "前往 AI 设置", "不自动执行"]) {
    assert.match(assistant, new RegExp(label));
  }
  assert.match(assistant, /controller\.abort\(\)/);
  assert.match(assistant, /api\.customerAnalysis/);
  assert.match(assistant, /店铺退款数据不归因到单个客户/);
  assert.doesNotMatch(assistant, /回复客户|沟通话术|营销文案|复制|发送给客户/);
});

test("adds a global controlled AI dashboard query drawer", async () => {
  const [page, client, drawer] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/api.ts", import.meta.url), "utf8"),
    readFile(new URL("../app/AskDashboardDrawer.tsx", import.meta.url), "utf8"),
  ]);
  assert.match(page, /<AskDashboardDrawer/);
  assert.match(page, /onContextChange=\{reportDashboardContext\}/);
  assert.match(page, /type AiQueryContext/);
  assert.match(client, /aiQuery/);
  assert.match(client, /"\/ai\/query"/);
  assert.match(client, /type AiQueryResult/);
  for (const label of ["AI 问看板", "自然语言理解", "白名单指标", "数据库证据", "AI 问数", "规则问数", "已降级", "关键证据", "查询明细", "在看板中查看", "所有数字来自只读数据库工具", "不执行数据库写操作"]) {
    assert.match(drawer, new RegExp(label));
  }
  assert.match(drawer, /new AbortController\(\)/);
  assert.match(drawer, /api\.aiQuery/);
  assert.match(drawer, /result\.chart/);
  assert.match(drawer, /result\.table\.rows/);
  assert.doesNotMatch(drawer, /dangerouslySetInnerHTML|contentEditable/);
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
  for (const moduleName of ["销售走势", "自然周客户健康度", "半年高频商品", "退款金额分析", "输入客户ID筛选", "CustomerAiAssistant"]) assert.match(page, new RegExp(moduleName));
});

test("uses expandable business groups and nested platforms without navigating from parent buttons", async () => {
  const page = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");
  for (const label of ["业务分组", "分销组", "私域组", "达人组", "有赞", "抖店"]) assert.match(page, new RegExp(label));
  assert.match(page, /const GROUP_NAV_CONFIG/);
  assert.match(page, /onClick=\{\(\) => toggleGroup\(groupKey\)\}/);
  assert.match(page, /onClick=\{\(\) => togglePlatform\(item\.scopeKey\)\}/);
  assert.match(page, /aria-expanded=\{groupExpanded\}/);
  assert.match(page, /aria-expanded=\{platformExpanded\}/);
  assert.match(page, /overallPage && pageButton/);
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
