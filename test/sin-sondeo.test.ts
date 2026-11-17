import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

// La barra solo pinta lo que dejan los eventos: ni lee el clúster, la forja o el panel, ni guarda cachés por edad.
test("la barra no ejecuta gh, kubectl, flux ni curl, ni caduca cachés por tiempo", () => {
  const codigo = readFileSync(new URL("../statusline/claude-statusline-panel", import.meta.url), "utf8")
    .split("\n")
    .map((l) => l.replace(/(^|\s)#.*$/, "")) // los comentarios pueden nombrarlos
    .join("\n");
  for (const prohibido of [/\bgh\s/, /\bkubectl\b/, /\bflux\s+get\b/, /\bcurl\b/, /\bwget\b/, /-mmin\b/, /\bsleep\b/]) {
    assert.doesNotMatch(codigo, prohibido);
  }
});
