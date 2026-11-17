#!/usr/bin/env python3
"""vigia.py — el único borde de la barra con lo que cambia fuera de la sesión: CD y CI llegan por eventos, nadie sondea.

Uno por host (flock en <estado>/vigia.lock; <estado> = ~/.cache/claude-consola/<host>); lo arranca la barra cuando no está vivo y no tiene más ciclo de vida que el host.
- CD: un watch de Kubernetes por recurso — Applications de ArgoCD; Kustomizations, HelmReleases y GitRepositories de Flux — como el de
  paseo-argocd: lista inicial por sendInitialEvents con bookmark de fin, reanuda por resourceVersion, 410 relista. Escribe
  <estado>/cd-<motor> (`<url del repo>\t<app>\t<estado>` por app) solo cuando cambia lo que pinta la barra, y
  <estado>/cd-<motor>.estado: `ok`, `caido <por qué>` o `no` (sin kubectl o el clúster no sirve ese recurso).
- CI: una cola propia en el bus de Synapse (`webhook.github.received`, la misma entrada de GitHub que despierta al
  supervisor) con el usuario de pr-watch. Con cada evento de un repo relee con gh la PR de las ramas de ese repo que la
  barra está mirando (<estado>/ci/<clave>.rama) y la deja en <estado>/ci/<clave>; <estado>/ci.estado dice si hay bus.
  La primera lectura de una rama la pide la barra con SIGUSR1. Sin bus no hay CI: la barra no la pinta, no la sondea.
Reconectar un stream que se cierra (el API server y el broker los cortan) es el propio watch, no un reloj que relee.
"""
from __future__ import annotations  # el python3 de Cloudblue es 3.9: las uniones `X | None` de las firmas no se evalúan

import fcntl
import json
import os
import signal
import socket
import subprocess
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import quote

# Por host: el home puede estar compartido entre máquinas (dos pods con el mismo volumen), el vigía y su estado no.
ESTADO = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "claude-consola" / socket.gethostname()
CREDENCIAL = Path("~/.company/synapse/credentials/synapse_pr_watch.rmq.password").expanduser()
INTERES_S = 86_400  # una rama que la barra no pinta en un día deja de releerse
REINTENTO_MAX_S = 30

RECURSOS = {
    "argocd": {"app": "/apis/argoproj.io/v1alpha1/namespaces/argocd/applications"},
    "flux": {
        "ks": "/apis/kustomize.toolkit.fluxcd.io/v1/kustomizations",
        "hr": "/apis/helm.toolkit.fluxcd.io/v2/helmreleases",
        "git": "/apis/source.toolkit.fluxcd.io/v1/gitrepositories",
    },
}


def escribe(ruta: Path, texto: str) -> None:
    tmp = ruta.with_name(f".{ruta.name}.{os.getpid()}.{threading.get_ident()}")
    tmp.write_text(texto)
    os.replace(tmp, ruta)


# ---------------------------------------------------------------- CD


def lineas(motor: str, objetos: dict) -> str:
    """Lo que pinta la barra de cada app, ordenado por nombre: solo esto cuenta como cambio (cada reconcile reescribe el objeto)."""
    filas = []
    if motor == "argocd":
        for nombre, o in objetos["app"].items():
            st = o.get("status") or {}
            estado = f"{(st.get('sync') or {}).get('status') or '?'}/{(st.get('health') or {}).get('status') or '?'}"
            filas.append((nombre, ((o.get("spec") or {}).get("source") or {}).get("repoURL") or "", estado))
    else:
        # Flux despliega un repo con Kustomizations (spec.sourceRef) o con HelmReleases cuyo chart sale de él (spec.chart.spec.sourceRef).
        urls = {k: ((o.get("spec") or {}).get("url") or "") for k, o in objetos["git"].items()}
        desplegados = [(k, o, (o.get("spec") or {}).get("sourceRef")) for k, o in objetos["ks"].items()]
        desplegados += [(k, o, (((o.get("spec") or {}).get("chart") or {}).get("spec") or {}).get("sourceRef"))
                        for k, o in objetos["hr"].items()]
        for (ns, nombre), o, ref in desplegados:
            ref = ref or {}
            url = urls.get((ref.get("namespace") or ns, ref.get("name"))) if ref.get("kind") == "GitRepository" else None
            listo = [c for c in (o.get("status") or {}).get("conditions") or [] if c.get("type") == "Ready"]
            filas.append((nombre, url or "", listo[0].get("status", "Unknown") if listo else "Unknown"))
    return "".join(f"{url}\t{nombre}\t{estado}\n" for nombre, url, estado in sorted(filas))


def abre_kubectl(ruta: str, consulta: str):
    """Un watch: devuelve el proceso (stdout = un evento JSON por línea)."""
    return subprocess.Popen(["kubectl", "get", "--raw", f"{ruta}?{consulta}"], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)


