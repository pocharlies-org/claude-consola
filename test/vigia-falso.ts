import { spawn } from "node:child_process";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { hostname, tmpdir } from "node:os";
import { join } from "node:path";
import { after } from "node:test";

export const BARRA = new URL("../statusline/claude-statusline-panel", import.meta.url).pathname;

// Un vigía de mentira (un sleep que se llama como él) para que la barra no arranque uno de verdad durante los tests.
const falso = spawn("sleep", ["300"], { argv0: "python3 /falso/console/vigia.py", stdio: "ignore" });
after(() => falso.kill());

/** Un XDG_CACHE_HOME vacío con el vigía de mentira como vivo; devuelve la raíz y el estado de este host. */
export function cacheVacia(): { cache: string; estado: string } {
  const cache = mkdtempSync(join(tmpdir(), "consola-"));
  const estado = join(cache, "claude-consola", hostname());
  mkdirSync(estado, { recursive: true });
  writeFileSync(join(estado, "vigia.pid"), `${falso.pid}\n`);
  return { cache, estado };
}
