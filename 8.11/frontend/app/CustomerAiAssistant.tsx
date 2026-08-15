"use client";

import { useEffect, useState } from "react";
import {
  api,
  type CustomerAnalysisData,
  type CustomerAnalysisEvidence,
  type CustomerAnalysisType,
  type CustomerDetailData,
} from "./api";

type CustomerAiAssistantProps = {
  customer: CustomerDetailData;
  onOpenSettings: () => void;
};

type ChatMessage = { role: "user" | "assistant"; content: string };

const analysisOptions: { type: CustomerAnalysisType; label: string }[] = [
  { type: "overview", label: "综合诊断" },
  { type: "recent_performance", label: "最近表现" },
  { type: "health_reason", label: "健康依据" },
  { type: "products", label: "主要商品" },
  { type: "store_refund", label: "店铺退款" },
  { type: "follow_up", label: "内部跟进" },
];

const errorText = (error: unknown) => error instanceof Error ? error.message : "客户经营诊断加载失败，请稍后重试。";

function evidenceValue(item: CustomerAnalysisEvidence) {
  if (item.value_type === "currency") {
    const value = Number(item.value);
    if (Number.isFinite(value)) return new Intl.NumberFormat("zh-CN", { style: "currency", currency: "CNY", maximumFractionDigits: 2 }).format(value);
  }
  return item.value;
}

function generatedTime(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });
}

export default function CustomerAiAssistant({ customer, onOpenSettings }: CustomerAiAssistantProps) {
  const [analysisType, setAnalysisType] = useState<CustomerAnalysisType>("overview");
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [result, setResult] = useState<{ requestKey: string; data: CustomerAnalysisData } | null>(null);
  const [settledRequestKey, setSettledRequestKey] = useState("");
  const [failure, setFailure] = useState<{ requestKey: string; message: string } | null>(null);
  const [message, setMessage] = useState("");
  const [chat, setChat] = useState<ChatMessage[]>([]);
  const [sending, setSending] = useState(false);
  const requestKey = `${customer.store_key}|${customer.customer_id}|${customer.as_of}|${analysisType}|${refreshVersion}`;
  const analysis = result?.requestKey === requestKey ? result.data : null;
  const loading = settledRequestKey !== requestKey;
  const error = failure?.requestKey === requestKey ? failure.message : "";

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    api.customerAnalysis(
      {
        store_key: customer.store_key,
        customer_id: customer.customer_id,
        as_of: customer.as_of,
        analysis_type: analysisType,
      },
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
  }, [customer.store_key, customer.customer_id, customer.as_of, analysisType, refreshVersion, requestKey]);

  const send = async () => {
    const userMessage = message.trim();
    if (!userMessage || sending) return;
    const history = chat;
    setChat(items => [...items, { role: "user", content: userMessage }]);
    setMessage("");
    setSending(true);
    try {
      const response = await api.chat({
        store_key: customer.store_key,
        customer_id: customer.customer_id,
        as_of: customer.as_of,
        message: userMessage,
        history,
      });
      setChat(items => [...items, { role: "assistant", content: response.answer }]);
    } catch (reason) {
      setChat(items => [...items, { role: "assistant", content: errorText(reason) }]);
    } finally {
      setSending(false);
    }
  };

  const modeLabel = analysis?.degraded ? "已降级" : analysis?.mode === "ai" ? "AI 诊断" : "规则诊断";
  return (
    <aside className={`ai-panel customer-ai-panel ${analysis?.degraded ? "degraded" : ""}`} aria-labelledby="customer-ai-title" aria-busy={loading}>
      <header className="ai-header customer-ai-header">
        <div className="ai-mark">AI</div>
        <div><strong id="customer-ai-title">客户经营助手</strong><span>仅供业务内部分析</span></div>
        {analysis && <b className={`customer-ai-mode mode-${analysis.degraded ? "degraded" : analysis.mode}`}>{modeLabel}</b>}
      </header>

      <div className="ai-context customer-ai-context">
        <span>当前客户</span>
        <strong>{customer.display_name || customer.customer_id}</strong>
        <small>{customer.status} · 健康度 {customer.score.toFixed(0)} · 截至 {customer.as_of}</small>
      </div>

      <div className="customer-ai-tabs" aria-label="客户经营分析类型">
        {analysisOptions.map(option => <button key={option.type} type="button" className={analysisType === option.type ? "active" : ""} onClick={() => setAnalysisType(option.type)}>{option.label}</button>)}
      </div>

      <div className="customer-ai-result">
        {loading && !analysis && <div className="customer-ai-loading"><i></i><span>正在读取客户经营证据并生成诊断…</span></div>}
        {error && !analysis && <div className="customer-ai-error" role="alert"><span>{error}</span><button type="button" onClick={() => setRefreshVersion(value => value + 1)}>重试</button></div>}
        {analysis && <div className={loading ? "refreshing" : ""}>
          <section className="customer-ai-summary">
            <span>经营结论</span>
            <h3>{analysis.conclusion}</h3>
            <p>{analysis.summary}</p>
            <small>生成于 {generatedTime(analysis.generated_at)}</small>
          </section>

          {!analysis.configured && !analysis.empty && <div className="customer-ai-config">
            <div><strong>当前使用后端规则诊断</strong><span>设置 API Key 后，AI 只增强诊断表达，数据库证据和结论边界不变。</span></div>
            <button type="button" onClick={onOpenSettings}>前往 AI 设置</button>
          </div>}

          {analysis.evidence.length > 0 && <section className="customer-ai-evidence">
            <div className="customer-ai-section-title"><strong>数据库证据</strong><span>{analysis.evidence.length} 项</span></div>
            {analysis.evidence.map(item => <article key={item.key} className={`evidence-${item.direction}`}>
              <div><span>{item.label}</span><b>{evidenceValue(item)}</b></div>
              <p>{item.description}</p>
              <small>{item.period} · {item.source}</small>
            </article>)}
          </section>}

          {analysis.actions.length > 0 && <section className="customer-ai-actions">
            <div className="customer-ai-section-title"><strong>内部跟进建议</strong><span>不自动执行</span></div>
            {analysis.actions.map((action, index) => <article key={action.title}><b className={`priority-${action.priority}`}>{index + 1}</b><div><strong>{action.title}</strong><span>{action.description}</span></div></article>)}
          </section>}

          {analysis.warnings.length > 0 && <div className="customer-ai-warnings">{analysis.warnings.map(warning => <span key={warning}>{warning}</span>)}</div>}
        </div>}
      </div>

      <section className="customer-ai-chat">
        <div className="customer-ai-section-title"><strong>内部数据问答</strong><span>基于当前客户</span></div>
        {chat.length > 0 && <div className="chat-list customer-chat-list">{chat.map((item, index) => <div key={`${item.role}-${index}`} className={item.role === "user" ? "chat-user" : "chat-ai"}>{item.role === "assistant" && <b>AI</b>}<p>{item.content}</p></div>)}</div>}
        <div className="chat-input customer-chat-input">
          <textarea value={message} onChange={event => setMessage(event.target.value)} onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void send(); } }} placeholder="询问当前客户的经营数据…" aria-label="询问当前客户的经营数据" />
          <button type="button" onClick={() => void send()} disabled={sending || !message.trim()} aria-label="提交内部数据问题">{sending ? "…" : "↑"}</button>
        </div>
      </section>
      <small className="ai-disclaimer">仅供业务部门内部判断；店铺退款数据不归因到单个客户</small>
    </aside>
  );
}
