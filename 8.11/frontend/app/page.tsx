"use client";

import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";
import CustomerDimensionPanel from "./CustomerDimensionPanel";
import {
  ApiRequestError,
  api,
  type AiSetting,
  type CustomerDetailData,
  type CustomerListData,
  type CustomerListItem,
  type DashboardData,
  type Grain,
  type HealthRuleGroup,
  type MetaOptions,
  type ProductRecord,
  type Role,
  type StoreOption,
  type UploadPreview,
  type User,
} from "./api";

type PageKind = "dashboard" | "upload" | "settings";
type PageConfig = {
  key: string;
  route: string;
  kind: PageKind;
  title: string;
  navLabel: string;
  section: string;
  breadcrumb: string[];
  subtitle: string;
  scopeKey?: string;
  showCustomers?: boolean;
};

const pagesByRole: Record<Role, PageConfig[]> = {
  talent: [
    { key: "overall", route: "#/talent/overall", kind: "dashboard", title: "达人组整体经营概览", navLabel: "整体展示页", section: "达人组", breadcrumb: ["达人组", "整体展示页"], subtitle: "达人渠道全部店铺汇总", scopeKey: "talent", showCustomers: true },
    { key: "weidian", route: "#/talent/weidian", kind: "dashboard", title: "微店", navLabel: "微店", section: "达人组", breadcrumb: ["达人组", "微店"], subtitle: "微店经营与客户数据", scopeKey: "talent.weidian", showCustomers: true },
    { key: "doudian-overall", route: "#/talent/doudian/overall", kind: "dashboard", title: "抖店整体", navLabel: "抖店整体", section: "抖店", breadcrumb: ["达人组", "抖店", "整体"], subtitle: "抖店两家店铺汇总", scopeKey: "talent.doudian", showCustomers: true },
    { key: "doudian-children", route: "#/talent/doudian/children", kind: "dashboard", title: "儿童服饰旗舰店", navLabel: "儿童服饰旗舰店", section: "抖店", breadcrumb: ["达人组", "抖店", "儿童服饰旗舰店"], subtitle: "儿童服饰旗舰店经营数据", scopeKey: "talent.doudian.children", showCustomers: true },
    { key: "doudian-kocotree", route: "#/talent/doudian/kocotree", kind: "dashboard", title: "Kocotree服饰配件店", navLabel: "Kocotree服饰配件店", section: "抖店", breadcrumb: ["达人组", "抖店", "Kocotree服饰配件店"], subtitle: "Kocotree服饰配件店经营数据", scopeKey: "talent.doudian.kocotree", showCustomers: true },
    { key: "kuaishou", route: "#/talent/kuaishou", kind: "dashboard", title: "快手小店", navLabel: "快手小店", section: "达人组", breadcrumb: ["达人组", "快手小店"], subtitle: "快手小店经营与客户数据", scopeKey: "talent.kuaishou", showCustomers: true },
    { key: "upload", route: "#/talent/upload", kind: "upload", title: "达人组数据上传", navLabel: "上传", section: "系统", breadcrumb: ["达人组", "上传"], subtitle: "按平台与店铺预览数据文件" },
    { key: "settings", route: "#/talent/settings", kind: "settings", title: "达人组看板设置", navLabel: "设置", section: "系统", breadcrumb: ["达人组", "设置"], subtitle: "查看数据库健康规则与后端 AI 配置" },
  ],
  private: [
    { key: "overall", route: "#/private/overall", kind: "dashboard", title: "私域组整体经营概览", navLabel: "整体展示页", section: "私域组", breadcrumb: ["私域组", "整体展示页"], subtitle: "私域渠道全部店铺汇总", scopeKey: "private", showCustomers: true },
    { key: "youzan-overall", route: "#/private/youzan/overall", kind: "dashboard", title: "有赞整体", navLabel: "有赞整体", section: "有赞", breadcrumb: ["私域组", "有赞", "整体"], subtitle: "有赞两家店铺汇总", scopeKey: "private.youzan", showCustomers: true },
    { key: "youzan-qijian", route: "#/private/youzan/qijian", kind: "dashboard", title: "有赞旗舰店", navLabel: "有赞旗舰店", section: "有赞", breadcrumb: ["私域组", "有赞", "有赞旗舰店"], subtitle: "有赞旗舰店经营数据", scopeKey: "private.youzan.qijian", showCustomers: true },
    { key: "youzan-muying", route: "#/private/youzan/muyinqijian", kind: "dashboard", title: "母婴旗舰店", navLabel: "母婴旗舰店", section: "有赞", breadcrumb: ["私域组", "有赞", "母婴旗舰店"], subtitle: "母婴旗舰店经营数据", scopeKey: "private.youzan.muying", showCustomers: true },
    { key: "kuaituantuan", route: "#/private/kuaituantuan", kind: "dashboard", title: "快团团", navLabel: "快团团", section: "私域组", breadcrumb: ["私域组", "快团团"], subtitle: "快团团经营与客户数据", scopeKey: "private.kuaituantuan", showCustomers: true },
    { key: "upload", route: "#/private/upload", kind: "upload", title: "私域组数据上传", navLabel: "上传", section: "系统", breadcrumb: ["私域组", "上传"], subtitle: "按店铺预览数据文件" },
    { key: "settings", route: "#/private/settings", kind: "settings", title: "私域组看板设置", navLabel: "设置", section: "系统", breadcrumb: ["私域组", "设置"], subtitle: "查看数据库健康规则与后端 AI 配置" },
  ],
  distribution: [
    { key: "overall", route: "#/distribution/overall", kind: "dashboard", title: "分销组整体经营概览", navLabel: "整体展示页", section: "分销组", breadcrumb: ["分销组", "整体展示页"], subtitle: "分销渠道全部店铺汇总", scopeKey: "distribution", showCustomers: true },
    { key: "alibaba", route: "#/distribution/alibaba", kind: "dashboard", title: "阿里巴巴", navLabel: "阿里巴巴", section: "分销组", breadcrumb: ["分销组", "阿里巴巴"], subtitle: "阿里巴巴经营与客户数据", scopeKey: "distribution.alibaba", showCustomers: true },
    { key: "jushuitan", route: "#/distribution/jushuitan", kind: "dashboard", title: "聚水潭", navLabel: "聚水潭", section: "分销组", breadcrumb: ["分销组", "聚水潭"], subtitle: "聚水潭经营与客户数据", scopeKey: "distribution.jushuitan", showCustomers: true },
    { key: "upload", route: "#/distribution/upload", kind: "upload", title: "分销组数据上传", navLabel: "上传", section: "系统", breadcrumb: ["分销组", "上传"], subtitle: "按店铺预览数据文件" },
    { key: "settings", route: "#/distribution/settings", kind: "settings", title: "分销组看板设置", navLabel: "设置", section: "系统", breadcrumb: ["分销组", "设置"], subtitle: "查看数据库健康规则与后端 AI 配置" },
  ],
  manager: [
    { key: "overall", route: "#/manager/overall", kind: "dashboard", title: "主管整体经营概览", navLabel: "整体经营概览", section: "主管视图", breadcrumb: ["主管", "整体经营概览"], subtitle: "全部业务组与店铺汇总", scopeKey: "all", showCustomers: true },
    { key: "distribution-overall", route: "#/manager/distribution/overall", kind: "dashboard", title: "分销组", navLabel: "分销组整体", section: "分销组", breadcrumb: ["主管", "分销组"], subtitle: "分销组经营汇总", scopeKey: "distribution", showCustomers: true },
    { key: "distribution-alibaba", route: "#/manager/distribution/alibaba", kind: "dashboard", title: "阿里巴巴", navLabel: "阿里巴巴", section: "分销组", breadcrumb: ["主管", "分销组", "阿里巴巴"], subtitle: "阿里巴巴经营数据", scopeKey: "distribution.alibaba", showCustomers: true },
    { key: "distribution-jushuitan", route: "#/manager/distribution/jushuitan", kind: "dashboard", title: "聚水潭", navLabel: "聚水潭", section: "分销组", breadcrumb: ["主管", "分销组", "聚水潭"], subtitle: "聚水潭经营数据", scopeKey: "distribution.jushuitan", showCustomers: true },
    { key: "private-overall", route: "#/manager/private/overall", kind: "dashboard", title: "私域组", navLabel: "私域组整体", section: "私域组", breadcrumb: ["主管", "私域组"], subtitle: "私域组经营汇总", scopeKey: "private", showCustomers: true },
    { key: "private-youzan-overall", route: "#/manager/private/youzan/overall", kind: "dashboard", title: "有赞整体", navLabel: "有赞整体", section: "私域组", breadcrumb: ["主管", "私域组", "有赞"], subtitle: "有赞店铺经营汇总", scopeKey: "private.youzan", showCustomers: true },
    { key: "private-youzan-qijian", route: "#/manager/private/youzan/qijian", kind: "dashboard", title: "有赞旗舰店", navLabel: "有赞旗舰店", section: "私域组", breadcrumb: ["主管", "私域组", "有赞旗舰店"], subtitle: "有赞旗舰店经营数据", scopeKey: "private.youzan.qijian", showCustomers: true },
    { key: "private-youzan-muying", route: "#/manager/private/youzan/muyinqijian", kind: "dashboard", title: "母婴旗舰店", navLabel: "母婴旗舰店", section: "私域组", breadcrumb: ["主管", "私域组", "母婴旗舰店"], subtitle: "母婴旗舰店经营数据", scopeKey: "private.youzan.muying", showCustomers: true },
    { key: "private-kuaituantuan", route: "#/manager/private/kuaituantuan", kind: "dashboard", title: "快团团", navLabel: "快团团", section: "私域组", breadcrumb: ["主管", "私域组", "快团团"], subtitle: "快团团经营数据", scopeKey: "private.kuaituantuan", showCustomers: true },
    { key: "talent-overall", route: "#/manager/talent/overall", kind: "dashboard", title: "达人组", navLabel: "达人组整体", section: "达人组", breadcrumb: ["主管", "达人组"], subtitle: "达人组经营汇总", scopeKey: "talent", showCustomers: true },
    { key: "talent-weidian", route: "#/manager/talent/weidian", kind: "dashboard", title: "微店", navLabel: "微店", section: "达人组", breadcrumb: ["主管", "达人组", "微店"], subtitle: "微店经营数据", scopeKey: "talent.weidian", showCustomers: true },
    { key: "talent-doudian-overall", route: "#/manager/talent/doudian/overall", kind: "dashboard", title: "抖店整体", navLabel: "抖店整体", section: "达人组", breadcrumb: ["主管", "达人组", "抖店"], subtitle: "抖店经营汇总", scopeKey: "talent.doudian", showCustomers: true },
    { key: "talent-doudian-children", route: "#/manager/talent/doudian/children", kind: "dashboard", title: "儿童服饰旗舰店", navLabel: "儿童服饰旗舰店", section: "达人组", breadcrumb: ["主管", "达人组", "儿童服饰旗舰店"], subtitle: "儿童服饰旗舰店经营数据", scopeKey: "talent.doudian.children", showCustomers: true },
    { key: "talent-doudian-kocotree", route: "#/manager/talent/doudian/kocotree", kind: "dashboard", title: "Kocotree服饰配件店", navLabel: "Kocotree服饰配件店", section: "达人组", breadcrumb: ["主管", "达人组", "Kocotree服饰配件店"], subtitle: "Kocotree服饰配件店经营数据", scopeKey: "talent.doudian.kocotree", showCustomers: true },
    { key: "talent-kuaishou", route: "#/manager/talent/kuaishou", kind: "dashboard", title: "快手小店", navLabel: "快手小店", section: "达人组", breadcrumb: ["主管", "达人组", "快手小店"], subtitle: "快手小店经营数据", scopeKey: "talent.kuaishou", showCustomers: true },
    { key: "settings", route: "#/manager/settings", kind: "settings", title: "主管端设置", navLabel: "主管端设置", section: "系统", breadcrumb: ["主管", "设置"], subtitle: "主管端 AI 大模型相关设置" },
  ],
};

