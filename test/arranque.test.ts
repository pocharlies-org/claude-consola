import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { chmodSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { BARRA } from "./vigia-falso.ts";

// Quien lee la barra espera al fin de su salida: arrancar el vigía (que vive horas) no puede dejarla abierta.
test("la barra que arranca el vigía acaba enseguida y no retiene su salida", () => {
  const bin = mkdtempSync(join(tmpdir(), "consola-bin-"));
  // Un vigía de mentira que dura 8 s y se va solo: si la barra retuviera su salida, tardaría eso en volver.
  writeFileSync(join(bin, "python3"), "#!/bin/sh\nexec sleep 8\n");
  chmodSync(join(bin, "python3"), 0o755);
  const t0 = Date.now();
  execFileSync("bash", [BARRA], {
    input: JSON.stringify({ session_id: "s", model: { id: "x" } }),
    env: { ...process.env, PATH: `${bin}:${process.env.PATH}`, XDG_CACHE_HOME: mkdtempSync(join(tmpdir(), "consola-")) },
    encoding: "utf8",
    timeout: 10_000,
  });
  assert.ok(Date.now() - t0 < 5_000);
});
