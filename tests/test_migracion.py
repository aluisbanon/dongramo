"""Migración del nombre antiguo (don-gramo, 1.0) al nuevo (dongramo, 1.1).

Cada prueba usa un HOME temporal: nunca toca ~/.don-gramo ni ~/.dongramo reales.

    python3 -m unittest tests.test_migracion -v
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Las pruebas nunca deben tocar los datos reales (~/.dongramo, ~/.don-gramo): carpeta temporal para todo
# lo que importe common.py en este mismo proceso. Va antes de cualquier import del motor.
_DATOS_PRUEBA = tempfile.mkdtemp(prefix="dongramo-pruebas-")
os.environ["DONGRAMO_HOME"] = _DATOS_PRUEBA
os.environ.pop("DON_GRAMO_HOME", None)

RAIZ = Path(__file__).resolve().parent.parent
SKILL = RAIZ / "plugins" / "dongramo" / "skills" / "dongramo"
COOKIDOO = RAIZ / "plugins" / "dongramo-cookidoo" / "skills" / "dongramo-cookidoo"
SHELLS = [RAIZ / "instalar.sh", RAIZ / "plugins" / "dongramo" / "bot" / "install.sh",
          RAIZ / "plugins" / "dongramo-cookidoo" / "install.sh"]
CONFIG = {"personas": {"ana": {"nombre": "Ana", "sexo": "mujer", "edad": 35, "altura_cm": 165, "peso_kg": 62,
                               "objetivo_kcal": 1700}}}


def entorno(home: Path, **extra) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("DONGRAMO_", "DON_GRAMO_"))}
    env.update(HOME=str(home), **extra)
    return env


def py(home: Path, codigo: str, **extra) -> str:
    p = subprocess.run([sys.executable, "-c", codigo], cwd=SKILL / "scripts", env=entorno(home, **extra),
                       capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        raise AssertionError(p.stderr)
    return p.stdout.strip()


HOME_PY = "import common; print(common.HOME)"


class CarpetaDeDatos(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name).resolve()
        self.viejo, self.nuevo = self.home / ".don-gramo", self.home / ".dongramo"

    def tearDown(self):
        self.tmp.cleanup()

    def crear_viejo(self):
        (self.viejo / "state").mkdir(parents=True)
        (self.viejo / "config.json").write_text(json.dumps(CONFIG), encoding="utf-8")
        (self.viejo / "state" / "pesos.jsonl").write_text('{"persona": "ana", "kg": 62}\n', encoding="utf-8")

    def test_sin_nada_usa_la_nueva_y_no_crea_nada(self):
        self.assertEqual(py(self.home, HOME_PY), str(self.nuevo))
        self.assertFalse(self.nuevo.exists())
        self.assertFalse(self.viejo.exists())

    def test_migra_la_antigua_y_deja_enlace(self):
        self.crear_viejo()
        self.assertEqual(py(self.home, HOME_PY), str(self.nuevo))
        self.assertTrue(self.nuevo.is_dir() and not self.nuevo.is_symlink())
        self.assertEqual(json.loads((self.nuevo / "config.json").read_text()), CONFIG)
        self.assertTrue((self.nuevo / "state" / "pesos.jsonl").exists())
        self.assertTrue(self.viejo.is_symlink())
        self.assertEqual(self.viejo.resolve(), self.nuevo)
        # lo que escribe un bot antiguo por la ruta vieja acaba en la nueva
        (self.viejo / "state" / "x.txt").write_text("hola")
        self.assertEqual((self.nuevo / "state" / "x.txt").read_text(), "hola")

    def test_segunda_vez_no_hace_nada(self):
        self.crear_viejo()
        py(self.home, HOME_PY)
        py(self.home, HOME_PY)
        self.assertTrue(self.viejo.is_symlink())
        self.assertEqual(sorted(p.name for p in self.home.iterdir() if "gramo" in p.name), [".don-gramo", ".dongramo"])

    def test_si_existen_las_dos_no_toca_ninguna(self):
        self.crear_viejo()
        self.nuevo.mkdir()
        self.assertEqual(py(self.home, HOME_PY), str(self.nuevo))
        self.assertTrue(self.viejo.is_dir() and not self.viejo.is_symlink())
        self.assertTrue((self.viejo / "config.json").exists())

    def test_variable_antigua_se_respeta(self):
        otra = self.home / "otra"
        self.assertEqual(py(self.home, HOME_PY, DON_GRAMO_HOME=str(otra)), str(otra))

    def test_variable_nueva_manda(self):
        a, b = self.home / "a", self.home / "b"
        self.assertEqual(py(self.home, HOME_PY, DONGRAMO_HOME=str(a), DON_GRAMO_HOME=str(b)), str(a))

    def test_el_motor_lee_los_datos_migrados(self):
        self.crear_viejo()
        p = subprocess.run([sys.executable, "-I", "scripts/dieta.py", "hogar"], cwd=SKILL, env=entorno(self.home),
                           capture_output=True, text=True, timeout=60)
        self.assertIn("Ana", p.stdout + p.stderr)
        self.assertTrue(self.viejo.is_symlink())

    def test_shells_migran_igual(self):
        for sh in SHELLS:
            with self.subTest(sh=sh.name):
                if self.viejo.is_symlink():
                    self.viejo.unlink()
                if self.nuevo.exists():
                    shutil.rmtree(self.nuevo)
                self.crear_viejo()
                funcion = re.search(r"^dg_home\(\) \{.*?^\}", sh.read_text(), re.S | re.M).group(0)
                for _ in range(2):  # idempotente
                    out = subprocess.run(["bash", "-c", funcion + "\ndg_home"], env=entorno(self.home),
                                         capture_output=True, text=True, check=True).stdout.strip()
                    self.assertEqual(out, str(self.nuevo))
                self.assertTrue(self.viejo.is_symlink())
                self.assertTrue((self.nuevo / "config.json").exists())
                out = subprocess.run(["bash", "-c", funcion + "\ndg_home"], capture_output=True, text=True,
                                     env=entorno(self.home, DON_GRAMO_HOME="/x/antigua")).stdout.strip()
                self.assertEqual(out, "/x/antigua")


class Secretos(unittest.TestCase):
    def test_nombres(self):
        sys.path.insert(0, str(SKILL / "scripts"))
        import common
        self.assertIn("dongramo-pruebas-", str(common.HOME))  # la guarda funciona: nunca la carpeta real
        self.assertNotIn(str(Path.home() / ".dongramo"), str(common.HOME))
        self.assertEqual(common.nombres_secreto("dongramo-telegram-bot"),
                         ["dongramo-telegram-bot", "don-gramo-telegram-bot"])
        self.assertEqual(common.nombres_secreto("don-gramo-telegram-chat"),
                         ["don-gramo-telegram-chat", "dongramo-telegram-chat"])
        self.assertEqual(common.nombres_secreto("cookidoo-email"), ["cookidoo-email"])

    def test_lee_el_secreto_con_el_nombre_antiguo(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            (home / "datos" / "state").mkdir(parents=True)
            s = home / "datos" / "state" / "secrets.env"
            s.write_text("don-gramo-telegram-bot=123:ABC\n")
            s.chmod(0o600)
            sin_keychain = ("import sys, common; sys.platform = 'linux'; "
                            "print(common.secreto('dongramo-telegram-bot'), common.secreto('dongramo-telegram-chat'))")
            out = py(home, sin_keychain, DONGRAMO_HOME=str(home / "datos"))
            self.assertEqual(out, "123:ABC None")


class RegistroDeExtensiones(unittest.TestCase):
    def test_quita_las_claves_antiguas(self):
        with tempfile.TemporaryDirectory() as d:
            datos = Path(d) / "datos"
            datos.mkdir()
            (datos / "plugins.json").write_text(json.dumps({"don-gramo": "/viejo", "don-gramo-cookidoo": "/v2"}))
            py(Path(d), "import common; from pathlib import Path; common.registrar_plugin('dongramo', Path('/nuevo'))",
               DONGRAMO_HOME=str(datos))
            self.assertEqual(json.loads((datos / "plugins.json").read_text()), {"dongramo": "/nuevo"})

    def _extension_aislada(self, d: Path) -> Path:
        dst = d / "plugins" / "dongramo-cookidoo"
        shutil.copytree(COOKIDOO.parent.parent, dst, ignore=shutil.ignore_patterns("__pycache__"))
        return dst / "skills" / "dongramo-cookidoo" / "scripts"

    def test_cookidoo_encuentra_el_nucleo_por_la_clave_antigua(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            scripts = self._extension_aislada(d)
            datos = d / "datos"
            datos.mkdir()
            (datos / "plugins.json").write_text(json.dumps({"don-gramo": str(SKILL / "scripts")}))
            p = subprocess.run([sys.executable, "-c", "import nucleo; print(nucleo.ruta())"], cwd=scripts,
                               env=entorno(d, DONGRAMO_HOME=str(datos)), capture_output=True, text=True)
            self.assertEqual(p.stdout.strip(), str(SKILL / "scripts"))

    def test_cookidoo_entiende_la_variable_antigua_del_nucleo(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            scripts = self._extension_aislada(d)
            p = subprocess.run([sys.executable, "-c", "import nucleo; print(nucleo.ruta())"], cwd=scripts,
                               env=entorno(d, DONGRAMO_HOME=str(d / "datos"), DON_GRAMO_NUCLEO=str(SKILL / "scripts")),
                               capture_output=True, text=True)
            self.assertEqual(p.stdout.strip(), str(SKILL / "scripts"))

    def test_cookidoo_usa_la_carpeta_antigua_si_aun_no_se_ha_migrado(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            scripts = self._extension_aislada(d)
            (d / ".don-gramo").mkdir()
            p = subprocess.run([sys.executable, "-c", "import nucleo; print(nucleo.HOME)"], cwd=scripts,
                               env=entorno(d), capture_output=True, text=True)
            self.assertEqual(p.stdout.strip(), str(d / ".don-gramo"))


class InstaladorYServicios(unittest.TestCase):
    def test_instalar_agents_quita_la_copia_antigua(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            (home / ".agents" / "skills" / "don-gramo").mkdir(parents=True)
            subprocess.run(["bash", str(RAIZ / "instalar.sh"), "agents", "--cookidoo"], env=entorno(home),
                           capture_output=True, text=True, check=True)
            hay = sorted(p.name for p in (home / ".agents" / "skills").iterdir())
            self.assertEqual(hay, ["dongramo", "dongramo-cookidoo"])

    def test_quita_las_unidades_systemd_antiguas(self):
        texto = SHELLS[1].read_text()
        funcion = re.search(r"^quitar_systemd_antiguo\(\) \{.*?^\}", texto, re.S | re.M).group(0)
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            u = home / ".config" / "systemd" / "user"
            u.mkdir(parents=True)
            for f in ("don-gramo-telegram.service", "don-gramo-diario.timer", "dongramo-diario.timer"):
                (u / f).touch()
            binario = home / "bin"
            binario.mkdir()
            (binario / "systemctl").write_text(f'#!/bin/bash\necho "$@" >> "{home}/llamadas"\n')
            (binario / "systemctl").chmod(0o755)
            env = entorno(home, PATH=f"{binario}:/usr/bin:/bin")
            subprocess.run(["bash", "-c", funcion + "\nquitar_systemd_antiguo"], env=env, check=True,
                           capture_output=True)
            self.assertEqual(sorted(p.name for p in u.iterdir()), ["dongramo-diario.timer"])
            self.assertIn("disable --now don-gramo-telegram.service", (home / "llamadas").read_text())
            (home / "llamadas").unlink()
            subprocess.run(["bash", "-c", funcion + "\nquitar_systemd_antiguo"], env=env, check=True)
            self.assertFalse((home / "llamadas").exists())  # sin unidades antiguas no llama a nada


class NoTocaLosDatosReales(unittest.TestCase):
    def test_importar_en_proceso_usa_la_carpeta_de_pruebas(self):
        p = subprocess.run([sys.executable, "-c", "import os, common; print(common.HOME == __import__('pathlib').Path(os.environ['DONGRAMO_HOME']))"],
                           cwd=SKILL / "scripts", env=dict(os.environ), capture_output=True, text=True)
        self.assertEqual(p.stdout.strip(), "True")


class SinRestosDelNombreAntiguo(unittest.TestCase):
    # Solo pueden nombrar «don-gramo»/«DON_GRAMO» la compatibilidad, la guía de migración y el historial
    PERMITIDOS = {"CHANGELOG.md", "README.md", "instalar.sh", "tests/test_migracion.py", "tests/test_motor.py",
                  "plugins/dongramo/bot/install.sh", "plugins/dongramo-cookidoo/install.sh",
                  "plugins/dongramo/skills/dongramo/scripts/common.py",
                  "plugins/dongramo-cookidoo/skills/dongramo-cookidoo/scripts/nucleo.py"}

    def test_repo(self):
        ficheros = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=RAIZ,
                                  capture_output=True, text=True, check=True).stdout.split()
        malos = []
        for f in ficheros:
            p = RAIZ / f
            if f in self.PERMITIDOS or not p.is_file() or p.suffix in (".png", ".pyc"):
                continue
            texto = p.read_text(encoding="utf-8", errors="ignore")
            if re.search(r"don-gramo|DON_GRAMO", texto) or "don-gramo" in f:
                malos.append(f)
        self.assertEqual(malos, [])

    def test_readme_solo_en_la_guia_de_migracion(self):
        texto = (RAIZ / "README.md").read_text(encoding="utf-8")
        guia = re.search(r"### Si vienes de la 1\.0.*?(?=\n### )", texto, re.S).group(0)
        self.assertNotRegex(texto.replace(guia, ""), r"don-gramo|DON_GRAMO")

    def test_manifiestos(self):
        m = json.loads((RAIZ / ".claude-plugin" / "marketplace.json").read_text())
        self.assertEqual(m["name"], "dongramo")
        self.assertEqual([p["name"] for p in m["plugins"]], ["dongramo", "dongramo-cookidoo"])
        for p in m["plugins"]:
            pj = json.loads((RAIZ / p["source"] / ".claude-plugin" / "plugin.json").read_text())
            self.assertEqual(pj["name"], p["name"])
            self.assertEqual(pj["version"], p["version"])
            self.assertIn("aluisbanon/dongramo", pj["repository"])
        for n in ("dongramo", "dongramo-cookidoo"):
            skill = RAIZ / "plugins" / n / "skills" / n / "SKILL.md"
            self.assertRegex(skill.read_text(encoding="utf-8"), rf"(?m)^name: {n}$")


if __name__ == "__main__":
    unittest.main()