const grainLabels: Record<Grain, string> = { day: "日", week: "周", month: "月", quarter: "季度", half: "半年" };
const customerHealthStatusOrder = ["高活跃", "活跃", "稳定", "观察", "风险", "流失预警", "流失"] as const;
const normalizeHealthRuleGroups = (groups: HealthRuleGroup[]) => groups.map(group => ({
  ...group,
  items: [...group.items].sort((left, right) => customerHealthStatusOrder.indexOf(left.customer_health_status as typeof customerHealthStatusOrder[number]) - customerHealthStatusOrder.indexOf(right.customer_health_status as typeof customerHealthStatusOrder[number])),
}));
const money = (value: string | number) => new Intl.NumberFormat("zh-CN", { style: "currency", currency: "CNY", minimumFractionDigits: 2 }).format(Number(value));
const compactMoney = (value: string | number) => {
  const amount = Number(value);
  if (Math.abs(amount) >= 100000000) return `¥${(amount / 100000000).toFixed(2)}亿`;
  if (Math.abs(amount) >= 10000) return `¥${(amount / 10000).toFixed(1)}万`;
  return `¥${amount.toFixed(0)}`;
};
const dateText = (value?: string | null) => value ? value.replaceAll("-", ".") : "暂无";
const errorText = (error: unknown) => error instanceof Error ? error.message : "请求失败，请稍后重试。";

function Breadcrumbs({ items }: { items: string[] }) {
  return <div className="breadcrumb">{items.map((item, index) => <span key={`${item}-${index}`}>{index > 0 && <b>/</b>}{item}</span>)}</div>;
}

