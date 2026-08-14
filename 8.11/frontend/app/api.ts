export type Role = "talent" | "private" | "distribution" | "manager";
export type Grain = "day" | "week" | "month" | "quarter" | "half";

export type User = {
  id: string;
  username: string;
  display_name: string;
  role: Role;
  group_key: string | null;
};

export type StoreOption = {
  key: string;
  name: string;
  platform_key: string;
  platform_name: string;
  group_key: string;
  group_name: string;
};

export type MetaOptions = {
  role: Role;
  group_key: string | null;
  stores: StoreOption[];
  scopes: { scope_key: string; store_keys: string[] }[];
  grains: Grain[];
  upload: { extensions: string[]; max_bytes: number; can_upload: boolean };
};

export type ProductRecord = { product_code: string; quantity: string; amount: string };

export type DashboardData = {
  scope_key: string;
  store_keys: string[];
  as_of: string;
  latest_data_date: string | null;
  kpis: { key: string; label: string; value: string | number; change: number | null; period: string }[];
  sales_trend: { grain: Grain; series: { start: string; end: string; label: string; amount: string }[] };
  customer_health: {
    period: { start: string; end: string; label: string };
    total: number;
    healthy_count: number;
    healthy_ratio: number | null;
    items: { status: string; count: number; color: string }[];
  };
  top_products: { period: string; by_quantity: ProductRecord[]; by_amount: ProductRecord[]; double_top_count: number };
  refund: {
    grain: Grain;
    current: string;
    previous: string;
    change: number | null;
    period: string;
    series: { start: string; end: string; amount: string }[];
  };
  presale: { available: boolean; period: string; amount: string; quantity: string; product_count: number; products: ProductRecord[] };
};

export type CustomerListItem = {
  store_key: string;
  store_name: string;
  customer_id: string;
  display_name: string;
  period_amount: string;
  purchase_count: number;
  score: number;
  status: string | null;
  risk_reason: string | null;
  suggested_action: string | null;
};

export type CustomerListData = {
  items: CustomerListItem[];
  period: { grain: Grain; start: string; end: string };
  pagination: {
    page: number;
    page_size: number;
    total: number;
    total_pages: number;
    has_previous: boolean;
    has_next: boolean;
  };
};

export type CustomerDimension = {
  start: string;
  end: string;
  sales_amount: string;
  purchase_count: number;
  products: ProductRecord[];
};

export type CustomerDetailData = {
  store_key: string;
  store_name: string;
  customer_id: string;
  display_name: string;
  score: number;
  status: string;
  risk_reason: string | null;
  suggested_action: string | null;
  as_of: string;
  dimensions: Record<Grain, CustomerDimension>;
};

export type HealthRule = {
  id: number;
  customer_health_status: string;
  state_instructions: string;
  follow_up_action: string;
  created_time: string;
  updated_time: string;
};
export type HealthRuleGroup = {
  group_key: "talent" | "private" | "distribution";
  group_name: string;
  editable: boolean;
  items: HealthRule[];
};
export type HealthRuleSaveResult = {
  group_key: string;
  group_name: string;
  updated_rule_count: number;
  changed_rule_count: number;
  changed_statuses: string[];
  updated_health_rows: Record<string, number>;
};
export type AiSetting = { scope_key: string; base_url: string; model_name: string | null; api_key_masked: string; configured: boolean };
export type AiSettingInput = { base_url: string; api_key: string | null; model_name: string | null };
export type AiSettingTestResult = { model_name: string; reply_preview: string };
export type UploadStorePeriodChange = {
  period_start: string;
  period_end: string;
  current_store_sales_amount: string;
  file_sales_amount: string;
  replaced_database_sales_amount: string;
  sales_delta_amount: string;
  projected_store_sales_amount: string;
  current_store_refund_amount: string;
  file_refund_amount: string;
  replaced_database_refund_amount: string;
  refund_rule_reclassification_amount?: string;
  refund_delta_amount: string;
  projected_store_refund_amount: string;
  current_sales_comparison_rate?: string;
  projected_sales_comparison_rate?: string;
};
export type UploadAggregatePeriodChange = {
  table_sales: string;
  table_refunds: string;
  period_start: string;
  period_end: string;
  current_sales_amount: string;
  sales_delta_amount: string;
  projected_sales_amount: string;
  current_refund_amount: string;
  refund_delta_amount: string;
  projected_refund_amount: string;
  current_sales_comparison_rate?: string;
  projected_sales_comparison_rate?: string;
};
export type UploadPreview = {
  id: string;
  store_key: string;
  file_name: string;
  mode: string;
  status: string;
  commit_available?: boolean;
  upload_strategy: "replace_existing_dates" | "skip_existing_dates" | "upsert_business_keys";
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  new_date_rows: number;
  existing_date_rows: number;
  replacement_date_rows: number;
  skipped_existing_date_rows?: number;
  rows_to_delete: number;
  rows_to_insert: number;
  update_rows?: number;
  unchanged_rows?: number;
  order_key_columns?: string[];
  new_customer_rows: number;
  dates: {
    file: string[];
    new: string[];
    existing: string[];
    replacement: string[];
    changed_existing: string[];
  };
  message: string;
  errors: { row: number; message: string }[];
  refresh?: {
    store_tables: string[];
    aggregate_schemas: string[];
    aggregate_tables: Record<string, string[]>;
  };
  business_preview?: {
    source_kind: string;
    source_classification: {
      valid_sales_rows: number;
      refund_rows: number;
      sales_with_refund_rows: number;
      refund_only_rows: number;
      gross_sales_amount: string;
      refund_amount: string;
      presale_rows?: number;
      presale_quantity?: number;
      presale_transaction_amount?: string;
    };
    store_period_changes: Record<string, UploadStorePeriodChange[]>;
    aggregate_period_changes: Record<string, Record<string, UploadAggregatePeriodChange[]>>;
  };
  write_result?: {
    raw_deleted: number;
    raw_inserted: number;
    raw_updated: number;
    customers_inserted: number;
    store_tables_refreshed: number;
    aggregate_tables_refreshed: number;
    changed_tables: number;
    derived_inserted_rows: number;
    derived_updated_rows: number;
    derived_deleted_rows: number;
  };
  table_changes?: {
    schema_name: string;
    table_name: string;
    before_rows: number;
    after_rows: number;
    inserted_rows: number;
    updated_rows: number;
    deleted_rows: number;
  }[];
};

