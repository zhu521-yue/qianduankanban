"use client";

import { useEffect, useState } from "react";
import { api, type DashboardInsightData, type Grain } from "./api";

type AiInsightPanelProps = {
  scopeKey: string;
  asOf: string;
  trendGrain: Grain;
  refundGrain: Grain;
  onOpenSettings: () => void;
};

const errorText = (error: unknown) => error instanceof Error ? error.message : "经营洞察加载失败，请稍后重试。";

function generatedTime(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });
}

function evidenceValue(key: string, value: string) {
  if (key === "month_sales" || key === "refund_amount") {
    return new Intl.NumberFormat("zh-CN", { style: "currency", currency: "CNY", maximumFractionDigits: 2 }).format(Number(value));
  }
  return value;
}

export default function AiInsightPanel({ scopeKey, asOf, trendGrain, refundGrain, onOpenSettings }: AiInsightPanelProps) {
  const [result, setResult] = useState<{ requestKey: string; data: DashboardInsightData } | null>(null);
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [settledRequestKey, setSettledRequestKey] = useState("");
  const [failure, setFailure] = useState<{ requestKey: string; message: string } | null>(null);
  const requestKey = `${scopeKey}|${asOf}|${trendGrain}|${refundGrain}|${refreshVersion}`;
  const insight = result?.requestKey === requestKey ? result.data : null;
  const loading = settledRequestKey !== requestKey;
  const error = failure?.requestKey === requestKey ? failure.message : "";

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    api.dashboardInsight(
      { scope_key: scopeKey, as_of: asOf, trend_grain: trendGrain, refund_grain: refundGrain },
      controller.signal,
    )
      .then(value => {
        if (active) {
          setResult({ requestKey, data: value });
          setFailure(null);
        }
      })
      .catch(reason => {
        if (active && !(reason instanceof DOMException && reason.name === "AbortError")) {
          setFailure({ requestKey, message: errorText(reason) });
        }
      })
      .finally(() => {
        if (active) setSettledRequestKey(requestKey);
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [scopeKey, asOf, trendGrain, refundGrain, refreshVersion, requestKey]);

  const modeLabel = insight?.empty ? "数据不足" : insight?.degraded ? "已降级" : insight?.mode === "ai" ? "AI 分析" : "规则摘要";
  return (
    <section className={`panel ai-insight-panel ${insight?.degraded ? "degraded" : ""}`} aria-labelledby="ai-insight-title" aria-busy={loading}>
      <header className="ai-insight-header">
        <div className="ai-insight-heading">
          <div className="ai-insight-mark" aria-hidden="true">AI</div>
          <div><span>BUSINESS INSIGHT</span><h2 id="ai-insight-title">AI 经营洞察</h2><small>结论和建议均有数据库指标作为证据</small></div>
        </div>
        <div className="ai-insight-controls">
          {insight && <span className={`ai-mode-badge mode-${insight.degraded ? "degraded" : insight.mode}`}>{modeLabel}</span>}
          <button type="button" className="ai-refresh-button" disabled={loading} onClick={() => setRefreshVersion(value => value + 1)}>{loading ? "分析中…" : "重新分析"}</button>
        </div>
      </header>

      {loading && !insight && <div className="ai-insight-loading"><i></i><div><strong>正在分析当前经营数据</strong><span>原看板数据会独立加载，不受 AI 请求影响</span></div></div>}
      {error && !insight && <div className="ai-insight-error" role="alert"><span>{error}</span><button type="button" onClick={() => setRefreshVersion(value => value + 1)}>重试</button></div>}

      {insight && <div className={`ai-insight-content ${loading ? "refreshing" : ""}`}>
        <div className="ai-insight-summary">
          <span>核心结论</span>
          <h3>{insight.headline}</h3>
          <p>{insight.summary}</p>
          <div className="ai-insight-meta"><span>统计至 {insight.as_of}</span><span>生成于 {generatedTime(insight.generated_at)}</span></div>
          {!insight.configured && !insight.empty && <div className="ai-config-cta"><div><strong>当前未配置大模型</strong><span>已使用后端规则摘要；配置后将自动增强摘要表达。</span></div><button type="button" onClick={onOpenSettings}>前往 AI 设置</button></div>}
        </div>

        {insight.evidence.length > 0 && <div className="ai-evidence-list">
          <div className="ai-insight-section-title"><span>数据库证据</span><small>最多展示 4 条高信号指标</small></div>
          <div className="ai-evidence-grid">{insight.evidence.map(item => <article className={`ai-evidence-card evidence-${item.direction}`} key={item.key}>
            <div><span>{item.label}</span><b>{evidenceValue(item.key, item.value)}</b></div>
            <p>{item.description}</p>
            <small>{item.period} · {item.source}</small>
          </article>)}</div>
        </div>}

        {insight.actions.length > 0 && <div className="ai-action-list">
          <div className="ai-insight-section-title"><span>建议动作</span><small>仅提供辅助建议，不自动执行</small></div>
          <div>{insight.actions.map((action, index) => <article key={action.title}><b className={`priority-${action.priority}`}>{index + 1}</b><div><strong>{action.title}</strong><span>{action.description}</span></div></article>)}</div>
        </div>}

        {insight.warnings.length > 0 && <div className="ai-insight-warnings">{insight.warnings.map(warning => <span key={warning}>{warning}</span>)}</div>}
      </div>}
    </section>
  );
}