function SectionHeader({ eyebrow, title, action }: { eyebrow: string; title: string; action?: ReactNode }) {
  return <div className="section-header"><div><span>{eyebrow}</span><h2>{title}</h2></div>{action}</div>;
}

function StatusBadge({ status }: { status: string }) {
  return <span className={`status-badge status-${status}`}>{status}</span>;
}

function LoadingPanel({ text = "正在读取数据库数据…" }: { text?: string }) {
  return <div className="panel loading-panel"><i></i><span>{text}</span></div>;
}

function Sidebar({ user, pages, activePage, onNavigate, onLogout }: { user: User; pages: PageConfig[]; activePage: PageConfig; onNavigate: (page: PageConfig) => void; onLogout: () => void }) {
  const sections = useMemo(() => [...new Set(pages.map(page => page.section))], [pages]);
  return (
    <aside className="sidebar">
      <div className="brand"><div className="brand-mark">AI</div><div><strong>客户看板</strong><span>Customer Intelligence</span></div></div>
      <nav aria-label="主导航">
        {sections.map(section => <div className="nav-group" key={section}><div className="nav-section-label">{section}</div>{pages.filter(page => page.section === section && page.section !== "系统").map(page => <button key={page.route} className={`nav-item ${activePage.key === page.key ? "active" : ""}`} onClick={() => onNavigate(page)} aria-current={activePage.key === page.key ? "page" : undefined}><span>{page.navLabel.slice(0, 1)}</span>{page.navLabel}</button>)}</div>)}
      </nav>
      <div className="sidebar-bottom">
        {pages.filter(page => page.section === "系统").map(page => <button key={page.route} className={`nav-item ${activePage.key === page.key ? "active" : ""}`} onClick={() => onNavigate(page)} aria-current={activePage.key === page.key ? "page" : undefined}><span>{page.kind === "upload" ? "⇧" : "⚙"}</span>{page.navLabel}</button>)}
        <div className="user-card"><div className="avatar">{user.display_name.slice(0, 1)}</div><div><strong>{user.display_name}</strong><span>数据库实时连接</span></div><button className="user-logout" onClick={onLogout} title="退出登录" aria-label="退出登录">•••</button></div>
      </div>
    </aside>
  );
}

function SalesPanel({ data, grain, onGrainChange }: { data: DashboardData; grain: Grain; onGrainChange: (grain: Grain) => void }) {
  const series = data.sales_trend.series;
  const max = Math.max(1, ...series.map(item => Number(item.amount)));
  const current = series.at(-1);
  const previous = series.at(-2);
  const change = previous && Number(previous.amount) !== 0 ? (Number(current?.amount || 0) - Number(previous.amount)) / Number(previous.amount) : null;
  return (
    <section className="panel sales-panel">
      <SectionHeader eyebrow="SALES OVERVIEW" title="销售走势" action={<div className="time-tabs">{(["day", "week", "month", "quarter", "half"] as Grain[]).map(item => <button key={item} onClick={() => onGrainChange(item)} className={grain === item ? "active" : ""}>{grainLabels[item]}</button>)}</div>} />
      <div className="chart-summary"><div><strong>{money(current?.amount || 0)}</strong><span>{current?.label || "当前周期"} · 数据库实际交易金额</span></div><div className={`delta ${change !== null && change < 0 ? "negative" : "positive"}`}>{change === null ? "—" : `${change >= 0 ? "↑" : "↓"} ${Math.abs(change * 100).toFixed(2)}%`}</div></div>
      <div className="bar-chart" aria-label={`${grainLabels[grain]}销售趋势图`}>{series.map(item => <div className="bar-column" key={`${item.start}-${item.end}`}><div className="bar-track"><div className="bar-fill" style={{ height: `${Math.max(4, Number(item.amount) / max * 100)}%` }}><span>{compactMoney(item.amount)}</span></div></div><small>{item.label}</small></div>)}</div>
    </section>
  );
}

function HealthPanel({ data }: { data: DashboardData }) {
  const ratio = (data.customer_health.healthy_ratio || 0) * 100;
  return (
    <section className="panel health-panel">
      <SectionHeader eyebrow="CUSTOMER HEALTH" title="自然周客户健康度" action={<span className="period-chip">{dateText(data.customer_health.period.start)}—{dateText(data.customer_health.period.end)}</span>} />
      <div className="health-content"><div className="health-ring"><div><strong>{data.customer_health.total.toLocaleString()}</strong><span>客户总数</span></div></div><div className="health-legend">{data.customer_health.items.map(item => <div key={item.status}><i style={{ background: item.color }}></i><span>{item.status}</span><strong>{item.count.toLocaleString()}</strong></div>)}</div></div>
      <div className="health-foot"><span>健康客户占比</span><strong>{ratio.toFixed(2)}%</strong><div><i style={{ width: `${ratio}%` }}></i></div></div>
    </section>
  );
}

function ProductPanel({ data }: { data: DashboardData }) {
  const [mode, setMode] = useState<"quantity" | "amount">("quantity");
  const list = mode === "quantity" ? data.top_products.by_quantity : data.top_products.by_amount;
  const value = (item: ProductRecord) => Number(mode === "quantity" ? item.quantity : item.amount);
  const max = Math.max(1, ...list.map(value));
  return (
    <section className="panel product-panel">
      <SectionHeader eyebrow="HIGH-FREQUENCY PRODUCTS" title="半年高频商品" action={<div className="mini-tabs"><button className={mode === "quantity" ? "active" : ""} onClick={() => setMode("quantity")}>数量Top5</button><button className={mode === "amount" ? "active" : ""} onClick={() => setMode("amount")}>金额Top5</button></div>} />
      <div className="panel-period">统计周期：{data.top_products.period}</div>
      <div className="product-list">{list.map((item, index) => <div className="product-row" key={item.product_code}><b>{index + 1}</b><div className="product-main"><div><span>{item.product_code}</span><strong>{mode === "quantity" ? `${Number(item.quantity).toLocaleString()} 件` : compactMoney(item.amount)}</strong></div><div className="product-track"><i style={{ width: `${value(item) / max * 100}%` }}></i></div></div></div>)}{list.length === 0 && <div className="empty-state">该周期数据库中没有商品记录</div>}</div>
      <div className="product-note"><span>双榜商品</span><strong>{data.top_products.double_top_count} 种</strong><small>同时进入数量与金额Top5</small></div>
    </section>
  );
}

