"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { api, type AiQueryContext, type AiQueryResult, type MetaOptions } from "./api";

type AskDashboardDrawerProps = {
  context: AiQueryContext;
  onOpenSettings: () => void;
};

type ChatMessage = { role: "user" | "assistant"; content: string };

const scopeLabels: Record<string, string> = {
  all: "全部业务",
  talent: "达人组",
  "talent.weidian": "微店",
  "talent.doudian": "抖店",
  "talent.doudian.children": "儿童服饰旗舰店",
  "talent.doudian.kocotree": "Kocotree服饰配件店",
  "talent.kuaishou": "快手小店",
  private: "私域组",
  "private.youzan": "有赞",
  "private.youzan.qijian": "有赞旗舰店",
  "private.youzan.muying": "母婴旗舰店",
  "private.kuaituantuan": "快团团",
  distribution: "分销组",
  "distribution.alibaba": "阿里巴巴",
  "distribution.jushuitan": "聚水潭",
};

const grainLabels: Record<string, string> = { day: "日", week: "周", month: "月", quarter: "季度", half: "半年" };
const recommendedQuestions = [
  "本月销售额是多少？",
  "本月哪个店铺销售额下降最多？",
  "最近6个月销售趋势怎么样？",
  "本季度哪个店铺退款额最高？",
  "列出半年销售额最高的10个风险客户。",
  "当前半年金额Top5商品是什么？",
  "哪些店铺的数据日期比较旧？",
];

const errorText = (error: unknown) => error instanceof Error ? error.message : "问看板请求失败，请稍后重试。";

function formatValue(value: unknown, type: string) {
  if (value === null || value === undefined || value === "") return "—";
  if (type === "currency") {
    const number = Number(value);
    return Number.isFinite(number) ? new Intl.NumberFormat("zh-CN", { style: "currency", currency: "CNY", maximumFractionDigits: 2 }).format(number) : String(value);
  }
  if (type === "percentage") {
    const number = Number(value);
    return Number.isFinite(number) ? `${number >= 0 ? "+" : ""}${(number * 100).toFixed(1)}%` : String(value);
  }
  if (type === "number") {
    const number = Number(value);
    return Number.isFinite(number) ? number.toLocaleString("zh-CN") : String(value);
  }
  return String(value);
}

function generatedTime(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });
}

function QueryChart({ chart }: { chart: NonNullable<AiQueryResult["chart"]> }) {
  const values = chart.series.map(item => Number(item.y)).filter(Number.isFinite);
  const chartValue = (value: number) => chart.y_key === "change" || chart.y_key === "contribution"
    ? `${value >= 0 ? "+" : ""}${(value * 100).toFixed(1)}%`
    : value.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
  if (!values.length) return null;
  if (chart.type === "line") {
    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = max - min || 1;
    const width = 520;
    const height = 150;
    const points = chart.series.map((item, index) => {
      const value = Number(item.y);
      const x = chart.series.length === 1 ? width / 2 : 12 + index * ((width - 24) / (chart.series.length - 1));
      const y = height - 15 - ((value - min) / span) * (height - 30);
      return `${x},${y}`;
    }).join(" ");
    return <div className="ask-chart ask-line-chart"><svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="问看板趋势图"><polyline points={points} fill="none" stroke="currentColor" strokeWidth="3" strokeLinejoin="round" strokeLinecap="round" />{points.split(" ").map((point, index) => { const [cx, cy] = point.split(","); return <circle key={`${cx}-${cy}`} cx={cx} cy={cy} r="4" fill="currentColor"><title>{chart.series[index].x}: {chartValue(Number(chart.series[index].y))}</title></circle>; })}</svg><div>{chart.series.map(item => <span key={item.x}>{item.x}</span>)}</div></div>;
  }
  const absoluteMax = Math.max(...values.map(Math.abs), 1);
  return <div className="ask-chart ask-bar-chart">{chart.series.map(item => { const value = Number(item.y); return <div key={item.x}><span title={item.x}>{item.x}</span><i><b className={value < 0 ? "negative" : ""} style={{ width: `${Math.max(Math.abs(value) / absoluteMax * 100, value === 0 ? 0 : 2)}%` }}></b></i><strong>{Number.isFinite(value) ? chartValue(value) : "—"}</strong></div>; })}</div>;
}

