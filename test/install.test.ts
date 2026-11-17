import assert from "node:assert/strict";
import { execFileSync, spawn } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

const REPO = new URL("..", import.meta.url).pathname;
const hayJq = existsSync("/usr/bin/jq") || (() => {
  try {
    execFileSync("jq", ["--version"], { stdio: "ignore" });
    return true;
  } catch {
    return false;
  }
})();

test("el instalador hornea SUGIERE_URL y la ruta del plugin en el /sugiere instalado", { skip: !hayJq && "jq no disponible" }, () => {
  const home = mkdtempSync(join(tmpdir(), "consola-inst-"));
  execFileSync("bash", [join(REPO, "install/install.sh")], {
    env: { ...process.env, HOME: home, SUGIERE_URL: "http://127.0.0.1:18099", NEXUS_URL: "" },
  });
  const cmd = readFileSync(join(home, ".claude/commands/sugiere.md"), "utf8");
  assert.match(cmd, /SUGIERE_URL="http:\/\/127\.0\.0\.1:18099"/);
  assert.match(cmd, new RegExp(`node '?${REPO.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}console/sugiere-stop\\.ts`));
  assert.ok(!cmd.includes("__SUGIERE_URL__") && !cmd.includes("__PLUGIN_DIR__"));
  const settings = JSON.parse(readFileSync(join(home, ".claude/settings.json"), "utf8"));
  assert.match(settings.hooks.Stop.at(-1).hooks[0].command, /SUGIERE_URL='http:\/\/127\.0\.0\.1:18099'/);
});

test("sin SUGIERE_URL el comando queda con la URL vacía (el script usa su default)", { skip: !hayJq && "jq no disponible" }, () => {
  const home = mkdtempSync(join(tmpdir(), "consola-inst-"));
  const env: Record<string, string | undefined> = { ...process.env, HOME: home };
  delete env.SUGIERE_URL;
  execFileSync("bash", [join(REPO, "install/install.sh")], { env });
  assert.match(readFileSync(join(home, ".claude/commands/sugiere.md"), "utf8"), /SUGIERE_URL=""/);
});

test("con NEXUS_URL el TTL va en su propio hook Stop y la barra ya no la lleva", { skip: !hayJq && "jq no disponible" }, () => {
  const home = mkdtempSync(join(tmpdir(), "consola-inst-"));
  const env = { ...process.env, HOME: home, NEXUS_URL: "http://127.0.0.1:18098/api/session-routing" };
  execFileSync("bash", [join(REPO, "install/install.sh")], { env });
  execFileSync("bash", [join(REPO, "install/install.sh")], { env }); // idempotente: no duplica
  const settings = JSON.parse(readFileSync(join(home, ".claude/settings.json"), "utf8"));
  const stop = settings.hooks.Stop.flatMap((h: { hooks: Array<{ command: string }> }) => h.hooks.map((c) => c.command));
  assert.equal(stop.filter((c: string) => c.includes("ttl-stop.ts")).length, 1);
  assert.match(stop.find((c: string) => c.includes("ttl-stop.ts")), /NEXUS_URL='http:\/\/127\.0\.0\.1:18098\/api\/session-routing'/);
  assert.doesNotMatch(settings.statusLine.command, /NEXUS_URL/);
});

test("reinstalar para el vigía de esta copia y no una shell que solo nombre su ruta", async () => {
  const ruta = join(REPO, "console/vigia.py");
  const vigia = spawn("sleep", ["60"], { argv0: `python3 ${ruta}`, stdio: "ignore" });
  const shell = spawn("bash", ["-c", `sleep 60 # python3 ${ruta}`], { stdio: "ignore" });
  const muerto = new Promise((ok) => vigia.on("exit", ok));
  try {
    execFileSync("bash", [join(REPO, "install/install.sh")], { env: { ...process.env, HOME: mkdtempSync(join(tmpdir(), "consola-inst-")), NEXUS_URL: "" } });
    await muerto;
    assert.equal(shell.exitCode, null);
    assert.equal(shell.signalCode, null);
  } finally {
    vigia.kill();
    shell.kill();
  }
});
