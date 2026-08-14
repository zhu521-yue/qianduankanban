"use client";

import { useState } from "react";
import type { CustomerDetailData, Grain } from "./api";

const dimensions: { key: Grain; label: string }[] = [
  { key: "day", label: "日" },
  { key: "week", label: "周" },
  { key: "month", label: "月" },
  { key: "quarter", label: "季度" },
  { key: "half", label: "半年" },
];

const schemaByStore: Record<string, string> = {
  weidian: "weidian",
  doudian_children: "doudianChildren",
  doudian_kocotree: "doudianKocotree",
  kuaishou: "kuaishouxiaodian",
  youzan_qijian: "qijian",
  youzan_muying: "muyinqijian",
  kuaituantuan: "kuaituantuan",
  alibaba: "alibaba",
  jushuitan: "jushuitan",
};

const grainTableName: Record<Grain, string> = {
  day: "daily",
  week: "weekly",
  month: "monthly",
  quarter: "quarterly",
  half: "half_year",
};

const money = (value: string | number) => new Intl.NumberFormat("zh-CN", { style: "currency", currency: "CNY", minimumFractionDigits: 2 }).format(Number(value));
const dateText = (value: string) => value.replaceAll("-", ".");

export default function CustomerDimensionPanel({ customer }: { customer: CustomerDetailData }) {
  const [grain, setGrain] = useState<Grain>("half");
  const current = customer.dimensions[grain];
  const schema = schemaByStore[customer.store_key] || customer.store_key;
  const salesSource = `${schema}.customer_${grainTableName[grain]}_sales`;
  const productSource = grain === "week" ? null : `${schema}.customer_${grainTableName[grain]}_product_sales`;

  return (
    <section className="customer-dimension-module">
      <div className="customer-dimension-heading">
        <div><span>CUSTOMER SALES &amp; PURCHASES</span><h2>客户销售与拿货信息</h2><p>{dateText(current.start)}—{dateText(current.end)}</p></div>
        <div className="time-tabs customer-dimension-tabs" aria-label="客户信息时间维度">
          {dimensions.map(item => <button key={item.key} className={grain === item.key ? "active" : ""} onClick={() => setGrain(item.key)} aria-pressed={grain === item.key}>{item.label}</button>)}
        </div>
      </div>
      <div className="customer-dimension-summary">
        <article><span>{dimensions.find(item => item.key === grain)?.label}销售额</span><strong>{money(current.sales_amount)}</strong><small>数据库聚合结果</small></article>
        <article><span>{dimensions.find(item => item.key === grain)?.label}拿货频次</span><strong>{current.purchase_count.toLocaleString()} 次</strong><small>后端按交易记录统计</small></article>
        <article><span>拿货商品</span><strong>{productSource ? `${current.products.length} 种` : "不展示"}</strong><small>{productSource ? `当前返回 Top ${current.products.length}` : "周维度无客户商品表"}</small></article>
      </div>
      {productSource ? <div className="customer-purchase-table">
        <div className="customer-purchase-head"><span>商品编码</span><span>拿货数量</span><span>商品交易金额</span></div>
        {current.products.map(product => <div className="customer-purchase-row" key={`${grain}-${product.product_code}`}><strong>{product.product_code}</strong><span>{Number(product.quantity).toLocaleString()} 件</span><span>{money(product.amount)}</span></div>)}
        {current.products.length === 0 && <div className="empty-state">该周期数据库中没有客户商品记录</div>}
      </div> : <div className="customer-product-disabled"><strong>周维度不使用客户商品表</strong><span>当前维度仅展示客户销售额和拿货频次，商品明细请切换至日、月、季度或半年。</span></div>}
      <div className="customer-dimension-sources"><div><span>销售表</span><strong>{salesSource}</strong><small>金额与拿货次数由后端按客户及周期聚合</small></div><div><span>拿货表</span><strong>{productSource || "不读取客户商品表"}</strong><small>{productSource ? "product_code、数量字段、交易金额字段" : "周维度只读取客户销售表"}</small></div></div>
    </section>
  );
}
