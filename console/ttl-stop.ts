// Hook `Stop`: el TTL de la caché de la ruta se lee una vez por turno —el evento tras el que empieza a correr— y no en cada
// repintado de la barra. Misma fuente que la píldora de Paseo (`$NEXUS_URL/session/{sid}`, el panel de enrutado); la barra
// cuenta atrás desde lo que esto deja en `<estado>/ttl/<sid>`: `<plan> <caduca, epoch s>`, o `<plan> -` sin caché.
// Silencioso por diseño: sin NEXUS_URL, sin sesión o con el panel mudo queda el último valor y la sesión no se bloquea.
import { mkdirSync, renameSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

export const stateDir = () => join(process.env.XDG_CACHE_HOME || join(homedir(), ".cache"), "claude-consola");

/** La línea que lee la barra: el TTL de la cuenta manda sobre el del plan, como en la píldora. */
export function ttlLine(j: { plan?: unknown; plan_ttl?: unknown; claude?: { ttl?: unknown } | null }, nowS: number): string {
  const plan = typeof j.plan === "string" && j.plan ? j.plan : "-";
  const ttl = typeof j.claude?.ttl === "number" ? j.claude.ttl : typeof j.plan_ttl === "number" ? j.plan_ttl : null;
  return `${plan} ${ttl == null ? "-" : Math.round(nowS + ttl)}\n`;
}

async function main(): Promise<void> {
  const trozos: Buffer[] = [];
  for await (const t of process.stdin) trozos.push(t as Buffer);
  const sid = (JSON.parse(Buffer.concat(trozos).toString("utf8") || "{}") as { session_id?: string }).session_id ?? "";
  const base = process.env.NEXUS_URL;
  if (!base || !/^[\w-]+$/.test(sid)) return;
  try {
    const res = await fetch(`${base.replace(/\/+$/, "")}/session/${sid}`, { signal: AbortSignal.timeout(3_000) });
    if (!res.ok) return;
    const dir = join(stateDir(), "ttl");
    mkdirSync(dir, { recursive: true });
    writeFileSync(join(dir, `${sid}.tmp`), ttlLine((await res.json()) as Parameters<typeof ttlLine>[0], Date.now() / 1000));
    renameSync(join(dir, `${sid}.tmp`), join(dir, sid));
  } catch {
    // Panel mudo: la barra se queda con el último valor conocido.
  }
}

if (import.meta.url === `file://${process.argv[1]}`) void main();
