"""Pruebas del motor de Don Gramo con hogares de 0, 1, 2 y 4 personas.

    python3 -m unittest discover -s tests -v

Cada prueba usa un DON_GRAMO_HOME temporal y lanza dieta.py como lo haría Claude.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SKILL = RAIZ / "plugins" / "don-gramo" / "skills" / "don-gramo"
COOKIDOO = RAIZ / "plugins" / "don-gramo-cookidoo" / "skills" / "don-gramo-cookidoo"
LUNES = "2026-10-26"


class Hogar:
    def __init__(self):
        self.dir = tempfile.TemporaryDirectory()
        self.home = Path(self.dir.name)

    def run(self, *args, ok=True, script="dieta.py", cwd=SKILL) -> str:
        env = dict(os.environ, DON_GRAMO_HOME=str(self.home))
        p = subprocess.run([sys.executable, "-I", f"scripts/{script}", *args], cwd=cwd, env=env,
                           capture_output=True, text=True, timeout=60)
        if ok and p.returncode != 0:
            raise AssertionError(f"{args} falló ({p.returncode}):\n{p.stdout}\n{p.stderr}")
        return p.stdout + p.stderr

    def config(self, cfg: dict):
        (self.home / "config.json").write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")

    def totales(self, fecha=LUNES) -> dict:
        """{nombre: (kcal, proteína)} de la cabecera de `hoy`."""
        out = self.run("hoy", "--fecha", fecha)
        return {m[0]: (int(m[1].replace(".", "")), int(m[2]))
                for m in re.findall(r"^(\w+): ([\d.]+) kcal · P (\d+) g", out, re.M)}

    def close(self):
        self.dir.cleanup()


def pareja() -> dict:
    return {"hogar": {"nombre": "Casa", "thermomix": True}, "personas": {
        "ana": {"nombre": "Ana", "extra_diario": [{"f": "proteína whey", "g": 30, "nota": "batido"}],
                "perfil": {"objetivo_kcal": 2180, "mantenimiento_kcal": 2650, "suelo_kcal": 1800, "modo": "perder",
                           "ritmo_kg_sem": 0.4, "meta_kg": 79.5, "desde": "2026-10-01"}},
        "bea": {"nombre": "Bea", "extra_diario": [],
                "perfil": {"objetivo_kcal": 1590, "mantenimiento_kcal": 2150, "suelo_kcal": 1300, "modo": "perder",
                           "ritmo_kg_sem": 0.45, "meta_kg": 74.5, "desde": "2026-10-01"}}}}


class SinPersonas(unittest.TestCase):
    def setUp(self):
        self.h = Hogar()

    def tearDown(self):
        self.h.close()

    def test_menu_sin_configurar(self):
        self.assertIn("Menú", self.h.run("menu"))

    def test_hoy_pide_configurar(self):
        self.assertIn("persona-alta", self.h.run("hoy", ok=False))


class UnaPersona(unittest.TestCase):
    def setUp(self):
        self.h = Hogar()
        self.h.run("persona-alta", "--nombre", "Marta", "--sexo", "m", "--edad", "41", "--altura", "165",
                   "--peso", "72", "--actividad", "ligera", "--meta-kg", "65")

    def tearDown(self):
        self.h.close()

    def test_estimacion_y_objetivo(self):
        perfil = self.h.run("perfil")
        self.assertRegex(perfil, r"Marta\*: 1\d{3} kcal/día")
        kcal, prot = self.h.totales()["Marta"]
        objetivo = int(re.search(r"(\d+) kcal/día", perfil).group(1))
        self.assertLess(abs(kcal - objetivo) / objetivo, 0.08)
        self.assertGreater(prot, 90)

    def test_compra_para_una(self):
        self.assertIn("para Marta", self.h.run("compra"))

    def test_hogar_muestra_objetivo_vigente(self):
        self.h.run("objetivo", "--persona", "marta", "--kcal", "1650")
        self.assertIn("Marta (`marta`, 1650 kcal)", self.h.run("hogar"))

    def test_peso_y_progreso(self):
        for f, kg in (("2026-10-05", 73.5), ("2026-10-12", 73.0), ("2026-10-19", 72.4)):
            self.h.run("peso", "--persona", "marta", "--kg", str(kg), "--fecha", f)
        self.assertIn("Tendencia 4 semanas", self.h.run("progreso"))


class Pareja(unittest.TestCase):
    def setUp(self):
        self.h = Hogar()
        self.h.config(pareja())

    def tearDown(self):
        self.h.close()

    def test_cada_uno_en_su_objetivo(self):
        t = self.h.totales()
        self.assertLess(abs(t["Ana"][0] - 2180) / 2180, 0.06)
        self.assertLess(abs(t["Bea"][0] - 1590) / 1590, 0.06)
        # quien come menos conserva casi toda la proteína
        self.assertGreater(t["Bea"][1] / t["Ana"][1], 0.6)

    def test_extra_se_compensa_y_se_deshace(self):
        out = self.h.run("registrar", "--persona", "ana", "--tipo", "extra", "--desc", "cañas", "--kcal", "430",
                         "--fecha", LUNES, "--hora", "13:00")
        self.assertIn("Exceso del día: 430 kcal", out)
        self.assertIn("Ana", self.h.run("ajustes"))
        self.h.run("borrar", "1")
        self.assertIn("Ana: sin ajustes", self.h.run("ajustes"))

    def test_plato_nuevo_valida(self):
        malo = self.h.run("plato-nuevo", "--fecha", LUNES, "--comida", "Cena", "--nombre", "Solo ensalada",
                          "--items", "tomate:200; lechuga:100")
        self.assertIn("No lo aplico", malo)
        bueno = self.h.run("plato-nuevo", "--fecha", LUNES, "--comida", "Cena", "--nombre", "Merluza con pan",
                           "--items", "merluza:200; tomate:150; pan integral:60; aceite:8")
        self.assertIn("✅", bueno)

    def test_preferencia_solo_a_una_persona(self):
        self.h.run("preferencia", "--de", "pechuga de pollo", "--a", "pechuga de pavo", "--persona", "bea")
        detalle = self.h.run("receta", LUNES, "comida")
        self.assertIn("Bea: pavo en vez de pollo", detalle)

    def test_cantidad_por_persona_y_para_todos(self):
        self.h.run("cantidad", "--alimento", "pan integral", "--fecha", LUNES, "--comida", "Cena", "--gramos", "bea=40")
        self.assertIn("Bea 40 g", self.h.run("cambios", "--semana", LUNES))
        out = self.h.run("anadir", "--alimento", "huevo", "--fecha", LUNES, "--comida", "Cena", "--gramos", "55")
        self.assertIn("cada uno", out)

    def test_racion_reparte_la_olla(self):
        out = self.h.run("racion", "--fecha", LUNES)
        pct = [int(x) for x in re.findall(r"(?:Ana|Bea) (\d+) %", out)]
        self.assertTrue(pct)
        self.assertEqual(sum(pct[:2]), 100)

    def test_revision_propone_y_acepta(self):
        for f, kg in (("2026-10-05", 85.0), ("2026-10-12", 84.9), ("2026-10-19", 84.9), ("2026-10-26", 84.8)):
            self.h.run("peso", "--persona", "ana", "--kg", str(kg), "--fecha", f)
        self.assertIn("Revisión semanal", self.h.run("revision"))


class Familia(unittest.TestCase):
    def setUp(self):
        self.h = Hogar()
        for a in (["Marta", "m", "41", "165", "72", "ligera", "65"], ["Javier", "h", "44", "180", "92", "moderada", "82"]):
            self.h.run("persona-alta", "--nombre", a[0], "--sexo", a[1], "--edad", a[2], "--altura", a[3],
                       "--peso", a[4], "--actividad", a[5], "--meta-kg", a[6])
        self.h.run("persona-alta", "--nombre", "Leo", "--sexo", "h", "--edad", "12", "--altura", "150", "--peso", "40",
                   "--actividad", "alta")
        self.h.run("persona-alta", "--nombre", "Sofía", "--sexo", "m", "--edad", "7", "--altura", "122", "--peso", "23")
        self.h.run("hogar", "--thermomix", "si")

    def tearDown(self):
        self.h.close()

    def test_menores_sin_deficit_y_proteina_razonable(self):
        self.assertIn("modo crecimiento", self.h.run("perfil", "--persona", "sofia"))
        kcal, prot = self.h.totales()["Sofía"]
        self.assertLess(prot * 4 / kcal, 0.26)
        self.assertNotIn("Propuesta", self.h.run("revision", "--sin-guardar"))

    def test_menor_no_acepta_meta_de_perdida(self):
        out = self.h.run("persona-alta", "--nombre", "Hugo", "--sexo", "h", "--edad", "15", "--altura", "170",
                         "--peso", "75", "--meta-kg", "65")
        self.assertIn("modo: crecer", out)

    def test_menor_no_admite_objetivo_de_perdida(self):
        for args in (["--modo", "perder"], ["--meta-kg", "35"], ["--suelo", "900"]):
            self.assertIn("edad de crecimiento", self.h.run("objetivo", "--persona", "leo", *args))
        self.assertIn("modo crecimiento", self.h.run("perfil", "--persona", "leo"))

    def test_menor_kcal_respeta_suelo(self):
        out = self.h.run("persona-alta", "--nombre", "Hugo", "--sexo", "h", "--edad", "10", "--altura", "140",
                         "--peso", "33", "--kcal", "600")
        kcal, suelo = map(int, re.search(r"objetivo: \*(\d+) kcal/día\* · suelo: (\d+)", out).groups())
        self.assertGreaterEqual(kcal, suelo)

    def test_agua_escalada_y_aviso_de_vaso(self):
        receta = self.h.run("receta", LUNES, "comida")
        self.assertIn("(Marta · Javier · Leo · Sofía · total)", receta)
        agua = int(re.search(r"(\d[\d.]*) g de agua", receta).group(1).replace(".", ""))
        self.assertGreater(agua, 700)

    def test_sin_thermomix_pasos_tradicionales(self):
        self.h.run("hogar", "--thermomix", "no")
        receta = self.h.run("receta", LUNES, "comida")
        self.assertNotIn("vel ", receta)
        self.assertNotIn("(TM)", self.h.run("menu", "--semana", LUNES))

    def test_nucleo_sin_comandos_de_cookidoo(self):
        self.assertIn("invalid choice", self.h.run("cookidoo", ok=False))

    def test_baja_conserva_historial(self):
        self.h.run("persona-baja", "--persona", "leo")
        self.assertNotIn("Leo", self.h.run("personas"))



class AsistenteTelegram(unittest.TestCase):
    """Los pasos que no tocan Telegram ni los servicios del sistema."""

    def setUp(self):
        self.h = Hogar()

    def tearDown(self):
        self.h.close()

    def tg(self, *args):
        return self.h.run(*args, script="telegram_setup.py")

    def test_estado_guia_desde_el_principio(self):
        self.assertIn("Siguiente paso: Configura antes el hogar", self.tg("estado"))
        self.h.config(pareja())
        self.assertIn("⬜ Token del bot guardado", self.tg("estado"))

    def test_copia_estable_funciona_sola(self):
        self.h.config(pareja())
        self.assertIn("Copia estable instalada", self.tg("copiar"))
        copia = self.h.home / "app" / "don-gramo" / "skills" / "don-gramo"
        env = dict(os.environ, DON_GRAMO_HOME=str(self.h.home))
        p = subprocess.run([sys.executable, "-I", "scripts/dieta.py", "personas"], cwd=copia, env=env,
                           capture_output=True, text=True)
        self.assertIn("Ana", p.stdout)
        self.assertFalse((self.h.home / "app" / "don-gramo-cookidoo").exists())  # no instalada: no se copia
        self.assertIn("actualizada", self.tg("copiar"))

    def test_token_nunca_por_argumento_ni_sin_terminal(self):
        self.h.config(pareja())
        out = self.tg("token", "--terminal")
        self.assertIn("terminal", out)
        self.assertFalse((self.h.home / "state" / "secrets.env").exists())

    def test_pasos_en_orden(self):
        self.h.config(pareja())
        self.assertIn("Primero guarda el token", self.tg("chat"))
        self.assertIn("Faltan pasos: token", self.tg("activar"))


class SkillsSueltas(unittest.TestCase):
    """Como las instala OpenClaw: <dir>/don-gramo y <dir>/don-gramo-cookidoo, una junto a otra, sin plugin."""

    def test_nucleo_y_extension_se_encuentran(self):
        import shutil
        h = Hogar()
        try:
            h.config(pareja())
            dirs = h.home / "skills"
            shutil.copytree(SKILL, dirs / "don-gramo")
            shutil.copytree(COOKIDOO, dirs / "don-gramo-cookidoo")
            env = dict(os.environ, DON_GRAMO_HOME=str(h.home))
            run = lambda *a: subprocess.run([sys.executable, "-I", *a], env=env, capture_output=True, text=True).stdout  # noqa: E731
            self.assertIn("Ana", run(str(dirs / "don-gramo" / "scripts" / "dieta.py"), "personas"))
            (h.home / "plugins.json").unlink(missing_ok=True)  # que no tire de lo registrado
            out = run(str(dirs / "don-gramo-cookidoo" / "scripts" / "cookidoo.py"), "receta", "--fecha", LUNES, "--comida", "Comida")
            self.assertIn("Para Cookidoo", out)
            self.assertIn("solo tiene la skill", run(str(dirs / "don-gramo" / "scripts" / "telegram_setup.py"), "copiar"))
        finally:
            h.close()

    def test_cabecera_compatible(self):
        cab = (SKILL / "SKILL.md").read_text().split("---")[1]
        self.assertIn("name: don-gramo", cab)
        self.assertIn('"openclaw"', cab)
        self.assertNotIn("python3 scripts/", (SKILL / "SKILL.md").read_text())


class Instalador(unittest.TestCase):
    def test_codex_y_agents(self):
        with tempfile.TemporaryDirectory() as d:
            env = dict(os.environ, HOME=d, CODEX_HOME=f"{d}/.codex")
            for destino in ("codex", "agents"):
                p = subprocess.run(["bash", str(RAIZ / "instalar.sh"), destino, "--cookidoo"], env=env,
                                   capture_output=True, text=True)
                self.assertEqual(p.returncode, 0, p.stderr)
            for sk in (Path(d) / ".codex" / "skills", Path(d) / ".agents" / "skills"):
                self.assertTrue((sk / "don-gramo" / "SKILL.md").exists())
                self.assertTrue((sk / "don-gramo-cookidoo" / "scripts" / "cookidoo.py").exists())
                self.assertFalse(list(sk.rglob("__pycache__")))

    def test_cabecera_valida_para_codex(self):
        """Codex solo admite name, description, license, allowed-tools y metadata."""
        for skill in (SKILL, COOKIDOO):
            cab = (skill / "SKILL.md").read_text().split("---")[1]
            claves = {l.split(":", 1)[0] for l in cab.strip().splitlines() if re.match(r"^[a-z-]+:", l)}
            self.assertLessEqual(claves, {"name", "description", "license", "allowed-tools", "metadata"}, skill)


class ExtensionCookidoo(unittest.TestCase):
    """La extensión encuentra el núcleo, prepara la receta y no sube nada sin instalar ni confirmar."""

    def setUp(self):
        self.h = Hogar()
        self.h.config(pareja())

    def tearDown(self):
        self.h.close()

    def ck(self, *args, ok=True):
        return self.h.run(*args, ok=ok, script="cookidoo.py", cwd=COOKIDOO)

    def test_vista_previa_con_cantidades_de_todos(self):
        out = self.ck("receta", "--fecha", LUNES, "--comida", "Comida")
        self.assertIn("Para Cookidoo", out)
        self.assertIn("2 raciones", out)
        self.assertIn("¿La subo?", out)

    def test_no_sube_sin_instalar(self):
        out = self.ck("receta", "--fecha", LUNES, "--comida", "Comida", "--subir")
        self.assertIn("no está preparada", out)

    def test_se_registra_y_el_nucleo_la_ve(self):
        self.ck("receta", "--fecha", LUNES, "--comida", "Comida")
        reg = json.loads((self.h.home / "plugins.json").read_text())
        self.assertIn("don-gramo-cookidoo", reg)
        self.assertNotIn("conectado", self.h.run("hogar"))  # sin ./install.sh instalar, no se anuncia
        (self.h.home / ".venv-cookidoo" / "bin").mkdir(parents=True)
        (self.h.home / ".venv-cookidoo" / "bin" / "python").touch()
        self.assertIn("Para Cookidoo", self.h.run("receta", LUNES, "comida"))
        self.assertIn("Cookidoo: conectado", self.h.run("hogar"))

    def test_sin_nucleo_avisa(self):
        env = dict(os.environ, DON_GRAMO_HOME=str(self.h.home), DON_GRAMO_NUCLEO="/no/existe")
        with tempfile.TemporaryDirectory() as d:  # copia aislada de la extensión, sin el núcleo al lado
            import shutil
            dst = Path(d) / "plugins" / "don-gramo-cookidoo"
            shutil.copytree(COOKIDOO.parent.parent, dst)
            (self.h.home / "plugins.json").write_text("{}")
            p = subprocess.run([sys.executable, "-I", "scripts/cookidoo.py", "probar"],
                               cwd=dst / "skills" / "don-gramo-cookidoo", env=env, capture_output=True, text=True)
        self.assertIn("necesita el plugin don-gramo", p.stdout)

class EnvioTelegram(unittest.TestCase):
    """tg_send sin red: Telegram devuelve el Markdown inválido como HTTP 400."""

    def setUp(self):
        sys.path.insert(0, str(SKILL / "scripts"))
        import common
        self.common = common
        self.addCleanup(sys.path.remove, str(SKILL / "scripts"))

    def _http(self, code):
        import io
        import urllib.error
        return urllib.error.HTTPError("https://api.telegram.org", code, "Bad Request", {}, io.BytesIO(b"{}"))

    def test_markdown_rechazado_reintenta_en_plano(self):
        from unittest import mock
        llamadas = []

        def api(token, method, **params):
            llamadas.append(params)
            if "parse_mode" in params:
                raise self._http(400)
            return {"ok": True}
        with mock.patch.object(self.common, "tg_api", api), mock.patch.object(self.common, "log"):
            self.assertTrue(self.common.tg_send("t", "c", "*hola"))
        self.assertEqual(len(llamadas), 2)
        self.assertNotIn("parse_mode", llamadas[1])

    def test_chat_privado_no_necesita_mencion(self):
        import telegram_bridge as tb
        privado = {"chat": {"type": "private"}, "text": "he comido fuera"}
        grupo = {"chat": {"type": "group"}, "text": "he comido fuera"}
        self.assertTrue(tb.dirigido_al_bot(privado, "dongramo_bot", 1))
        self.assertFalse(tb.dirigido_al_bot(grupo, "dongramo_bot", 1))
        self.assertTrue(tb.dirigido_al_bot(dict(grupo, text="@dongramo_bot he comido fuera"), "dongramo_bot", 1))

    def test_fallo_de_envio_devuelve_false(self):
        from unittest import mock

        def api(token, method, **params):
            raise self._http(403)
        with mock.patch.object(self.common, "tg_api", api), mock.patch.object(self.common, "log"):
            self.assertFalse(self.common.tg_send("t", "c", "hola"))


if __name__ == "__main__":
    unittest.main()