function RefundPanel({ data, grain, onGrainChange }: { data: DashboardData; grain: Grain; onGrainChange: (grain: Grain) => void }) {
  const allowed: Grain[] = ["week", "month", "quarter", "half"];
  const max = Math.max(1, ...data.refund.series.map(item => Number(item.amount)));
  return (
    <section className="panel operations-card refund-panel">
      <SectionHeader eyebrow="REFUND AMOUNT" title="退款金额分析" action={<div className="time-tabs">{allowed.map(item => <button key={item} className={grain === item ? "active" : ""} onClick={() => onGrainChange(item)}>{grainLabels[item]}</button>)}</div>} />
      <div className="operation-period">统计周期：{data.refund.period} · 数据由后端按当前页面店铺范围聚合</div>
      <div className="operation-kpis"><div><span>所选周期退款金额</span><strong>{money(data.refund.current)}</strong><small>数据库当前周期</small></div><div><span>上一周期退款金额</span><strong>{money(data.refund.previous)}</strong><small>同粒度上一周期</small></div><div><span>较上一周期</span><strong className={data.refund.change !== null && data.refund.change > 0 ? "warning" : "positive"}>{data.refund.change === null ? "—" : `${data.refund.change > 0 ? "+" : ""}${(data.refund.change * 100).toFixed(2)}%`}</strong><small>后端根据两期退款金额计算</small></div></div>
      <div className="refund-trend"><div className="refund-chart">{data.refund.series.map(item => <div key={`${item.start}-${item.end}`}><span>{compactMoney(item.amount)}</span><i><b style={{ height: `${Math.max(4, Number(item.amount) / max * 100)}%` }}></b></i><small>{item.start.slice(2, 7).replace("-", ".")}</small></div>)}</div>{data.refund.series.length === 0 && <div className="refund-empty">数据库中没有对应退款记录</div>}</div>
    </section>
  );
}

function PresalePanel({ data }: { data: DashboardData }) {
  return (
    <section className="panel operations-card presale-panel">
      <SectionHeader eyebrow="PRODUCT PRESALES" title="微店商品预售" />
      <div className="operation-period">统计周期：{data.presale.period} · 仅统计 is_presale = true</div>
      <div className="presale-metrics verified"><div><span>预售交易金额</span><strong>{money(data.presale.amount)}</strong></div><div><span>预售商品数量</span><strong>{Number(data.presale.quantity).toLocaleString()} 件</strong></div><div><span>预售商品种数</span><strong>{data.presale.product_count.toLocaleString()} 种</strong></div></div>
      <div className="presale-table"><div className="presale-table-head"><span>商品编码</span><span>预售数量</span><span>预售交易金额</span></div>{data.presale.products.map(product => <div key={product.product_code}><strong>{product.product_code}</strong><span>{Number(product.quantity).toLocaleString()} 件</span><span>{money(product.amount)}</span></div>)}{data.presale.products.length === 0 && <div className="presale-empty">该周期数据库中没有预售商品记录</div>}</div>
      <div className="presale-foot"><span>数据来源</span><strong>weidian.half_year_product_presales</strong></div>
    </section>
  );
}

