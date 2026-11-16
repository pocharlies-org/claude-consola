# claude-consola

Claude Code en la terminal con lo que ya ves en Paseo. Todo lo visual, sobre el mismo sistema de siempre: la sugerencia
la produce el servicio `sugiere` del clúster (el mismo de la píldora del composer, mismo cuerpo de petición), y la barra
usa las mismas fuentes que las píldoras de Paseo.

- **Barra de estado** (`statusLine`): etiqueta del modelo (🟢 LOCAL / 🔵 ANTHROPIC), TTL de la ruta (🟣 local 🟢 >5 min
  🟡 ≤5 min 🔴 sin caché), descuento nocturno de Alibaba 🌙 (solo con modelo `alibaba-*`), CI del PR de la rama actual
  y CD — ArgoCD por defecto, Flux si el repo del `cwd` lleva `flux` en el nombre. Cada segmento falla en silencio: sin
  dato, sin segmento.
- **Sugerencia al acabar el turno** (hook `Stop`): si el servicio propone un siguiente mensaje, sale como
  `💡 Sugerencia: …` en el terminal. Silencioso por diseño: servicio mudo, sin turno del asistente o fuera de
  presupuesto → nada, y la sesión no se bloquea.
- **`/sugiere`**: la sugerencia bajo demanda, sin esperar al final del turno.

## Instalación

Se clona en el host y el instalador deja la config de Claude Code apuntando a ese clon. Idempotente: vuelve a
ejecutarlo tras actualizar y no duplica ni toca entradas ajenas.

```sh
git clone https://github.com/pocharlies-org/claude-consola && cd claude-consola
bash install/install.sh
```

Requiere `jq`, `node` y `bash`; `kubectl`/`flux`/`gh` opcionales — sin ellos, su segmento no aparece.

**URLs por host** — el repo no lleva direcciones de casa; el instalador las hornea en el comando de la barra
(`NEXUS_URL`) y en el del hook `Stop` (`SUGIERE_URL`); `/sugiere` no las lleva y usa el entorno de Claude Code:

```sh
SUGIERE_URL=https://… NEXUS_URL=https://… bash install/install.sh
```

- `SUGIERE_URL` — el servicio `sugiere` cuando el host no está dentro del clúster (por defecto `http://sugiere.llm.svc:8080`).
- `NEXUS_URL` — el panel de enrutado para el segmento TTL (sin él, la barra no pinta TTL).

## Desarrollo

`npm ci --ignore-scripts && npm run typecheck && npm test`. CI: `ci.yml` (typecheck, test, `bash -n`, `check-internal`)
y `duplicados.yml` (estándar de la org).

## Publicación

Como en los demás plugins de la org (patrón `paseo-agentes`): rama + PR contra `main`, CI verde, squash. Los hosts se
actualizan con `git pull` en su clon y volviendo a pasar el instalador.

MIT licensed.
