import { expect, test } from "@playwright/test";

const PASSPHRASE = process.env.E2E_ADMIN_PASSPHRASE ?? "hunter2";

test("playground lemmatizes without exposing a credential", async ({ page }) => {
  await page.goto("/");
  await page.selectOption('select[name="lang"]', "de");
  await page.fill('input[name="text"]', "Häuser");
  await page.click('button[type="submit"]');

  await expect(page.getByRole("cell", { name: "Haus", exact: true })).toBeVisible();

  // The demo key must never reach the browser: not in the DOM, not in cookies.
  const html = await page.content();
  expect(html).not.toMatch(/ls_[A-Za-z0-9]{10,}/);
  const cookies = await page.context().cookies();
  expect(cookies.some((c) => c.value.includes("ls_"))).toBe(false);
});

test("playground shows the equivalent curl", async ({ page }) => {
  await page.goto("/");
  await page.fill('input[name="text"]', "Häuser");
  await page.click('button[type="submit"]');
  await expect(page.getByText("Equivalent request")).toBeVisible();
  await expect(page.locator("pre")).toContainText("/v1/lemmatize");
});

test("japanese sentence highlights with offsets", async ({ page }) => {
  await page.goto("/");
  await page.selectOption('select[name="lang"]', "ja");
  await page.fill('input[name="text"]', "東京都へ行きました");
  await page.click('button[type="submit"]');
  await expect(page.locator("mark").first()).toBeVisible();
});

test("admin cookie is httpOnly and unreadable from scripts", async ({ page, context }) => {
  await page.goto("/login");
  await page.fill('input[name="passphrase"]', PASSPHRASE);
  await page.click('button[type="submit"]');
  await page.waitForURL(/\/keys/);

  const cookies = await context.cookies();
  const admin = cookies.find((c) => c.name === "lemma_admin");
  expect(admin?.httpOnly).toBe(true);

  const readable = await page.evaluate(() => document.cookie);
  expect(readable).not.toContain(admin!.value);
});

test("wrong passphrase is rejected", async ({ page }) => {
  await page.goto("/login");
  await page.fill('input[name="passphrase"]', "definitely-wrong");
  await page.click('button[type="submit"]');
  await expect(page.getByText("Incorrect passphrase.")).toBeVisible();
});

test("a created key is shown once and then gone", async ({ page }) => {
  await page.goto("/login");
  await page.fill('input[name="passphrase"]', PASSPHRASE);
  await page.click('button[type="submit"]');
  await page.waitForURL(/\/keys/);

  await page.fill('input[name="name"]', `e2e-${Date.now()}`);
  await page.click("text=Create key");
  await expect(page.getByText(/will not be shown again/)).toBeVisible();
  const secretText = await page.locator("dd.break-all").first().innerText();
  expect(secretText).toMatch(/^ls_/);

  await page.reload();
  await expect(page.getByText(/will not be shown again/)).toHaveCount(0);
  const html = await page.content();
  expect(html).not.toContain(secretText);
});

test("protected routes redirect to login", async ({ page }) => {
  await page.context().clearCookies();
  await page.goto("/settings");
  await expect(page).toHaveURL(/\/login\?next=%2Fsettings/);
});

test("settings diagnostics are read-only", async ({ page }) => {
  await page.goto("/login");
  await page.fill('input[name="passphrase"]', PASSPHRASE);
  await page.click('button[type="submit"]');
  await page.waitForURL(/\/keys/);
  await page.goto("/settings");
  await expect(page.getByText("read-only")).toBeVisible();
});