function CustomerTable({ scopeKey, asOf, onSelect }: { scopeKey: string; asOf: string; onSelect: (customer: CustomerListItem) => void }) {
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<CustomerListData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    setLoading(true);
    api.customers({ scope_key: scopeKey, as_of: asOf, grain: "half", search: query.trim() || undefined, page, page_size: 20 })
      .then(value => { if (active) { setData(value); setError(""); } })
      .catch(reason => { if (active) setError(errorText(reason)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [scopeKey, asOf, query, page]);
  useEffect(() => setPage(1), [scopeKey, query]);
  return (
    <section className="panel customer-table-panel">
      <SectionHeader eyebrow="CUSTOMER LIST" title={`${data ? `${dateText(data.period.start)}—${dateText(data.period.end)}` : "半年"}客户销售表现`} action={<div className="table-actions"><label><span>⌕</span><input value={query} onChange={event => setQuery(event.target.value)} placeholder="输入客户ID筛选" aria-label="输入客户ID筛选" /></label><span className="readonly-pill">数据库实时查询</span></div>} />
      {error && <div className="api-error-banner">{error}</div>}
      <div className="table-wrap"><table><thead><tr><th>排名</th><th>客户ID / 客户昵称</th><th>店铺</th><th>半年销售额</th><th>拿货次数</th><th>健康度</th><th>状态</th><th></th></tr></thead><tbody>{data?.items.map((customer, index) => <tr key={`${customer.store_key}-${customer.customer_id}`}><td><span className={`rank rank-${index + 1}`}>{(page - 1) * 20 + index + 1}</span></td><td><button className="customer-link" onClick={() => onSelect(customer)}><strong>{customer.customer_id}</strong><span>{customer.display_name || customer.customer_id}</span></button></td><td><span className="customer-store">{customer.store_name}</span></td><td className="amount-cell">{money(customer.period_amount)}</td><td>{customer.purchase_count.toLocaleString()} 次</td><td><div className="score"><span>{customer.score.toFixed(0)}</span><i><b style={{ width: `${Math.max(0, Math.min(100, customer.score))}%` }}></b></i></div></td><td><StatusBadge status={customer.status || "未评分"} /></td><td><button className="arrow-button" onClick={() => onSelect(customer)} aria-label={`查看客户 ${customer.customer_id} 详情`}>→</button></td></tr>)}</tbody></table>{loading && <div className="empty-state">正在从数据库查询客户…</div>}{!loading && data?.items.length === 0 && <div className="empty-state">数据库中没有符合条件的客户</div>}</div>
      <div className="table-footer"><span>共 {data?.pagination.total.toLocaleString() || 0} 条 · 按半年销售额倒序 · 每页20条</span><div><button disabled={!data?.pagination.has_previous} onClick={() => setPage(value => Math.max(1, value - 1))}>‹</button><button className="active">{page}</button><span>/ {data?.pagination.total_pages || 0}</span><button disabled={!data?.pagination.has_next} onClick={() => setPage(value => value + 1)}>›</button></div></div>
    </section>
  );
}

function DashboardPage({ page, onSelect }: { page: PageConfig; onSelect: (customer: CustomerListItem) => void }) {
  const [selectedDate, setSelectedDate] = useState("");
  const [trendGrain, setTrendGrain] = useState<Grain>("month");
  const [refundGrain, setRefundGrain] = useState<Grain>("half");
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    setLoading(true);
    api.dashboard({ scope_key: page.scopeKey!, as_of: selectedDate || undefined, trend_grain: trendGrain, refund_grain: refundGrain })
      .then(value => { if (active) { setData(value); setSelectedDate(current => current || value.as_of); setError(""); } })
      .catch(reason => { if (active) setError(errorText(reason)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [page.scopeKey, selectedDate, trendGrain, refundGrain]);
  const hasPresaleStore = data?.store_keys.includes("weidian") && data.presale.available;
  return (
    <main className="main-content">
      <header className="topbar"><div><Breadcrumbs items={page.breadcrumb} /><h1>{page.title}</h1><p>{page.subtitle}{data ? ` · 当前统计至 ${dateText(data.as_of)}` : ""}</p></div><div className="header-actions"><div className="sync-pill"><i></i>数据更新至 {dateText(data?.latest_data_date)}</div><label className="date-control"><span>统计日期</span><input type="date" value={selectedDate} max={data?.latest_data_date || undefined} onChange={event => setSelectedDate(event.target.value)} aria-label="选择看板统计日期" /></label></div></header>
      {error && <div className="api-error-banner">{error}</div>}
      {loading && !data ? <LoadingPanel /> : data && <>
        <section className="kpi-grid">{data.kpis.map((kpi, index) => <article className={`kpi-card ${index === 0 ? "accent" : ""}`} key={kpi.key}><div className={`kpi-icon ${index === 1 ? "blue" : index === 2 ? "green" : index === 3 ? "purple" : ""}`}>{["¥", "月", "客", "品"][index]}</div><span>{kpi.label}</span><strong>{kpi.key.includes("sales") ? compactMoney(kpi.value) : Number(kpi.value).toLocaleString()}</strong><small className={kpi.change !== null && kpi.change < 0 ? "down" : ""}><b>{kpi.change === null ? "—" : `${kpi.change >= 0 ? "+" : ""}${(kpi.change * 100).toFixed(2)}%`}</b> · {kpi.period}</small></article>)}</section>
        <section className="dashboard-grid"><SalesPanel data={data} grain={trendGrain} onGrainChange={setTrendGrain} /><HealthPanel data={data} /><ProductPanel data={data} /></section>
        <section className={`operations-grid ${hasPresaleStore ? "has-presale" : ""}`}><RefundPanel data={data} grain={refundGrain} onGrainChange={setRefundGrain} />{hasPresaleStore && <PresalePanel data={data} />}</section>
        {page.showCustomers && <CustomerTable scopeKey={page.scopeKey!} asOf={data.as_of} onSelect={onSelect} />}
      </>}
      <footer className="page-footer">AI客户看板 · 数据由 weidian 数据库实时驱动</footer>
    </main>
  );
}

function CustomerDetailPage({ page, target, onBack }: { page: PageConfig; target: { storeKey: string; customerId: string }; onBack: () => void }) {
  const [customer, setCustomer] = useState<CustomerDetailData | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [chat, setChat] = useState<{ role: "user" | "assistant"; content: string }[]>([]);
  const [sending, setSending] = useState(false);
  useEffect(() => {
    let active = true;
    api.customer(target.storeKey, target.customerId).then(value => { if (active) setCustomer(value); }).catch(reason => { if (active) setError(errorText(reason)); });
    return () => { active = false; };
  }, [target.storeKey, target.customerId]);
  const send = async () => {
    if (!customer || !message.trim() || sending) return;
    const userMessage = message.trim();
    const history = chat;
    setChat(items => [...items, { role: "user", content: userMessage }]);
    setMessage("");
    setSending(true);
    try {
      const result = await api.chat({ store_key: customer.store_key, customer_id: customer.customer_id, as_of: customer.as_of, message: userMessage, history });
      setChat(items => [...items, { role: "assistant", content: result.answer }]);
    } catch (reason) {
      setChat(items => [...items, { role: "assistant", content: errorText(reason) }]);
    } finally {
      setSending(false);
    }
  };
  if (error) return <main className="main-content detail-content"><header className="detail-header"><button className="back-button" onClick={onBack}>← 返回客户列表</button></header><div className="api-error-banner">{error}</div></main>;
  if (!customer) return <main className="main-content detail-content"><header className="detail-header"><button className="back-button" onClick={onBack}>← 返回客户列表</button></header><LoadingPanel text="正在读取客户数据库详情…" /></main>;
  const half = customer.dimensions.half;
  const month = customer.dimensions.month;
  return (
    <main className="main-content detail-content">
      <header className="detail-header"><button className="back-button" onClick={onBack}>← 返回客户列表</button><Breadcrumbs items={[...page.breadcrumb, "客户详情"]} /><span className="detail-date">统计截至 {dateText(customer.as_of)}</span></header>
      <section className="customer-hero"><div className="customer-avatar">{(customer.display_name || customer.customer_id).slice(0, 1)}</div><div><div className="hero-title"><h1>{customer.display_name || customer.customer_id}</h1><StatusBadge status={customer.status} /></div><p>客户ID <strong>{customer.customer_id}</strong> · {customer.store_name}</p></div><div className="hero-score"><span>健康度</span><strong>{customer.score.toFixed(0)}</strong><small>/ 100</small></div></section>
      <section className="detail-kpis"><article><span>半年销售额</span><strong>{money(half.sales_amount)}</strong><small>{dateText(half.start)}—{dateText(half.end)}</small></article><article><span>半年拿货次数</span><strong>{half.purchase_count.toLocaleString()} 次</strong><small>数据库周期聚合</small></article><article><span>本月销售额</span><strong>{money(month.sales_amount)}</strong><small>{dateText(month.start)}—{dateText(month.end)}</small></article><article><span>半年主要商品</span><strong>{half.products.length} 种</strong><small>数据库返回 Top {half.products.length}</small></article></section>
      <div className="detail-layout"><section className="detail-data"><CustomerDimensionPanel customer={customer} /></section><aside className="ai-panel"><div className="ai-header"><div className="ai-mark">AI</div><div><strong>客户分析助手</strong><span>基于当前客户数据库数据</span></div><i></i></div><div className="ai-context"><span>正在分析</span><strong>{customer.display_name || customer.customer_id}</strong><small>{customer.status} · 健康度 {customer.score.toFixed(0)}</small></div><div className="chat-list">{chat.map((item, index) => <div key={`${item.role}-${index}`} className={item.role === "user" ? "chat-user" : "chat-ai"}>{item.role === "assistant" && <b>AI</b>}<p>{item.content}</p></div>)}{chat.length === 0 && <div className="chat-ai"><b>AI</b><p>可询问该客户的销售、拿货、健康状态与主要商品。</p></div>}</div><div className="suggestions"><button onClick={() => setMessage("这个客户最近表现怎么样？")}>最近表现</button><button onClick={() => setMessage("主要销售哪些商品？")}>主要商品</button></div><div className="chat-input"><textarea value={message} onChange={event => setMessage(event.target.value)} onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void send(); } }} placeholder="向AI询问这个客户…" aria-label="向AI询问这个客户" /><button onClick={() => void send()} disabled={sending} aria-label="发送消息">{sending ? "…" : "↑"}</button></div><small className="ai-disclaimer">回答上下文来自当前客户的真实数据库记录</small></aside></div>
    </main>
  );
}

function formatFileSize(bytes: number) {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

function UploadBusinessPreview({ preview }: { preview: UploadPreview }) {
  const business = preview.business_preview;
  if (!business) return null;
  const source = business.source_classification;
  const grains = [
    ["weeks", "自然周"],
    ["months", "自然月"],
    ["quarters", "业务季度"],
    ["half_years", "业务半年"],
  ] as const;
  const schemaNames: Record<string, string> = { doudian: "抖店总体", daren: "达人组", siyu: "私域组", fenxiao: "分销组", qudao: "渠道" };
  const isKeyedUpsert = preview.upload_strategy === "upsert_business_keys";
  const strategyLabel = preview.upload_strategy === "replace_existing_dates"
    ? "整日覆盖"
    : isKeyedUpsert
      ? "商品明细新增/更新"
      : "已有日期跳过";
  return (
    <details className="upload-business-preview" open>
      <summary>查看销售、退款与周月联动</summary>
      <div className="upload-source-metrics">
        <span>处理规则 <b>{strategyLabel}</b></span>
        {isKeyedUpsert
          ? <><span>明细新增 <b>{preview.rows_to_insert}</b> 行</span><span>明细更新 <b>{preview.update_rows || 0}</b> 行</span><span>明细不变 <b>{preview.unchanged_rows || 0}</b> 行</span><span>业务键 <b>{preview.order_key_columns?.join(" + ")}</b></span></>
          : <><span>新日期记录 <b>{preview.new_date_rows}</b> 行</span><span>覆盖日期记录 <b>{preview.replacement_date_rows}</b> 行</span></>}
        <span>原始表预计删除 <b>{preview.rows_to_delete}</b> 行</span>
        <span>原始表预计新增 <b>{preview.rows_to_insert}</b> 行</span>
        <span>客户名单预计新增 <b>{preview.new_customer_rows}</b> 行</span>
        <span>有效销售 <b>{source.valid_sales_rows}</b> 行</span>
        <span>退款 <b>{source.refund_rows}</b> 行</span>
        <span>销售且退款 <b>{source.sales_with_refund_rows}</b> 行</span>
        <span>毛销售额 <b>{money(source.gross_sales_amount)}</b></span>
        <span>退款额 <b>{money(source.refund_amount)}</b></span>
        {source.presale_rows !== undefined && <span>预售 <b>{source.presale_rows}</b> 行</span>}
        {source.presale_transaction_amount !== undefined && <span>预售额 <b>{money(source.presale_transaction_amount)}</b></span>}
      </div>
      {grains.map(([grain, label]) => business.store_period_changes[grain]?.map(row => (
        <section className="upload-period-change" key={`${grain}-${row.period_start}`}>
          <header><strong>店铺{label}</strong><span>{dateText(row.period_start)}—{dateText(row.period_end)}</span></header>
          <div className="upload-change-grid">
            <span>销售原值<b>{money(row.current_store_sales_amount)}</b></span>
            <span>文件销售<b>{money(row.file_sales_amount)}</b></span>
            <span>销售预计值<b>{money(row.projected_store_sales_amount)}</b></span>
            <span>退款原值<b>{money(row.current_store_refund_amount)}</b></span>
            <span>文件退款<b>{money(row.file_refund_amount)}</b></span>
            <span>退款预计值<b>{money(row.projected_store_refund_amount)}</b></span>
          </div>
          {row.refund_rule_reclassification_amount !== undefined && Number(row.refund_rule_reclassification_amount) !== 0 && <small>退款口径重算：{money(row.refund_rule_reclassification_amount)}；已计入退款预计值</small>}
          {row.projected_sales_comparison_rate !== undefined && <small>销售环比：{row.current_sales_comparison_rate}% → {row.projected_sales_comparison_rate}%</small>}
        </section>
      )))}
      <div className="upload-cascade-list">
        {Object.entries(business.aggregate_period_changes).map(([schema, changes]) => (
          <section key={schema}>
            <strong>{schemaNames[schema] || schema}</strong>
            {grains.flatMap(([grain, label]) => (changes[grain] || []).map(row => (
              <span key={`${grain}-${row.period_start}`}>{label}销售 {money(row.current_sales_amount)} → {money(row.projected_sales_amount)}；退款 {money(row.current_refund_amount)} → {money(row.projected_refund_amount)}</span>
            )))}
          </section>
        ))}
      </div>
      {preview.refresh && <small className="upload-refresh-count">预计刷新：店铺 {preview.refresh.store_tables.length} 张业务表；上层 {Object.values(preview.refresh.aggregate_tables).reduce((sum, tables) => sum + tables.length, 0)} 张汇总表。</small>}
    </details>
  );
}

function UploadCommitResult({ preview }: { preview: UploadPreview }) {
  const result = preview.write_result;
  if (!result) return null;
  return (
    <details className="upload-commit-result" open>
      <summary>写入成功 · 查看全部受影响表</summary>
      <div className="upload-commit-metrics">
        <span>原始表删除 <b>{result.raw_deleted}</b></span>
        <span>原始表新增 <b>{result.raw_inserted}</b></span>
        <span>原始表更新 <b>{result.raw_updated}</b></span>
        <span>客户新增 <b>{result.customers_inserted}</b></span>
        <span>联动刷新 <b>{result.store_tables_refreshed + result.aggregate_tables_refreshed}</b> 张</span>
        <span>派生表新增 <b>{result.derived_inserted_rows}</b></span>
        <span>派生表更新 <b>{result.derived_updated_rows}</b></span>
        <span>派生表删除 <b>{result.derived_deleted_rows}</b></span>
        <span>实际变化 <b>{result.changed_tables}</b> 张</span>
      </div>
      <div className="upload-table-changes">
        {preview.table_changes?.map(row => (
          <div key={`${row.schema_name}.${row.table_name}`}>
            <strong>{row.schema_name}.{row.table_name}</strong>
            <span>{row.before_rows} → {row.after_rows}</span>
            <small>新增 {row.inserted_rows} · 更新 {row.updated_rows} · 删除 {row.deleted_rows}</small>
          </div>
        ))}
      </div>
    </details>
  );
}

function UploadCard({ store, maxBytes }: { store: StoreOption; maxBytes: number }) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<UploadPreview | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [committing, setCommitting] = useState(false);
  const inputId = `file-${store.key}`;
  const selectFile = (next?: File) => {
    setPreview(null);
    setError("");
    if (!next) return;
    const extension = next.name.split(".").pop()?.toLowerCase();
    if (!['xlsx', 'csv'].includes(extension || "")) return setError("文件格式不支持，请选择 .xlsx 或 .csv 文件");
    if (next.size > maxBytes) return setError(`文件超过 ${formatFileSize(maxBytes)} 限制`);
    setFile(next);
  };
  const checkFile = async () => {
    if (!file) return;
    setLoading(true);
    setError("");
    try { setPreview(await api.uploadPreview(store.key, file)); } catch (reason) { setError(errorText(reason)); } finally { setLoading(false); }
  };
  const commitFile = async () => {
    if (!file || !preview?.commit_available || committing) return;
    const confirmed = window.confirm(
      `确认将“${file.name}”写入${store.name}？\n\n系统将重新校验文件，并在同一个数据库事务中更新原始表、33张店铺派生表以及上层汇总表；任一步失败都会整体回滚。`,
    );
    if (!confirmed) return;
    setCommitting(true);
    setError("");
    try { setPreview(await api.uploadCommit(store.key, file)); } catch (reason) { setError(errorText(reason)); } finally { setCommitting(false); }
  };
  return (
    <article className="upload-card"><div className="upload-card-head"><span>{store.name.slice(0, 1)}</span><div><small>{store.platform_name}</small><h3>{store.name}</h3></div><b>xlsx / csv</b></div><label className={`drop-zone ${preview ? "checked" : file ? "selected" : ""}`} htmlFor={inputId} onDragOver={event => event.preventDefault()} onDrop={event => { event.preventDefault(); selectFile(event.dataTransfer.files[0]); }}><input id={inputId} type="file" accept=".xlsx,.csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv" onChange={event => selectFile(event.target.files?.[0])} /><span className="upload-symbol">⇧</span><strong>{file ? "重新选择文件" : "选择或拖入数据文件"}</strong><small>先预览全部影响，确认后才会写入数据库</small></label>{file ? <div className="selected-file selected"><div><strong>{file.name}</strong><span>{formatFileSize(file.size)}</span></div><small>文件将从当前网页发送到后端校验</small></div> : <div className="upload-placeholder">尚未选择文件</div>}{error && <div className="api-error-banner">{error}</div>}{preview && <><div className={`upload-result ${preview.status === "committed" ? "committed" : ""}`}><strong>{preview.status === "committed" ? "整批写入成功，所有联动表已同步" : "后端校验完成，当前尚未写入数据库"}</strong><span>总行数 {preview.total_rows} · 有效 {preview.valid_rows} · 无日期排除 {preview.invalid_rows}</span>{preview.errors?.slice(0, 3).map(item => <small key={`${item.row}-${item.message}`}>第 {item.row} 行：{item.message}</small>)}</div>{preview.status === "committed" ? <UploadCommitResult preview={preview} /> : <UploadBusinessPreview preview={preview} />}</>}<div className="upload-actions"><button className="ghost-button" onClick={() => { setFile(null); setPreview(null); setError(""); }} disabled={!file || committing}>清除</button><button className="primary-button" onClick={() => void checkFile()} disabled={!file || loading || committing}>{loading ? "后端校验中…" : preview ? "重新校验" : "上传并预览"}</button>{preview?.commit_available && preview.status !== "committed" && <button className="commit-button" onClick={() => void commitFile()} disabled={loading || committing}>{committing ? "整批写入中…" : "确认写入数据库"}</button>}</div></article>
  );
}

function UploadPage({ page }: { page: PageConfig }) {
  const [meta, setMeta] = useState<MetaOptions | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { api.meta().then(setMeta).catch(reason => setError(errorText(reason))); }, []);
  const groups = useMemo(() => {
    const result = new Map<string, StoreOption[]>();
    meta?.stores.forEach(store => result.set(store.platform_name, [...(result.get(store.platform_name) || []), store]));
    return [...result.entries()];
  }, [meta]);
  return (
    <main className="main-content upload-page"><header className="topbar"><div><Breadcrumbs items={page.breadcrumb} /><h1>{page.title}</h1><p>{page.subtitle}</p></div><div className="upload-mode"><i></i>前端上传 · 预览后确认</div></header><div className="upload-notice"><strong>上传说明</strong><span>在当前网页选择 xlsx / csv 文件后先查看完整影响预览。只有已完成原子刷新开发的店铺会显示“确认写入数据库”；写入时任一表失败都会整体回滚。</span></div>{error && <div className="api-error-banner">{error}</div>}{!meta && !error && <LoadingPanel text="正在读取账号可用店铺…" />}{groups.map(([platform, stores]) => <section className="panel upload-platform-section" key={platform}><div className="upload-section-head"><div className="platform-emblem">{platform.slice(0, 1)}</div><div><span>{stores[0].platform_key.toUpperCase()}</span><h2>{platform}</h2></div><small>{stores.length} 个店铺入口</small></div><div className={`upload-card-grid ${stores.length > 1 ? "two" : ""}`}>{stores.map(store => <UploadCard key={store.key} store={store} maxBytes={meta!.upload.max_bytes} />)}</div></section>)}<footer className="page-footer">AI客户看板 · 文件从当前网页上传，预览与正式写入分两步执行</footer></main>
  );
}