class Motor:
    """Los watches de un motor (ArgoCD o Flux) y el fichero que la barra lee de él."""

    def __init__(self, motor: str, abre=abre_kubectl, espera=time.sleep):
        self.motor, self.abre, self.espera = motor, abre, espera
        self.objetos = {tipo: {} for tipo in RECURSOS[motor]}
        self.caidos: dict[str, str] = {}
        self.ausentes: set[str] = set()  # recursos que este clúster no sirve (o no hay kubectl): cuentan como listados y vacíos
        self.listados: set[str] = set()
        self.cerrojo = threading.Lock()
        self.escrito = self.estado = None

    def _publica(self) -> None:
        # Hasta que cada recurso haya listado, la barra no ve nada: un join a medias pintaría apps sin repo.
        with self.cerrojo:
            if self.ausentes == set(self.objetos):
                estado = "no"
            elif self.caidos:
                estado = f"caido {next(iter(self.caidos.values()))}"
            elif self.listados | self.ausentes == set(self.objetos):
                estado = "ok"
                texto = lineas(self.motor, self.objetos)
                if texto != self.escrito:
                    escribe(ESTADO / f"cd-{self.motor}", texto)
                    self.escrito = texto
            else:
                return
            if estado != self.estado:
                escribe(ESTADO / f"cd-{self.motor}.estado", estado + "\n")
                self.estado = estado

    def vigila(self, tipo: str) -> None:
        ruta, vistos, reanuda, fallos = RECURSOS[self.motor][tipo], self.objetos[tipo], None, 0
        while True:  # cada vuelta es un stream nuevo cuando el anterior se cerró, no una relectura
            desde = f"&resourceVersion={quote(reanuda)}" if reanuda else "&sendInitialEvents=true&resourceVersionMatch=NotOlderThan"
            try:
                proc = self.abre(ruta, f"watch=1&allowWatchBookmarks=true{desde}")
            except FileNotFoundError:
                self.ausentes.add(tipo)
                return self._publica()
            nuevos: set = set()
            for texto in proc.stdout:
                try:
                    evento = json.loads(texto)
                except ValueError:
                    continue
                o = evento.get("object") or {}
                if evento.get("type") == "ERROR":
                    if o.get("code") == 410:
                        reanuda = None  # demasiado viejo para reanudar: lista otra vez
                    continue
                fallos = 0
                meta = o.get("metadata") or {}
                reanuda = meta.get("resourceVersion") or reanuda
                clave = meta.get("name") if self.motor == "argocd" else (meta.get("namespace"), meta.get("name"))
                if evento.get("type") in ("ADDED", "MODIFIED"):
                    nuevos.add(clave)
                    vistos[clave] = o
                elif evento.get("type") == "DELETED":
                    vistos.pop(clave, None)
                elif evento.get("type") == "BOOKMARK":
                    if (meta.get("annotations") or {}).get("k8s.io/initial-events-end") == "true":
                        for viejo in set(vistos) - nuevos:  # borrado mientras el watch no estaba
                            vistos.pop(viejo)
                        self.listados.add(tipo)
                    else:
                        continue
                self.caidos.pop(tipo, None)
                self._publica()
            error = (proc.stderr.read() if proc.stderr else "").strip()
            proc.wait()
            if "NotFound" in error and tipo not in self.listados:
                self.ausentes.add(tipo)  # este clúster no sirve el recurso (Flux sin helm-controller, o sin Flux)
                return self._publica()
            self.caidos[tipo] = (error.splitlines() or ["el watch se cerró"])[-1][:120]
            self._publica()
            fallos += 1
            self.espera(min(REINTENTO_MAX_S, 0.5 * 2 ** fallos))


# ---------------------------------------------------------------- CI


def ramas(mensaje: dict) -> tuple[str, set[str] | None]:
    """Repo y ramas de un evento de GitHub del bus (sobre del gateway: {headers, body}); None = todas las del repo."""
    cuerpo = mensaje.get("body") or {}
    evento = (mensaje.get("headers") or {}).get("x-github-event") or ""
    repo = ((cuerpo.get("repository") or {}).get("full_name") or "").lower()
    if evento == "pull_request":
        return repo, {((cuerpo.get("pull_request") or {}).get("head") or {}).get("ref")}
    if evento in ("workflow_run", "check_suite"):
        return repo, {(cuerpo.get(evento) or {}).get("head_branch")}
    if evento == "check_run":
        return repo, {(((cuerpo.get("check_run") or {}).get("check_suite")) or {}).get("head_branch")}
    if evento == "status":
        return repo, {b.get("name") for b in cuerpo.get("branches") or []} or None
    return "", set()


