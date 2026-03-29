export default {
  testDir: ".",
  testMatch: ["ui-smoke.spec.mjs"],
  timeout: 30_000,
  use: {
    baseURL: process.env.REPO_RAG_UI_URL || "http://127.0.0.1:4173",
    browserName: "chromium",
    headless: true,
    screenshot: "only-on-failure",
  },
  reporter: [["list"]],
};