function SettingsPage({ page, user }: { page: PageConfig; user: User }) {
  const [ruleGroups, setRuleGroups] = useState<HealthRuleGroup[]>([]);
  const [setting, setSetting] = useState<AiSetting | null>(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState("");
  useEffect(() => {
    if (user.role === "manager") {
      api.aiSetting().then(setSetting).catch(reason => setError(errorText(reason)));
      return;
    }
    Promise.all([api.healthRules(), api.aiSetting()]).then(([health, aiSetting]) => { setRuleGroups(normalizeHealthRuleGroups(health.groups)); setSetting(aiSetting); }).catch(reason => setError(errorText(reason)));
  }, [user.role]);
  const updateRule = (groupKey: string, status: string, field: "state_instructions" | "follow_up_action", value: string) => {
    setSaveMessage("");
    setRuleGroups(groups => groups.map(group => group.group_key !== groupKey ? group : {
      ...group,
      items: group.items.map(rule => rule.customer_health_status === status ? { ...rule, [field]: value } : rule),
    }));
  };
  const editableGroup = ruleGroups.find(group => group.editable);
  const canSave = Boolean(editableGroup?.items.length === 7 && editableGroup.items.every(rule => rule.state_instructions.trim() && rule.follow_up_action.trim()));
  const saveRules = async () => {
    if (!editableGroup || !canSave || saving) return;
    setSaving(true);
    setError("");
    setSaveMessage("");
    try {
      const result = await api.updateHealthRules(editableGroup.items.map(rule => ({
        customer_health_status: rule.customer_health_status,
        state_instructions: rule.state_instructions.trim(),
        follow_up_action: rule.follow_up_action.trim(),
      })));
      const refreshed = await api.healthRules();
      setRuleGroups(normalizeHealthRuleGroups(refreshed.groups));
      const affected = Object.values(result.updated_health_rows).reduce((sum, value) => sum + value, 0);
      setSaveMessage(result.changed_rule_count === 0
        ? "规则内容没有变化，无需同步客户健康度表"
        : `已更新 ${result.changed_statuses.join("、")}，并同步 ${affected.toLocaleString()} 条客户健康度记录`);
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setSaving(false);
    }
  };
  return (
    <main className="main-content settings-page"><header className="topbar"><div><Breadcrumbs items={page.breadcrumb} /><h1>{page.title}</h1><p>{page.subtitle}</p></div>{user.role !== "manager" && <div className="header-actions"><button className="primary-button" disabled={!canSave || saving} onClick={() => void saveRules()}>{saving ? "保存并同步中…" : "保存客户状态规则"}</button></div>}</header>{error && <div className="api-error-banner">{error}</div>}{saveMessage && <div className="settings-save-note">{saveMessage}</div>}{!setting && !error ? <LoadingPanel text={user.role === "manager" ? "正在读取后端设置…" : "正在读取规则配置表与后端设置…"} /> : <section className="settings-grid">{ruleGroups.map(group => <article className="panel settings-card rules-card" key={group.group_key}><SectionHeader eyebrow="CUSTOMER HEALTH RULES" title={`${group.group_name}客户状态规则`} action={<span className="readonly-pill">可编辑</span>} /><p>客户状态及顺序固定；可修改状态说明和建议跟进动作，保存后将同步更新本组组级、平台级及全部店铺级客户健康度表。</p><div className="health-rules-table"><div className="health-rules-head"><span>客户状态</span><span>状态说明</span><span>建议跟进动作</span></div>{group.items.map((rule, index) => <div className="health-rule-row" key={rule.customer_health_status}><div className="rule-status"><strong>{rule.customer_health_status}</strong><small>固定顺序 {index + 1}</small></div><textarea value={rule.state_instructions} onChange={event => updateRule(group.group_key, rule.customer_health_status, "state_instructions", event.target.value)} aria-label={`${group.group_name}${rule.customer_health_status}状态说明`} /><textarea value={rule.follow_up_action} onChange={event => updateRule(group.group_key, rule.customer_health_status, "follow_up_action", event.target.value)} aria-label={`${group.group_name}${rule.customer_health_status}建议跟进动作`} /></div>)}</div></article>)}<article className="panel settings-card ai-config-card"><SectionHeader eyebrow="AI API CONFIG" title="AI 接口设置" /><div className="api-fields"><label><span>api_key</span><input type="password" value={setting?.api_key_masked || ""} readOnly placeholder="后端尚未配置" /></label><label><span>base_url</span><input type="url" value={setting?.base_url || ""} readOnly placeholder="后端尚未配置" /></label><label><span>model_name</span><input value={setting?.model_name || ""} readOnly placeholder="后端尚未配置" /></label></div><div className="api-note"><strong>{setting?.configured ? "后端已配置" : "后端尚未配置"}</strong><span>密钥只保存在后端 .env，浏览器仅接收掩码，不读取明文。</span></div></article></section>}<footer className="page-footer">AI客户看板 · 设置数据来自后端接口</footer></main>
  );
}

function LoginPage({ ready, onLogin }: { ready: boolean; onLogin: (username: string, password: string) => Promise<void> }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!ready || submitting) return;
    setSubmitting(true);
    setError("");
    try { await onLogin(username.trim(), password); } catch (reason) { setError(reason instanceof ApiRequestError && reason.status === 401 ? "账号或密码不正确" : errorText(reason)); } finally { setSubmitting(false); }
  };
  return (
    <main className="login-page"><section className="login-card" aria-labelledby="login-title"><div className="login-brand"><div className="brand-mark">AI</div><div><strong>客户看板</strong><span>Customer Intelligence</span></div></div><div className="login-heading"><span>ACCOUNT ACCESS</span><h1 id="login-title">登录客户看板</h1><p>请输入分配给你的账号和密码，系统将从后端验证并进入对应组别。</p></div><form onSubmit={submit} noValidate><label><span>账号</span><input value={username} onChange={event => { setUsername(event.target.value); setError(""); }} autoComplete="username" placeholder="请输入账号" aria-invalid={Boolean(error)} /></label><label><span>密码</span><input type="password" value={password} onChange={event => { setPassword(event.target.value); setError(""); }} autoComplete="current-password" placeholder="请输入密码" aria-invalid={Boolean(error)} /></label><div className={`login-error ${error ? "visible" : ""}`} role="alert" aria-live="polite">{error || "\u00a0"}</div><button type="submit" disabled={!ready || submitting || !username.trim() || !password}>{!ready ? "正在连接后端…" : submitting ? "登录验证中…" : "登录并进入对应组别"}</button></form><footer><i></i><span>账号由后端独立配置文件管理</span></footer></section></main>
  );
}

