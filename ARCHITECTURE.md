# Arquitectura de claude-consola

Claude Code en la terminal con lo que Paseo enseña en sus píldoras. No es un plugin que cargue Paseo: `install/install.sh`
deja la config de Claude Code del host (`~/.claude/settings.json`, `~/.claude/commands/`) apuntando a esta copia.

## Dónde corre

Cualquier host con Claude Code: el pod de sesiones del clúster y Macs fuera de él. Lo que cambia por host (la URL del
servicio sugiere, la del panel de enrutado) no va en el repo: el instalador lo hornea en los comandos que escribe.

## Componentes

| Componente | Qué hace | Lo dispara |
|---|---|---|
| `statusline/claude-statusline-panel` | Pinta la barra con lo que hay en `~/.cache/claude-consola/<host>` (por host: dos máquinas pueden compartir home). No lee red ni clúster | Claude Code, en cada cambio de la conversación |
| `console/ttl-stop.ts` | Lee el TTL de la ruta del panel (`$NEXUS_URL/session/{sid}`) y deja `ttl/<sid>` = plan y caducidad | Hook `Stop` (una vez por turno) |
| `console/sugiere-stop.ts` | Pide la sugerencia de siguiente mensaje al servicio sugiere | Hook `Stop` y `/sugiere` |
| `console/vigia.py` | El único borde con el clúster y el bus. Uno por host (flock); escribe `cd-<motor>`, `ci/<clave>` y sus `.estado` | Lo arranca la barra si su pid no es un vigía vivo |

## El vigía

- **CD**: un watch de Kubernetes por recurso (`kubectl get --raw …?watch=1`): Applications de ArgoCD; Kustomizations y
  GitRepositories de Flux, unidas por `sourceRef`. Misma semántica que el watch del plugin paseo-argocd: lista inicial por
  `sendInitialEvents` con bookmark de fin, reanuda por `resourceVersion`, un 410 relista y quita lo borrado mientras no
  estaba. Solo escribe cuando cambia lo que pinta la barra: el reconcile que reescribe el objeto no cuenta. Un recurso
  que el clúster no sirve (`NotFound`) deja su motor en `no` y no se reintenta.
- **CI**: una cola exclusiva y auto-delete `pr-watch.consola.<host>.<uuid>` en el exchange `events` de Synapse, enlazada a
  `webhook.github.received` con el usuario RabbitMQ de pr-watch (su permiso es exactamente ese: crear colas `pr-watch.*`
  y enlazar esa clave). Con cada evento de un repo (`pull_request`, `workflow_run`, `check_suite`, `check_run`, `status`)
  relee con `gh pr list` la PR de las ramas de ese repo que la barra mira (`ci/<clave>.rama`, que la barra reescribe en
  cada repintado y el vigía olvida si lleva un día sin pintarse). La primera lectura de una rama la pide la barra con
  `SIGUSR1`; al enlazar la cola se releen todas, porque lo ocurrido con el bus caído no llegó como evento. Una ráfaga de
  eventos de la misma rama se funde en una lectura.
- **Ciclo de vida**: el del host. No sostiene ninguna espera de sesión ni bloquea un turno. Un hilo que muere tumba el
  proceso (`threading.excepthook`), así que la barra ve el pid muerto y arranca otro en vez de pintar un estado
  congelado. Reconectar un stream que el servidor cierra es el propio watch, no un reloj que relee.

## Dependencias

Hacia fuera: el API de Kubernetes (watch de Applications), el bus de Synapse (`events`/`webhook.github.received`), GitHub
por `gh` (solo tras un evento), el panel de enrutado (solo en el `Stop`) y el servicio sugiere. Nadie depende de este
repo. Sin `python3`, `kubectl`, `pika`, `gh` o la clave del bus, su segmento no sale: nunca hay un sondeo de reserva.

## Tests

`npm test` (barra, hooks, instalador y `sin-sondeo.test.ts`, que falla si la barra vuelve a llamar a `gh`, `kubectl`,
`curl` o caduca cachés por edad) y `python3 -m unittest discover -s test -p 'test_*.py'` (vigía con watch y pika falsos).