type ApiEnvelope<T> = { code: "OK"; data: T; message: string; errors: unknown[] };
type ApiErrorEnvelope = { code?: string; data?: null; message?: string; errors?: unknown[] };

export class ApiRequestError extends Error {
  status: number;
  code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

function apiBase() {
  const configured = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "");
  if (configured) return configured;
  if (typeof window === "undefined") throw new Error("服务端渲染阶段无法推断后端 API 地址");
  const port = process.env.NEXT_PUBLIC_API_PORT?.trim();
  if (!port) throw new Error("项目根目录 .env 未配置 NEXT_PUBLIC_API_PORT");
  return `${window.location.protocol}//${window.location.hostname}:${port}/api/v1`;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${apiBase()}${path}`, {
    ...init,
    credentials: "include",
    headers: init.body instanceof FormData ? init.headers : { "Content-Type": "application/json", ...init.headers },
  });
  const payload = (await response.json().catch(() => ({}))) as ApiEnvelope<T> | ApiErrorEnvelope;
  if (!response.ok || payload.code !== "OK") {
    throw new ApiRequestError(response.status, payload.code || "REQUEST_FAILED", payload.message || "后端请求失败，请稍后重试。");
  }
  return (payload as ApiEnvelope<T>).data;
}

function queryString(values: Record<string, string | number | undefined | null>) {
  const query = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") query.set(key, String(value));
  });
  return query.toString();
}

export const api = {
  login: (username: string, password: string) => request<{ user: User; expires_at: string }>("/auth/login", { method: "POST", body: JSON.stringify({ username, password }) }),
  session: () => request<{ user: User }>("/auth/session"),
  logout: () => request<null>("/auth/logout", { method: "POST" }),
  meta: () => request<MetaOptions>("/meta/options"),
  dashboard: (values: { scope_key: string; as_of?: string; trend_grain: Grain; refund_grain: Grain }) => request<DashboardData>(`/dashboard?${queryString(values)}`),
  customers: (values: { scope_key: string; as_of?: string; grain?: Grain; search?: string; page?: number; page_size?: number }) => request<CustomerListData>(`/customers?${queryString(values)}`),
  customer: (storeKey: string, customerId: string, asOf?: string) => request<CustomerDetailData>(`/customers/${encodeURIComponent(storeKey)}/${encodeURIComponent(customerId)}?${queryString({ as_of: asOf })}`),
  healthRules: () => request<{ groups: HealthRuleGroup[] }>("/settings/health-rules"),
  updateHealthRules: (rules: Pick<HealthRule, "customer_health_status" | "state_instructions" | "follow_up_action">[]) => request<HealthRuleSaveResult>("/settings/health-rules", { method: "PUT", body: JSON.stringify({ rules }) }),
  aiSetting: () => request<AiSetting>("/settings/ai"),
  testAiSetting: (values: AiSettingInput) => request<AiSettingTestResult>("/settings/ai/test", { method: "POST", body: JSON.stringify(values) }),
  updateAiSetting: (values: AiSettingInput) => request<AiSetting>("/settings/ai", { method: "PUT", body: JSON.stringify(values) }),
  chat: (values: { store_key: string; customer_id: string; as_of: string; message: string; history: { role: "user" | "assistant"; content: string }[] }) => request<{ answer: string; mode: string }>("/ai/chat", { method: "POST", body: JSON.stringify(values) }),
  uploadPreview: (storeKey: string, file: File) => {
    const form = new FormData();
    form.set("store_key", storeKey);
    form.set("mode", "preview");
    form.set("file", file);
    return request<UploadPreview>("/uploads/sales", { method: "POST", body: form });
  },
  uploadCommit: (storeKey: string, file: File) => {
    const form = new FormData();
    form.set("store_key", storeKey);
    form.set("mode", "commit");
    form.set("file", file);
    return request<UploadPreview>("/uploads/sales", { method: "POST", body: form });
  },
};
