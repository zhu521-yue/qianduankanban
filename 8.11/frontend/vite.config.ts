import vinext from "vinext";
import { fileURLToPath } from "node:url";
import { defineConfig, loadEnv } from "vite";

const PROJECT_ROOT = fileURLToPath(new URL("../..", import.meta.url));
const isSandbox = process.env.CODEX_SANDBOX === "seatbelt";

export default defineConfig(({ mode }) => {
  const projectEnv = loadEnv(mode, PROJECT_ROOT, "");
  process.env.WRANGLER_WRITE_LOGS ??= "false";
  process.env.WRANGLER_LOG_PATH ??= ".wrangler/logs";
  process.env.MINIFLARE_REGISTRY_PATH ??= ".wrangler/registry";

  return {
    envDir: PROJECT_ROOT,
    define: {
      "process.env.NEXT_PUBLIC_API_BASE_URL": JSON.stringify(projectEnv.NEXT_PUBLIC_API_BASE_URL ?? ""),
      "process.env.NEXT_PUBLIC_API_PORT": JSON.stringify(projectEnv.NEXT_PUBLIC_API_PORT ?? ""),
    },
    server: {
      host: "127.0.0.1",
      port: 3011,
      ...(isSandbox ? { watch: { useFsEvents: false, usePolling: true } } : {}),
    },
    plugins: [vinext()],
  };
});