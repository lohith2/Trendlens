import { test, expect } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const FIXTURE = path.join(here, "fixtures", "sample.jpg");

// The backend seeds three classified images (serve.py): a denim JACKET by Lia,
// a summer DRESS by Mara, a wool COAT by Lia. Tests run serially against that
// shared, freshly-seeded DB; the only test that changes the grid count
// (upload) is declared last so the read assertions stay deterministic.

test("grid loads the seeded images", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("image-count")).toHaveText("3 images");
  await expect(page.getByTestId("image-card")).toHaveCount(3);
});

test("filter by garment type narrows the grid", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("filter-garment_type").selectOption("dress");
  await expect(page.getByTestId("image-card")).toHaveCount(1);
  await expect(page.getByTestId("image-card")).toContainText("dress");
});

test("filter by designer narrows the grid", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("filter-designer").selectOption("Lia");
  await expect(page.getByTestId("image-card")).toHaveCount(2);
});

test("full-text search matches the description", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("searchbox").fill("denim");
  await expect(page.getByTestId("image-card")).toHaveCount(1);
  await expect(page.getByTestId("image-card")).toContainText("jacket");
});

test("open detail and add a designer annotation", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("filter-garment_type").selectOption("dress");
  await page.getByTestId("image-card").first().click();

  const panel = page.getByTestId("detail-panel");
  await expect(panel).toBeVisible();
  await expect(panel.getByText("No annotations yet.")).toBeVisible();

  await panel.getByRole("textbox").fill("runway favorite");
  await panel.getByRole("button", { name: "Add" }).click();

  await expect(panel.getByText("runway favorite")).toBeVisible();
  await expect(panel.getByText("No annotations yet.")).toHaveCount(0);
});

test("upload a photo and see it classified into the grid", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("image-card")).toHaveCount(3);

  await page.getByRole("button", { name: "Upload" }).click();
  await page.getByTestId("upload-file").setInputFiles(FIXTURE);
  await page.getByTestId("upload-submit").click();

  await expect(page.getByTestId("image-count")).toHaveText("4 images");
  await expect(page.getByTestId("image-card")).toHaveCount(4);
  await expect(
    page.getByText("an uploaded ribbed cotton top"),
  ).toBeVisible();
});
