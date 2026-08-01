import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
const file = path => readFile(new URL(`../${path}`, import.meta.url), "utf8");

test("bootstrap wizard is one-time B2B setup without public registration", async () => {
  const [html, script] = await Promise.all([
    file("bootstrap.html"), file("assets/js/auth/bootstrap.js"),
  ]);
  for (const value of ["Nessuna organizzazione configurata", "Nome azienda", "Station principale", "Timezone", "Primo Administrator", "Conferma password", "Crea e accedi"]) assert.match(html, new RegExp(value, "i"));
  assert.doesNotMatch(html, /Registrati|Signup|Google|Microsoft/);
  assert.match(script, /bootstrapStatus/);
  assert.match(script, /location\.replace\("\/app\/"\)/);
});

test("organization settings exposes general users and extensible roles", async () => {
  const page = await file("index.html");
  for (const value of ["Organization Settings", "Generale", "Utenti", "Ruoli", "Nuovo utente", "Operations Manager", "Fleet Manager", "Dispatcher", "Viewer", "Administrator"]) assert.match(page, new RegExp(value));
  assert.match(page, /temporaryPassword/);
  assert.match(page, /name="active"/);
});

test("user management separates api state renderer and orchestration", async () => {
  const names = ["api", "state", "renderer", "index"];
  const sources = await Promise.all(names.map(name => file(`assets/js/organization/${name}.js`)));
  names.forEach((name, index) => assert.ok(sources[index].length > 100, name));
  assert.match(sources[0], /\/api\/organization/);
  assert.doesNotMatch(sources.join("\n"), /localStorage|sessionStorage|window\.prompt|window\.confirm/);
  assert.match(sources[2], /user-status/);
  assert.match(sources[3], /changePassword/);
});

test("bootstrap and organization UI cover mobile tablet and desktop without fixed canvas", async () => {
  const css = await Promise.all([
    file("assets/css/auth-bootstrap.css"), file("assets/css/organization-settings.css"),
    file("assets/css/auth-header-responsive.css"),
  ]).then(parts => parts.join("\n"));
  assert.match(css, /max-width:600px/);
  assert.match(css, /max-width:800px/);
  assert.match(css, /max-width:520px/);
  assert.doesNotMatch(css, /width:(?:390|768|1440)px/);
  assert.match(css, /minmax\(0,1fr\)/);
  assert.match(css, /max-width:1500px/);
});