function findRoute(pages: PageConfig[], hash: string) {
  for (const page of pages.filter(item => item.kind === "dashboard")) {
    const prefix = `${page.route}/customer/`;
    if (hash.startsWith(prefix)) {
      const [storeKey, customerId] = hash.slice(prefix.length).split("/").map(decodeURIComponent);
      if (storeKey && customerId) return { page, target: { storeKey, customerId } };
    }
  }
  const page = pages.find(item => item.route === hash);
  return page ? { page, target: null } : null;
}

export default function Home() {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const [activePage, setActivePage] = useState<PageConfig | null>(null);
  const [customerTarget, setCustomerTarget] = useState<{ storeKey: string; customerId: string } | null>(null);
  useEffect(() => {
    api.session().then(result => setUser(result.user)).catch(() => setUser(null)).finally(() => setReady(true));
  }, []);
  useEffect(() => {
    if (!ready) return;
    if (!user) {
      setActivePage(null);
      setCustomerTarget(null);
      if (window.location.hash !== "#/login") window.location.hash = "#/login";
      return;
    }
    const pages = pagesByRole[user.role];
    const sync = () => {
      const matched = findRoute(pages, window.location.hash);
      if (!matched) {
        window.location.hash = pages[0].route;
        setActivePage(pages[0]);
        setCustomerTarget(null);
        return;
      }
      setActivePage(matched.page);
      setCustomerTarget(matched.target);
    };
    sync();
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, [ready, user]);
  const login = async (username: string, password: string) => {
    const result = await api.login(username, password);
    setUser(result.user);
    window.location.hash = pagesByRole[result.user.role][0].route;
  };
  const logout = async () => {
    try { await api.logout(); } finally { setUser(null); setActivePage(null); setCustomerTarget(null); window.location.hash = "#/login"; }
  };
  if (!user || !activePage) return <LoginPage ready={ready} onLogin={login} />;
  const pages = pagesByRole[user.role];
  const navigate = (page: PageConfig) => { window.location.hash = page.route; window.scrollTo({ top: 0, behavior: "smooth" }); };
  const selectCustomer = (customer: CustomerListItem) => {
    window.location.hash = `${activePage.route}/customer/${encodeURIComponent(customer.store_key)}/${encodeURIComponent(customer.customer_id)}`;
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  const content = customerTarget ? <CustomerDetailPage page={activePage} target={customerTarget} onBack={() => navigate(activePage)} /> : activePage.kind === "dashboard" ? <DashboardPage key={activePage.route} page={activePage} onSelect={selectCustomer} /> : activePage.kind === "upload" ? <UploadPage page={activePage} /> : <SettingsPage page={activePage} user={user} />;
  return <div className="app-shell"><Sidebar user={user} pages={pages} activePage={activePage} onNavigate={navigate} onLogout={() => void logout()} />{content}</div>;
}
