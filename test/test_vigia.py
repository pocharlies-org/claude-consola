import io
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "console"))
import vigia  # noqa: E402


class Fin(Exception):
    """Corta el bucle de reconexión del watch en el test."""


def app(nombre, rv, sync="Synced", health="Healthy", repo="https://github.com/org/repo.git"):
    return {"type": "MODIFIED", "object": {"metadata": {"name": nombre, "resourceVersion": rv},
                                           "spec": {"source": {"repoURL": repo}},
                                           "status": {"sync": {"status": sync}, "health": {"status": health}}}}


FIN_LISTA = {"type": "BOOKMARK", "object": {"metadata": {"resourceVersion": "9",
                                                         "annotations": {"k8s.io/initial-events-end": "true"}}}}


class Proc:
    def __init__(self, eventos, error=""):
        self.stdout = io.StringIO("".join(json.dumps(e) + "\n" for e in eventos))
        self.stderr = io.StringIO(error)

    def wait(self):
        return 0


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        vigia.ESTADO = self.dir
        (self.dir / "ci").mkdir()

    def leer(self, nombre):
        return (self.dir / nombre).read_text()


class CD(Base):
    def test_watch_argocd_escribe_solo_lo_que_pinta_la_barra(self):
        consultas, escrituras = [], []
        streams = [
            Proc([dict(app("a", "1"), type="ADDED"), dict(app("b", "2", health="Progressing"), type="ADDED"), FIN_LISTA,
                  app("a", "3"),  # un reconcile que no cambia nada: no despierta a nadie
                  app("a", "4", health="Degraded")], error="watch cerrado"),
            Proc([{"type": "ERROR", "object": {"code": 410}}]),
        ]
        original = vigia.escribe
        vigia.escribe = lambda ruta, texto: (escrituras.append(ruta.name), original(ruta, texto))
        try:
            def abre(_ruta, consulta):
                consultas.append(consulta)
                return streams.pop(0)

            def espera(_s):
                if not streams:
                    raise Fin
            m = vigia.Motor("argocd", abre, espera)
            with self.assertRaises(Fin):
                m.vigila("app")
        finally:
            vigia.escribe = original
        self.assertEqual(self.leer("cd-argocd"),
                         "https://github.com/org/repo.git\ta\tSynced/Degraded\nhttps://github.com/org/repo.git\tb\tSynced/Progressing\n")
        self.assertEqual(escrituras.count("cd-argocd"), 2)  # la lista inicial y el Degraded; el reconcile, no
        self.assertIn("sendInitialEvents=true", consultas[0])
        self.assertIn("resourceVersion=4", consultas[1])  # reanuda donde lo dejó
        self.assertTrue(self.leer("cd-argocd.estado").startswith("caido"))

    def test_410_relista_y_quita_lo_borrado_mientras_no_estaba(self):
        streams = [Proc([dict(app("a", "1"), type="ADDED"), dict(app("b", "2"), type="ADDED"), FIN_LISTA,
                         {"type": "ERROR", "object": {"code": 410}}]),
                   Proc([dict(app("a", "5"), type="ADDED"), FIN_LISTA])]
        consultas = []

        def abre(_ruta, consulta):
            consultas.append(consulta)
            return streams.pop(0)

        def espera(_s):
            if not streams:
                raise Fin
        with self.assertRaises(Fin):
            vigia.Motor("argocd", abre, espera).vigila("app")
        self.assertIn("sendInitialEvents=true", consultas[1])
        self.assertEqual(self.leer("cd-argocd"), "https://github.com/org/repo.git\ta\tSynced/Healthy\n")

    def test_flux_une_kustomization_con_su_gitrepository(self):
        m = vigia.Motor("flux")
        m.objetos["git"][("flux-system", "infra")] = {"spec": {"url": "https://github.com/org/infra-flux"}}
        m.objetos["ks"][("flux-system", "apps")] = {
            "spec": {"sourceRef": {"kind": "GitRepository", "name": "infra"}},
            "status": {"conditions": [{"type": "Ready", "status": "False"}]}}
        self.assertEqual(vigia.lineas("flux", m.objetos), "https://github.com/org/infra-flux\tapps\tFalse\n")

    def test_flux_tambien_despliega_con_helmreleases_cuyo_chart_sale_del_repo(self):
        m = vigia.Motor("flux")
        m.objetos["git"][("flux-system", "app-repo")] = {"spec": {"url": "ssh://git@bitbucket.test/team/app.git"}}
        m.objetos["hr"][("app", "api")] = {
            "spec": {"chart": {"spec": {"sourceRef": {"kind": "GitRepository", "name": "app-repo", "namespace": "flux-system"}}}},
            "status": {"conditions": [{"type": "Ready", "status": "True"}]}}
        m.objetos["hr"][("app", "de-un-helmrepo")] = {"spec": {"chart": {"spec": {"sourceRef": {"kind": "HelmRepository", "name": "x"}}}}}
        self.assertEqual(vigia.lineas("flux", m.objetos),
                         "ssh://git@bitbucket.test/team/app.git\tapi\tTrue\n\tde-un-helmrepo\tUnknown\n")

    def test_flux_sin_helm_controller_sigue_pintando_sus_kustomizations(self):
        m = vigia.Motor("flux", lambda *_: Proc([], error="Error from server (NotFound): the server could not find"),
                        lambda _s: self.fail("no reintenta un recurso que no existe"))
        m.vigila("hr")
        m.listados |= {"ks", "git"}  # los otros dos listaron
        m._publica()
        self.assertEqual(self.leer("cd-flux.estado"), "ok\n")

    def test_un_cluster_sin_flux_deja_el_motor_en_no_y_no_reintenta(self):
        m = vigia.Motor("flux", lambda *_: Proc([], error='Error from server (NotFound): the server could not find'),
                        lambda _s: self.fail("no reintenta un recurso que no existe"))
        for tipo in vigia.RECURSOS["flux"]:
            m.vigila(tipo)
        self.assertEqual(self.leer("cd-flux.estado"), "no\n")

    def test_sin_kubectl_el_motor_queda_en_no(self):
        def abre(*_):
            raise FileNotFoundError("kubectl")
        vigia.Motor("argocd", abre).vigila("app")
        self.assertEqual(self.leer("cd-argocd.estado"), "no\n")


