const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");

const appUrl = "http://127.0.0.1:8765/app/";
const outputDir = __dirname;
const chromePath = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";

const viewports = [
  { name: "desktop-1440", width: 1440, height: 900 },
  { name: "tablet-768", width: 768, height: 1024 },
  { name: "mobile-390", width: 390, height: 844 },
];

const workspaces = ["home", "operations", "workforce", "fleet"];

function requestPath(url) {
  return new URL(url).pathname;
}

async function inspectWorkspace(page, viewport, workspace) {
  const startedAt = performance.now();
  await page.locator(`[data-workspace-view="${workspace}"]`).first().click();
  await page.waitForFunction(
    (target) => document.body.dataset.activeWorkspace === target,
    workspace,
  );
  const visibleMs = Math.round(performance.now() - startedAt);
  await page.waitForTimeout(500);

  const layout = await page.evaluate(() => {
    const visible = [...document.querySelectorAll("body *")].filter((item) => {
      const style = getComputedStyle(item);
      const rect = item.getBoundingClientRect();
      return style.display !== "none"
        && style.visibility !== "hidden"
        && rect.width > 0
        && rect.height > 0;
    });
    const offenders = visible
      .filter((item) => {
        const rect = item.getBoundingClientRect();
        return rect.left < -1 || rect.right > window.innerWidth + 1;
      })
      .slice(0, 10)
      .map((item) => ({
        tag: item.tagName.toLowerCase(),
        id: item.id,
        className: String(item.className || ""),
        left: Math.round(item.getBoundingClientRect().left),
        right: Math.round(item.getBoundingClientRect().right),
      }));
    return {
      viewportWidth: window.innerWidth,
      documentWidth: document.documentElement.scrollWidth,
      bodyWidth: document.body.scrollWidth,
      horizontalOverflow: document.documentElement.scrollWidth > window.innerWidth,
      offenders,
    };
  });

  const screenshot = path.join(
    outputDir,
    `after-${viewport.name}-${workspace}.png`,
  );
  await page.screenshot({ path: screenshot, fullPage: true });
  return {
    workspace,
    visibleMs,
    settledMs: Math.round(performance.now() - startedAt),
    screenshot,
    layout,
  };
}

async function inspectViewport(browser, viewport) {
  const context = await browser.newContext({
    viewport,
    serviceWorkers: "block",
  });
  const page = await context.newPage();
  const consoleErrors = [];
  const pageErrors = [];
  const failedRequests = [];
  const httpErrors = [];
  const apiRequests = [];

  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("requestfailed", (request) => {
    failedRequests.push({
      method: request.method(),
      path: requestPath(request.url()),
      reason: request.failure()?.errorText || "failed",
    });
  });
  page.on("response", (response) => {
    if (response.status() >= 400) {
      httpErrors.push({
        status: response.status(),
        path: requestPath(response.url()),
      });
    }
  });
  page.on("request", (request) => {
    const pathname = requestPath(request.url());
    if (pathname.startsWith("/api/")) {
      apiRequests.push({ method: request.method(), path: pathname });
    }
  });

  const loadStartedAt = performance.now();
  await page.goto(appUrl, { waitUntil: "domcontentloaded" });
  const domContentLoadedMs = Math.round(performance.now() - loadStartedAt);
  await page.waitForTimeout(700);

  const results = [];
  for (const workspace of workspaces) {
    results.push(await inspectWorkspace(page, viewport, workspace));
  }

  const settledRequestCount = apiRequests.length;
  await page.waitForTimeout(750);
  const requestsAfterSettled = apiRequests.length - settledRequestCount;

  await context.close();
  return {
    viewport,
    domContentLoadedMs,
    workspaces: results,
    consoleErrors,
    pageErrors,
    failedRequests,
    httpErrors,
    apiRequestCount: apiRequests.length,
    apiRequests,
    requestsAfterSettled,
  };
}

async function main() {
  fs.mkdirSync(outputDir, { recursive: true });
  const browser = await chromium.launch({
    headless: true,
    executablePath: chromePath,
  });
  const responsive = [];
  for (const viewport of viewports) {
    responsive.push(await inspectViewport(browser, viewport));
  }
  await browser.close();

  const report = {
    createdAt: new Date().toISOString(),
    url: appUrl,
    responsive,
    passed: responsive.every((item) => (
      item.consoleErrors.length === 0
      && item.pageErrors.length === 0
      && item.failedRequests.length === 0
      && item.requestsAfterSettled === 0
      && item.workspaces.every((workspace) => !workspace.layout.horizontalOverflow)
    )),
  };
  fs.writeFileSync(
    path.join(outputDir, "qa-report.json"),
    JSON.stringify(report, null, 2),
  );
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
