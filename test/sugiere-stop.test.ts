import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

const SCRIPT = new URL("../console/sugiere-stop.ts", import.meta.url).pathname;
const run = (input: string, env: Record<string, string> = {}) =>
  execFileSync("node", [SCRIPT], { input, encoding: "utf8", env: { ...process.env, SUGIERE_URL: "http://127.0.0.1:1", ...env }, timeout: 30_000 });

test("sin transcript, salida vacía y cero", () => {
  assert.equal(run(JSON.stringify({ session_id: "x" })), "");
});

test("transcript sin modelo real, salida vacía", () => {
  const t = join(mkdtempSync(join(tmpdir(), "sugiere-")), "t.jsonl");
  writeFileSync(t, JSON.stringify({ message: { role: "user", content: "hola" } }) + "\n");
  assert.equal(run(JSON.stringify({ session_id: "x", transcript_path: t })), "");
});

test("servicio inalcanzable: silencio, no error", () => {
  const t = join(mkdtempSync(join(tmpdir(), "sugiere-")), "t.jsonl");
  writeFileSync(
    t,
    [
      JSON.stringify({ message: { role: "user", content: "hola" } }),
      JSON.stringify({ message: { role: "assistant", model: "claude-test", content: [{ type: "text", text: "va" }] } }),
    ].join("\n") + "\n",
  );
  assert.equal(run(JSON.stringify({ session_id: "x", transcript_path: t })), "");
});