def interesados(repo: str | None, cuales: set[str] | None) -> set[tuple[Path, str, str]]:
    """Las ramas que la barra mira de `repo` (None = todos los repos); las que no pinta hace un día se olvidan aquí."""
    fuera = time.time() - INTERES_S
    hallados = set()
    for f in (ESTADO / "ci").glob("*.rama"):
        try:
            r, rama = f.read_text().split()[:2]
            viejo = f.stat().st_mtime < fuera
        except (OSError, ValueError):
            continue
        if viejo:
            f.unlink(missing_ok=True)
            f.with_suffix("").unlink(missing_ok=True)
        elif (repo is None or r.lower() == repo) and (cuales is None or rama in cuales):
            hallados.add((f.with_suffix(""), r, rama))
    return hallados


def lee_gh(destino: Path, repo: str, rama: str) -> None:
    try:
        out = subprocess.run(["gh", "pr", "list", "--repo", repo, "--head", rama, "--json", "number,state,statusCheckRollup"],
                             capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return
    if out.returncode == 0:
        escribe(destino, out.stdout)  # si gh falla queda lo último leído: el siguiente evento lo corrige


class Relector:
    """Un hilo que relee con gh; los eventos de una ráfaga sobre la misma rama se funden en una lectura."""

    def __init__(self, lee=lee_gh):
        self.lee, self.pendientes, self.aviso = lee, set(), threading.Condition()

    def pide(self, cuales) -> None:
        with self.aviso:
            self.pendientes |= set(cuales)
            self.aviso.notify()

    def corre(self) -> None:
        while True:
            with self.aviso:
                self.aviso.wait_for(lambda: self.pendientes)
                destino, repo, rama = self.pendientes.pop()
            self.lee(destino, repo, rama)


def url_bus() -> str:
    if os.environ.get("PR_WATCH_RMQ_URL"):
        return os.environ["PR_WATCH_RMQ_URL"]
    clave = CREDENCIAL.read_text().strip()
    return f"amqp://synapse_pr_watch:{quote(clave, safe='')}@shared-rabbitmq.databases.svc:5672/%2Fsynapse"


def escucha(relector: Relector, espera=time.sleep) -> None:
    estado = ESTADO / "ci.estado"
    try:
        import pika
        destino = url_bus()
    except (ImportError, OSError):
        return escribe(estado, "no\n")

    def al_evento(_ch, _metodo, _props, cuerpo):
        try:
            mensaje = json.loads(cuerpo)
        except ValueError:
            return
        if isinstance(mensaje, dict):
            repo, cuales = ramas(mensaje)
            if repo and cuales != set():
                relector.pide(interesados(repo, cuales))

    fallos = 0
    while True:  # cada vuelta es una conexión nueva cuando el broker cortó la anterior, no una relectura
        try:
            conexion = pika.BlockingConnection(pika.URLParameters(destino))
            canal = conexion.channel()
            cola = f"pr-watch.consola.{socket.gethostname()}.{uuid.uuid4().hex[:12]}"
            canal.queue_declare(cola, exclusive=True, auto_delete=True)
            canal.queue_bind(cola, "events", routing_key="webhook.github.received")
            escribe(estado, "ok\n")
            fallos = 0
            # Ya enlazada: lo que pasó con el bus caído no llegó como evento, así que se relee una vez lo que se mira.
            relector.pide(interesados(None, None))
            canal.basic_consume(cola, al_evento, auto_ack=True)
            canal.start_consuming()
        except pika.exceptions.AMQPError as e:
            escribe(estado, f"caido {type(e).__name__}\n")
        fallos += 1
        espera(min(REINTENTO_MAX_S, 0.5 * 2 ** fallos))


def main() -> int:
    (ESTADO / "ci").mkdir(parents=True, exist_ok=True)
    cerrojo = open(ESTADO / "vigia.lock", "w")
    try:
        fcntl.flock(cerrojo, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return 0  # ya hay uno
    # Un hilo que muere tumba el proceso: la barra ve el pid muerto y arranca otro, en vez de pintar un estado congelado.
    threading.excepthook = lambda _a: os._exit(1)
    relector = Relector()
    # La barra empieza a mirar una rama: deja su .rama y avisa con SIGUSR1; se lee la que aún no tiene estado.
    signal.signal(signal.SIGUSR1, lambda *_: relector.pide({i for i in interesados(None, None) if not i[0].exists()}))
    escribe(ESTADO / "vigia.pid", f"{os.getpid()}\n")
    hilos = [threading.Thread(target=relector.corre, daemon=True), threading.Thread(target=escucha, args=(relector,))]
    for motor in RECURSOS:
        m = Motor(motor)
        hilos += [threading.Thread(target=m.vigila, args=(tipo,)) for tipo in RECURSOS[motor]]
    for h in hilos:
        h.start()
    # Vive con el host aunque no le quede fuente: si saliera, la barra lo arrancaría en cada repintado.
    threading.Event().wait()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
