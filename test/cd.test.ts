import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { BARRA, cacheVacia } from "./vigia-falso.ts";

/** La barra en un checkout cuyo origin es `org/app`, con el estado de CD que habría escrito el vigía. */
function cd(estados: Record<string, string>, lineas: Record<string, string>): string {
  const { cache, estado } = cacheVacia();
  for (const [motor, est] of Object.entries(estados)) writeFileSync(join(estado, `cd-${motor}.estado`), `${est}\n`);
  for (const [motor, texto] of Object.entries(lineas)) writeFileSync(join(estado, `cd-${motor}`), texto);
  const repo = mkdtempSync(join(tmpdir(), "consola-repo-"));
  execFileSync("git", ["init", "-q", repo]);
  execFileSync("git", ["-C", repo, "remote", "add", "origin", "git@github.test:org/app.git"]);
  const barra = execFileSync("bash", [BARRA], {
    input: JSON.stringify({ session_id: "s", model: { id: "x" }, workspace: { current_dir: repo } }),
    env: { ...process.env, XDG_CACHE_HOME: cache },
    encoding: "utf8",
  });
  return barra.split("  ·  ").slice(3).join("  ·  "); // solo los segmentos tras etiqueta, modelo y carpeta
}

test("el clúster decide: si Flux despliega el repo sale Flux aunque el nombre no lo diga", () => {
  const argo = "https://github.com/org/app\tapp\tSynced/Healthy\n";
  const flux = "https://github.com/org/app.git\tinfra\tTrue\nhttps://github.com/org/app.git\tapps\tUnknown\n";
  assert.equal(cd({ flux: "ok", argocd: "ok" }, { flux, argocd: argo }), "🟡 apps Reconciling");
  assert.equal(cd({ flux: "no", argocd: "ok" }, { argocd: argo }), "🟢 app Synced/Healthy");
  assert.equal(cd({ flux: "ok", argocd: "ok" }, { flux: "https://github.com/org/otra\tx\tFalse\n", argocd: argo }), "🟢 app Synced/Healthy");
});

test("de varias apps del repo sale la primera que no está bien", () => {
  const flux = "ssh://git@github.test/org/app\ta\tTrue\nssh://git@github.test/org/app\tb\tFalse\n";
  assert.equal(cd({ flux: "ok" }, { flux }), "🔴 b Failed");
  assert.equal(cd({ flux: "ok" }, { flux: "ssh://git@github.test/org/app\ta\tTrue\n" }), "🟢 a Ready");
});

test("watch caído sin app en el otro motor: sin conexión; ninguna app del repo: silencio", () => {
  assert.equal(cd({ flux: "caido Forbidden", argocd: "ok" }, { argocd: "" }), "🟡 flux sin conexión");
  assert.equal(cd({ flux: "no", argocd: "ok" }, { argocd: "" }), "");
});