class CI(Base):
    def test_ramas_de_cada_evento(self):
        def m(evento, cuerpo):
            return {"headers": {"x-github-event": evento}, "body": {"repository": {"full_name": "Org/Repo"}, **cuerpo}}
        self.assertEqual(vigia.ramas(m("pull_request", {"pull_request": {"head": {"ref": "f"}}})), ("org/repo", {"f"}))
        self.assertEqual(vigia.ramas(m("workflow_run", {"workflow_run": {"head_branch": "f"}})), ("org/repo", {"f"}))
        self.assertEqual(vigia.ramas(m("check_run", {"check_run": {"check_suite": {"head_branch": "f"}}})), ("org/repo", {"f"}))
        self.assertEqual(vigia.ramas(m("status", {"branches": [{"name": "f"}, {"name": "g"}]})), ("org/repo", {"f", "g"}))
        self.assertEqual(vigia.ramas(m("status", {"branches": []})), ("org/repo", None))
        self.assertEqual(vigia.ramas(m("issues", {})), ("", set()))

    def test_interesados_filtra_por_repo_y_rama_y_olvida_lo_que_no_se_pinta(self):
        ci = self.dir / "ci"
        (ci / "k1.rama").write_text("Org/Repo f\n")
        (ci / "k2.rama").write_text("org/repo g\n")
        (ci / "k3.rama").write_text("org/otro f\n")
        (ci / "k4.rama").write_text("org/repo f\n")
        (ci / "k4").write_text("[]")
        viejo = time.time() - vigia.INTERES_S - 60
        os.utime(ci / "k4.rama", (viejo, viejo))
        self.assertEqual(vigia.interesados("org/repo", {"f"}), {(ci / "k1", "Org/Repo", "f")})
        self.assertEqual({r for _, r, _ in vigia.interesados(None, None)}, {"Org/Repo", "org/repo", "org/otro"})
        self.assertFalse((ci / "k4").exists())

    def test_relector_funde_una_rafaga_en_una_lectura(self):
        r = vigia.Relector()
        clave = (self.dir / "ci" / "k", "org/repo", "f")
        for _ in range(5):
            r.pide({clave})
        self.assertEqual(r.pendientes, {clave})  # cinco eventos de la misma rama, una lectura pendiente

    def test_sin_credencial_ni_pika_no_hay_ci(self):
        vigia.CREDENCIAL = self.dir / "no-existe"
        os.environ.pop("PR_WATCH_RMQ_URL", None)
        vigia.escucha(vigia.Relector())
        self.assertEqual(self.leer("ci.estado"), "no\n")


