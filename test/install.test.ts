import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
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
    env: { ...process.env, HOME: home, SUGIERE_URL: "http://127.0.0.1:18099" },
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
