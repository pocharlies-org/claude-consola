import assert from "node:assert/strict";
import { execFile, execFileSync, spawn } from "node:child_process";
import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import { hostname, tmpdir } from "node:os";
import { join } from "node:path";
import { after, test } from "node:test";
import { ttlLine } from "../console/ttl-stop.ts";

const HOOK = new URL("../console/ttl-stop.ts", import.meta.url).pathname;
const BARRA = new URL("../statusline/claude-statusline-panel", import.meta.url).pathname;

// Un vigía de mentira (un sleep que se llama como él) para que la barra no arranque uno de verdad durante los tests.
const falso = spawn("sleep", ["300"], { argv0: "python3 /falso/console/vigia.py", stdio: "ignore" });
after(() => falso.kill());

/** Un estado de la consola vacío, con el vigía de mentira como vivo. */
function cacheVacia(): string {
  const cache = mkdtempSync(join(tmpdir(), "consola-ttl-"));
  mkdirSync(join(cache, "claude-consola", hostname()), { recursive: true });
  writeFileSync(join(cache, "claude-consola", hostname(), "vigia.pid"), `${falso.pid}\n`);
  return cache;
}

test("el TTL de la cuenta manda sobre el del plan; sin ninguno, sin caché", () => {
  assert.equal(ttlLine({ plan: "alibaba", plan_ttl: 60, claude: { ttl: 3595 } }, 1000), "alibaba 4595\n");
  assert.equal(ttlLine({ plan: "local", plan_ttl: 300, claude: null }, 1000), "local 1300\n");
  assert.equal(ttlLine({ plan: "claude" }, 1000), "claude -\n");
});

test("el hook Stop lee el panel una vez y deja plan y caducidad donde la barra los lee", async () => {
  const pedidas: string[] = [];
  const panel = createServer((req, res) => {
    pedidas.push(req.url ?? "");
    res.end(JSON.stringify({ plan: "alibaba", plan_ttl: 3595, claude: { ttl: 3595 } }));
  });
  await new Promise<void>((ok) => panel.listen(0, "127.0.0.1", ok));
  const { port } = panel.address() as { port: number };
  const cache = cacheVacia();
  const env = { ...process.env, XDG_CACHE_HOME: cache, NEXUS_URL: `http://127.0.0.1:${port}/api/session-routing` };
  // El panel vive en este proceso: el hook va asíncrono, o el servidor no contestaría.
  await new Promise<void>((ok, ko) => {
    execFile("node", [HOOK], { env }, (e) => (e ? ko(e) : ok())).stdin!.end(JSON.stringify({ session_id: "s-1" }));
  });
  panel.close();
  assert.deepEqual(pedidas, ["/api/session-routing/session/s-1"]);
  const barra = execFileSync("bash", [BARRA], {
    input: JSON.stringify({ session_id: "s-1", model: { id: "claude-test", display_name: "Test" } }),
    env,
    encoding: "utf8",
  });
  assert.match(barra, /🟢 (59m|1h 0m)/);
});

test("la barra no hace red para el TTL: sin fichero, sin segmento; caducado, 🔴", () => {
  const cache = cacheVacia();
  const env = { ...process.env, XDG_CACHE_HOME: cache, NEXUS_URL: "http://127.0.0.1:1" };
  const pinta = () =>
    execFileSync("bash", [BARRA], { input: JSON.stringify({ session_id: "s-2", model: { id: "x" } }), env, encoding: "utf8" });
  assert.doesNotMatch(pinta(), /🔴|🟢|🟡|🟣/);
  mkdirSync(join(cache, "claude-consola", hostname(), "ttl"), { recursive: true });
  writeFileSync(join(cache, "claude-consola", hostname(), "ttl/s-2"), `claude ${Math.round(Date.now() / 1000) - 5}\n`);
  assert.match(pinta(), /🔴 —/);
  writeFileSync(join(cache, "claude-consola", hostname(), "ttl/s-2"), `local ${Math.round(Date.now() / 1000) + 240}\n`);
  assert.match(pinta(), /🟣 4m/);
});
