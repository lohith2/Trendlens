import { defineConfig, devices } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, "..", "..");
const venvPython = path.join(repoRoot, ".venv", "bin", "python");

// Two servers: the FastAPI backend (seeded throwaway DB + stubbed classifier,
// see serve.py) on :8000, and the Vite dev server on :5173 which proxies
// /api and /uploads to the backend. Tests drive the real UI at :5173.
export default defineConfig({
  testDir: here,
  testMatch: "*.spec.js",
  fullyParallel: false,
  workers: 1, // tests share one seeded DB; the upload test mutates it, runs last
  retries: 0, // retries would re-run mutating tests against already-mutated state
  reporter: process.env.CI ? "github" : "list",
  timeout: 30_000,
  expect: { timeout: 7_000 },
  use: {
    baseURL: "http://localhost:5173",
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: `${venvPython} tests/e2e/serve.py`,
      cwd: repoRoot,
      url: "http://127.0.0.1:8000/api/filters",
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
    {
      command: "npm run dev -- --port 5173 --strictPort",
      cwd: path.join(repoRoot, "app", "frontend"),
      url: "http://localhost:5173",
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
  ],
});
