import assert from "node:assert/strict";
import { readFile, stat } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);
const source = (path) => readFile(new URL(path, root), "utf8");
const binary = (path) => readFile(new URL(path, root));

function pngDimensions(buffer) {
  assert.equal(buffer.subarray(1, 4).toString("ascii"), "PNG");
  return {
    width: buffer.readUInt32BE(16),
    height: buffer.readUInt32BE(20),
  };
}

test("official brand assets are local, optimized and dimensioned", async () => {
  const expectations = [
    ["assets/brand/operations-engine-logo.png", 420, 133, 100_000],
    ["assets/brand/operations-engine-mark.png", 192, 134, 30_000],
    ["assets/brand/operations-engine-mark-16.png", 16, 16, 30_000],
    ["assets/brand/operations-engine-mark-32.png", 32, 32, 30_000],
    ["assets/brand/operations-engine-mark-192.png", 192, 192, 30_000],
    ["assets/brand/operations-engine-mark-512.png", 512, 512, 150_000],
  ];
  for (const [path, width, height, maximumBytes] of expectations) {
    const [contents, metadata] = await Promise.all([
      binary(path),
      stat(new URL(path, root)),
    ]);
    assert.deepEqual(pngDimensions(contents), { width, height });
    assert.ok(metadata.size < maximumBytes, `${path} exceeds its asset budget`);
  }
});

test("header, shell and primary workspaces use the official shared brand", async () => {
  const [html, css] = await Promise.all([
    source("index.html"),
    source("assets/css/brand.css"),
  ]);
  assert.match(html, /class="product-brand oe-header-brand"[\s\S]*operations-engine-logo\.png\?v=1/);
  assert.match(html, /appBootstrapShell[\s\S]*class="oe-loading-mark"[\s\S]*operations-engine-mark\.png\?v=1/);
  for (const label of ["Giornata operativa", "Workforce", "Workspace", "Organization", "Operations Academy"]) {
    assert.match(html, new RegExp(`oe-workspace-eyebrow[\\s\\S]{0,300}${label}`));
  }
  assert.match(css, /\.oe-header-brand/);
  assert.match(css, /\.oe-header-brand img\s*\{[\s\S]*height: 38px/);
  assert.match(css, /\.oe-workspace-eyebrow\s*\{[\s\S]*gap: 6px/);
  assert.match(css, /\.oe-workspace-mark\s*\{[\s\S]*width: 16px/);
  assert.doesNotMatch(css, /operations-home-hero[\s\S]{0,120}oe-workspace-mark/);
  assert.doesNotMatch(css, /fleet-sidebar-heading[\s\S]{0,120}oe-workspace-mark/);
  assert.doesNotMatch(html, /oe-workspace-brand/);
  assert.match(css, /@media \(max-width: 620px\)/);
  assert.doesNotMatch(css, /filter\s*:|animation\s*:/);
});

test("Planning keeps the same mark in loading and definitive first paints", async () => {
  const [loading, hero, components] = await Promise.all([
    source("assets/js/modules/planning-operations/renderer.js"),
    source("assets/js/modules/planning-operations/hero.js"),
    source("assets/js/modules/planning-workspace/components.js"),
  ]);
  for (const content of [loading, hero, components]) {
    assert.match(content, /oe-workspace-eyebrow/);
    assert.match(content, /oe-workspace-mark/);
    assert.match(content, /operations-engine-mark\.png\?v=1/);
  }
});

test("authentication and standalone pages expose one coherent accessible identity", async () => {
  const pages = [
    "login.html", "register.html", "bootstrap.html", "offline.html",
    "journal/index.html", "vehicles/index.html",
  ];
  for (const path of pages) {
    const html = await source(path);
    assert.match(html, /brand\.css\?v=2/);
    assert.match(html, /operations-engine-(?:logo|mark)\.png\?v=1/);
    assert.match(html, /operations-engine-mark-(?:16|32)\.png\?v=1/);
    assert.doesNotMatch(html, /(?:src|href)="https?:\/\//);
  }
  for (const path of ["login.html", "register.html", "bootstrap.html", "offline.html", "vehicles/index.html"]) {
    assert.match(await source(path), /alt="Operations Engine"/);
  }
  const journal = await source("journal/index.html");
  assert.match(journal, /alt="" aria-hidden="true"[\s\S]*Giornale di bordo/);
});

test("manifest and favicon use only official mark assets", async () => {
  const [manifestText, html] = await Promise.all([
    source("manifest.webmanifest"),
    source("index.html"),
  ]);
  const manifest = JSON.parse(manifestText);
  assert.equal(manifest.name, "Operations Engine");
  assert.equal(manifest.short_name, "Operations Engine");
  assert.deepEqual(manifest.icons.map((icon) => icon.sizes), ["192x192", "512x512"]);
  assert.ok(manifest.icons.every((icon) => icon.src.includes("/assets/brand/operations-engine-mark-")));
  assert.ok(manifest.icons.every((icon) => icon.type === "image/png" && icon.purpose === "any"));
  assert.match(html, /operations-engine-mark-16\.png\?v=1/);
  assert.match(html, /operations-engine-mark-32\.png\?v=1/);
  assert.match(html, /operations-engine-mark-192\.png\?v=1/);
  assert.match(html, /manifest\.webmanifest\?v=3/);
});

test("brand cache busting reaches the app and lazy Planning loaders", async () => {
  const [html, app, loader, layout, operations] = await Promise.all([
    source("index.html"), source("assets/js/app.js"),
    source("assets/js/modules/workspace-loader.js"),
    source("assets/js/modules/planning-workspace/layout.js"),
    source("assets/js/modules/planning-operations/index.js"),
  ]);
  assert.match(html, /brand\.css\?v=2/);
  assert.match(html, /onboarding\.css\?v=1/);
  assert.match(html, /app\.js\?v=67/);
  assert.match(app, /workspace-loader\.js\?v=67/);
  assert.match(loader, /planning-workspace\/index\.js\?v=6/);
  assert.match(layout, /components\.js\?v=brand2/);
  assert.match(operations, /renderer\.js\?v=brand2/);
});