class PikaFalso:
    """Lo justo de pika para escucha(): enlaza, entrega los mensajes dados y corta la conexión."""

    class exceptions:
        class AMQPError(Exception):
            pass

    def __init__(self, mensajes):
        self.mensajes, self.enlaces = mensajes, []
        falso = self

        class Canal:
            def queue_declare(self, cola, **kw):
                falso.enlaces.append(("cola", cola, kw))

            def queue_bind(self, cola, exchange, routing_key):
                falso.enlaces.append(("bind", exchange, routing_key))

            def basic_consume(self, cola, cb, auto_ack):
                self.cb = cb

            def start_consuming(self):
                for m in falso.mensajes:
                    self.cb(self, None, None, json.dumps(m).encode())
                raise PikaFalso.exceptions.AMQPError("el broker cortó")

        self.BlockingConnection = lambda _p: type("C", (), {"channel": lambda _s: Canal()})()
        self.URLParameters = lambda url: url


class Bus(Base):
    def test_lee_al_enlazar_y_con_cada_evento_relevante_y_nada_con_los_demas(self):
        ci = self.dir / "ci"
        (ci / "k1.rama").write_text("org/repo f\n")
        (ci / "k2.rama").write_text("org/otro g\n")
        evento = lambda tipo, repo, cuerpo: {"headers": {"x-github-event": tipo},
                                            "body": {"repository": {"full_name": repo}, **cuerpo}}
        pika = PikaFalso([
            evento("workflow_run", "org/repo", {"workflow_run": {"head_branch": "f"}}),
            evento("workflow_run", "org/repo", {"workflow_run": {"head_branch": "otra"}}),  # rama que nadie mira
            evento("issues", "org/repo", {}),  # no cambia la CI
            evento("pull_request", "org/otro", {"pull_request": {"head": {"ref": "g"}}}),
        ])
        pedidas = []
        relector = type("R", (), {"pide": lambda _s, c: pedidas.append(sorted(r for _, r, _ in c))})()
        os.environ["PR_WATCH_RMQ_URL"] = "amqp://falso"
        sys.modules["pika"] = pika
        try:
            def espera(_s):
                raise Fin
            with self.assertRaises(Fin):
                vigia.escucha(relector, espera)
        finally:
            del sys.modules["pika"]
            os.environ.pop("PR_WATCH_RMQ_URL")
        self.assertIn(("bind", "events", "webhook.github.received"), pika.enlaces)
        self.assertTrue(pika.enlaces[0][1].startswith("pr-watch.consola."))
        self.assertEqual(pika.enlaces[0][2], {"exclusive": True, "auto_delete": True})
        # al enlazar, todas; la rama que nadie mira no lee nada ([]); `issues` ni llega a pedir
        self.assertEqual(pedidas, [["org/otro", "org/repo"], ["org/repo"], [], ["org/otro"]])
        self.assertEqual(self.leer("ci.estado"), "caido AMQPError\n")


if __name__ == "__main__":
    unittest.main()
