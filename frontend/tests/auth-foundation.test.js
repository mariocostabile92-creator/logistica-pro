import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
const file = path => readFile(new URL(`../${path}`, import.meta.url), "utf8");

test("login is a real accessible page with remember-me and no public workspaces", async () => {
  const html = await file("login.html");
  for (const text of [
    "Bentornato", "Email aziendale", "Password", "Ricordami",
    "Accedi al workspace", "Crea organizzazione",
  ]) {
    assert.match(html, new RegExp(text, "i"));
  }
  assert.doesNotMatch(html, /Planning|Workforce|Vehicle Library|Fleet Vision/);
  assert.match(html, /autocomplete="username"/);
  assert.match(html, /autocomplete="current-password"/);
});

test("frontend auth separates api state components and session orchestration", async () => {
  const names = ["api", "state", "components", "session"];
  const sources = await Promise.all(names.map(name => file(`assets/js/auth/${name}.js`)));
  names.forEach((name, index) => assert.ok(sources[index].length > 80, name));
  assert.match(sources[0], /credentials: "same-origin"/);
  assert.doesNotMatch(sources.join("\n"), /localStorage|sessionStorage/);
  assert.match(sources[1], /permissions/);
  assert.match(sources[3], /location\.replace\("\/app\/login\.html"\)/);
});

test("registration presents structured validation errors instead of object text", async () => {
  const { authErrorMessage } = await import("../assets/js/auth/api.js");
  assert.equal(authErrorMessage([{
    type: "value_error",
    loc: ["body", "administrator"],
    msg: "Value error, Le password non coincidono.",
  }]), "Le password non coincidono.");
  assert.equal(authErrorMessage([{
    type: "string_too_short",
    loc: ["body", "administrator", "password"],
    ctx: { min_length: 10 },
  }]), "Il campo password deve contenere almeno 10 caratteri.");
  assert.doesNotMatch(authErrorMessage([{}]), /\[object Object\]/);
});

test("administrative bootstrap waits for session before mounting workspaces", async () => {
  const [app, page, session, components] = await Promise.all([
    file("assets/js/app.js"), file("index.html"),
    file("assets/js/auth/session.js"), file("assets/js/auth/components.js"),
  ]);
  assert.match(app, /await requireAdministrativeSession\(\)/);
  assert.match(app, /bootstrapAdministrativeApp/);
  assert.match(page, /authSessionControl/);
  assert.match(session, /auth\/session|requireAdministrativeSession/);
  assert.match(components, /data-auth-logout/);
});

test("login and session UI are responsive and use the existing design tokens", async () => {
  const css = await file("assets/css/auth.css");
  assert.match(css, /var\(--surface\)/);
  assert.match(css, /@media \(max-width: 480px\)/);
  assert.match(css, /width: min\(100%, 440px\)/);
  assert.match(css, /\.auth-login-shell[\s\S]*?grid-template-columns/);
  assert.match(css, /\.auth-card a\.button\.auth-secondary-button[\s\S]*?background: var\(--accent-dark\)/);
  assert.doesNotMatch(css, /var\(--primary\)/);
  assert.doesNotMatch(css, /width:(?:390|768|1440)px/);
});