export default function AskDashboardDrawer({ context, onOpenSettings }: AskDashboardDrawerProps) {
  const [open, setOpen] = useState(false);
  const [meta, setMeta] = useState<MetaOptions | null>(null);
  const [scopeOverride, setScopeOverride] = useState("");
  const [grainOverride, setGrainOverride] = useState("");
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [result, setResult] = useState<AiQueryResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const requestRef = useRef<AbortController | null>(null);
  const requestVersionRef = useRef(0);

  useEffect(() => {
    let active = true;
    api.meta().then(value => { if (active) setMeta(value); }).catch(() => undefined);
    return () => {
      active = false;
      requestRef.current?.abort();
    };
  }, []);

  const allowedScopes = meta?.scopes || [];
  const selectedScope = allowedScopes.some(item => item.scope_key === scopeOverride)
    ? scopeOverride
    : allowedScopes.some(item => item.scope_key === context.scope_key)
      ? context.scope_key
      : allowedScopes[0]?.scope_key || context.scope_key;
  const selectedGrain = (grainOverride || context.grain) as AiQueryContext["grain"];
  const currentContext = useMemo<AiQueryContext>(() => ({
    scope_key: selectedScope,
    as_of: context.as_of,
    grain: selectedGrain,
    route: context.route,
  }), [selectedScope, selectedGrain, context.as_of, context.route]);

  const close = () => {
    requestRef.current?.abort();
    setOpen(false);
  };

  const ask = async (preset?: string) => {
    const text = (preset || question).trim();
    if (!text || loading) return;
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    const version = ++requestVersionRef.current;
    const history = messages.slice(-6);
    setMessages(items => [...items, { role: "user", content: text }]);
    setQuestion("");
    setLoading(true);
    setError("");
    try {
      const value = await api.aiQuery({ question: text, context: currentContext, history }, controller.signal);
      if (requestVersionRef.current === version) {
        setResult(value);
        setMessages(items => [...items, { role: "assistant", content: value.answer }]);
      }
    } catch (reason) {
      if (!(reason instanceof DOMException && reason.name === "AbortError") && requestVersionRef.current === version) {
        setError(errorText(reason));
      }
    } finally {
      if (requestVersionRef.current === version) setLoading(false);
    }
  };

  const modeLabel = result?.degraded ? "已降级" : result?.mode === "ai" ? "AI 问数" : "规则问数";
  return <>
    <button type="button" className={`ask-dashboard-trigger ${open ? "active" : ""}`} onClick={() => setOpen(true)} aria-haspopup="dialog"><span>AI</span><strong>问看板</strong></button>
    {open && <div className="ask-dashboard-layer">
      <button type="button" className="ask-dashboard-backdrop" onClick={close} aria-label="关闭问看板"></button>
      <aside className="ask-dashboard-drawer" role="dialog" aria-modal="true" aria-labelledby="ask-dashboard-title">
        <header className="ask-drawer-header"><div className="ask-drawer-mark">AI</div><div><span>CONTROLLED ANALYTICS</span><h2 id="ask-dashboard-title">AI 问看板</h2><p>自然语言理解 · 白名单指标 · 数据库证据</p></div>{result && <b className={`ask-mode mode-${result.degraded ? "degraded" : result.mode}`}>{modeLabel}</b>}<button type="button" onClick={close} aria-label="关闭">×</button></header>

        <section className="ask-context-bar">
          <label><span>查询范围</span><select value={selectedScope} onChange={event => setScopeOverride(event.target.value)}>{allowedScopes.map(item => <option key={item.scope_key} value={item.scope_key}>{scopeLabels[item.scope_key] || item.scope_key}</option>)}</select></label>
          <label><span>默认粒度</span><select value={selectedGrain} onChange={event => setGrainOverride(event.target.value)}>{Object.entries(grainLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
          <div><span>统计截止</span><strong>{context.as_of || "范围内最新数据"}</strong></div>
        </section>

        {messages.length === 0 && !result && <section className="ask-welcome"><span>ASK YOUR DASHBOARD</span><h3>直接询问当前权限范围内的经营数据</h3><p>系统先理解问题，再调用固定只读指标工具。AI不能生成SQL，也不会修改数据库。</p><div>{recommendedQuestions.map(item => <button type="button" key={item} onClick={() => void ask(item)}>{item}</button>)}</div></section>}

        {messages.length > 0 && <section className="ask-conversation">{messages.slice(-6).map((item, index) => <div key={`${item.role}-${index}`} className={item.role === "user" ? "ask-user-message" : "ask-ai-message"}>{item.role === "assistant" && <b>AI</b>}<p>{item.content}</p></div>)}</section>}

        {loading && <div className="ask-loading"><i></i><div><strong>正在解析问题并查询指标</strong><span>权限、口径和结果会由后端逐层校验</span></div></div>}
        {error && <div className="ask-error" role="alert"><span>{error}</span><button type="button" onClick={() => setQuestion(messages.filter(item => item.role === "user").at(-1)?.content || "")}>修改问题</button></div>}

        {result && <section className={`ask-result ${loading ? "refreshing" : ""}`}>
          <div className="ask-answer"><span>经营结论</span><h3>{result.answer}</h3><div><small>{scopeLabels[result.scope.scope_key] || result.scope.scope_key}</small><small>截至 {result.scope.as_of}</small><small>{grainLabels[result.scope.grain]}粒度</small><small>{generatedTime(result.generated_at)}</small></div>{!result.configured && <div className="ask-config-cta"><p><strong>当前使用规则问数</strong><span>配置 API Key 后可理解更灵活的表达和连续追问。</span></p><button type="button" onClick={() => { close(); onOpenSettings(); }}>前往 AI 设置</button></div>}</div>

          {result.evidence.length > 0 && <div className="ask-evidence"><div className="ask-section-title"><strong>关键证据</strong><span>{result.query_plan.metric_key}</span></div><div>{result.evidence.map(item => <article key={item.key}><span>{item.label}</span><b>{formatValue(item.value, item.value_type)}</b><small>{item.period}</small><small title={item.source}>{item.source}</small></article>)}</div></div>}

          {result.chart && <div className="ask-chart-panel"><div className="ask-section-title"><strong>{result.chart.type === "line" ? "趋势图" : "对比图"}</strong><span>与下方表格使用同一结果集</span></div><QueryChart chart={result.chart} /></div>}

          {result.table.rows.length > 0 && <div className="ask-table-panel"><div className="ask-section-title"><strong>查询明细</strong><span>{result.table.rows.length} 行</span></div><div className="ask-table-scroll"><table><thead><tr>{result.table.columns.map(column => <th key={column.key}>{column.label}</th>)}</tr></thead><tbody>{result.table.rows.map((row, index) => <tr key={String(row.key || row.customer_id || row.product_code || index)}>{result.table.columns.map(column => <td key={column.key}>{formatValue(row[column.key], column.type)}</td>)}</tr>)}</tbody></table></div></div>}

          {result.warnings.length > 0 && <div className="ask-warnings">{result.warnings.map(warning => <span key={warning}>{warning}</span>)}</div>}
          <footer className="ask-result-footer"><div><span>查询方式：{result.plan_source === "ai" ? "AI意图解析" : "受控模板解析"}</span><span>所有数字来自只读数据库工具</span></div><button type="button" onClick={() => { window.location.hash = result.target.route; close(); }}>在看板中查看</button></footer>
        </section>}

        <footer className="ask-input-area"><textarea value={question} onChange={event => setQuestion(event.target.value)} onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void ask(); } }} placeholder="例如：本月哪个店铺销售额下降最多？" aria-label="向看板提问" /><button type="button" onClick={() => void ask()} disabled={loading || !question.trim()}>{loading ? "…" : "↑"}</button><small>仅支持内部经营指标查询，不执行数据库写操作</small></footer>
      </aside>
    </div>}
  </>;
}
