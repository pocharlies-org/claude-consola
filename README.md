# claude-consola

Claude Code en la terminal con lo que ya ves en Paseo. Todo lo visual, sobre el mismo sistema de siempre: la sugerencia
la produce el servicio `sugiere` del clúster (el mismo de la píldora del composer, mismo cuerpo de petición), y la barra
usa las mismas fuentes que las píldoras de Paseo.

- **Barra de estado** (`statusLine`): etiqueta del modelo (🟢 LOCAL / 🔵 ANTHROPIC), TTL de la ruta (🟣 local 🟢 >5 min
  🟡 ≤5 min 🔴 sin caché), descuento nocturno de Alibaba 🌙 (solo con modelo `alibaba-*`), CI del PR de la rama actual
  y CD — lo decide el clúster: Flux si una GitRepository de Flux apunta al repo del `cwd` (🟢 Ready, 🔴 Failed,
  🟡 Reconciling), si no la Application de ArgoCD que lo despliega; de varias apps del mismo repo, la primera que no está
  bien. Cada segmento falla en silencio: sin dato, sin segmento.
- **Nada sondea.** La barra solo pinta lo que dejan los eventos en `~/.cache/claude-consola/<host>` (por host: el home puede ser compartido entre máquinas): el TTL lo lee el hook
  `Stop` una vez por turno y la barra cuenta atrás; CD y CI los escribe el **vigía** (`console/vigia.py`, uno por host,
  lo arranca la barra si no está vivo), que mantiene un watch de Kubernetes sobre las Applications de ArgoCD (y las
  Kustomizations, HelmReleases y GitRepositories de Flux) y una cola en el bus de Synapse con los webhooks de GitHub: con cada evento
  de un repo relee con `gh` la PR de las ramas que la barra está mirando. Sin bus no hay segmento CI.
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

Requiere `jq`, `node` y `bash`; para CI y CD, `python3`. Opcionales —sin ellos, su segmento no aparece—: `kubectl` con
un kubeconfig que pueda hacer `watch` de Applications (CD), y para CI `gh` con sesión, `pika` (`pip install --user pika`)
y la clave del usuario RabbitMQ de pr-watch en `~/.company/synapse/credentials/synapse_pr_watch.rmq.password` (fuera del
clúster, la URL entera en `PR_WATCH_RMQ_URL`).

**URLs por host** — el repo no lleva direcciones de casa; el instalador las hornea en los comandos de los hooks `Stop`
(`SUGIERE_URL` en el de sugiere, `NEXUS_URL` en el del TTL) y en `/sugiere`:

```sh
SUGIERE_URL=https://… NEXUS_URL=https://… bash install/install.sh
```

- `SUGIERE_URL` — el servicio `sugiere` cuando el host no está dentro del clúster (por defecto `http://sugiere.llm.svc:8080`).
- `NEXUS_URL` — el panel de enrutado que lee el hook `Stop` del TTL (sin él no se instala ese hook y la barra no pinta TTL).

## Desarrollo

`npm ci --ignore-scripts && npm run typecheck && npm test && python3 -m unittest discover -s test -p 'test_*.py'`.
CI: `ci.yml` (typecheck, tests de node y del vigía, `bash -n`, `check-internal`) y `duplicados.yml` (estándar de la org).
Diseño y dependencias: [ARCHITECTURE.md](ARCHITECTURE.md).

## Publicación

Como en los demás plugins de la org (patrón `paseo-agentes`): rama + PR contra `main`, CI verde, squash. Los hosts se
actualizan con `git pull` en su clon y volviendo a pasar el instalador, que para el vigía viejo (la barra arranca el
nuevo en el siguiente repintado).

MIT licensed.
