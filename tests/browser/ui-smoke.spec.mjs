import { expect, test } from "@playwright/test";

test("served UI shows the repository answer and evidence", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByText("Repository RAG UI")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "What does this repository research?" }),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "Evidence" })).toBeVisible();
  await expect(page.getByText("README.md")).toBeVisible();
});
