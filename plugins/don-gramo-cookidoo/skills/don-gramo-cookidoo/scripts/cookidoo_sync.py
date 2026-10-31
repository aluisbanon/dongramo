"""Puente con Cookidoo, OPCIONAL y NO OFICIAL (librería comunitaria cookidoo-api; Vorwerk no la
publica ni la soporta y puede dejar de funcionar en cualquier momento). Se ejecuta con el Python 3.12
de ~/.don-gramo/.venv-cookidoo, no con el del sistema. Lo llama dieta.py; no lo uses directamente
salvo para probar:

    python3 scripts/cookidoo.py probar

Salida: una línea JSON {"ok": true, ...} o {"ok": false, "error": "..."}.
Credenciales: cookidoo-email y cookidoo-password (Keychain o ~/.don-gramo/state/secrets.env).
Cada usuario usa SU cuenta; nada se comparte.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nucleo import cargar  # noqa: E402

cargar()
from common import load_config, secreto  # noqa: E402

_CK = load_config().get("cookidoo", {})
PAIS, IDIOMA = _CK.get("pais", "es"), _CK.get("idioma", "es-ES")


def salir(**datos) -> None:
    print(json.dumps(datos, ensure_ascii=False))
    sys.exit(0 if datos.get("ok") else 1)


async def cliente(session):
    from cookidoo_api import Cookidoo, CookidooConfig, get_localization_options

    email, password = secreto("cookidoo-email"), secreto("cookidoo-password")
    if not email or not password:
        salir(ok=False, error="Faltan las credenciales de Cookidoo: ./install.sh cuenta (en la carpeta de la extensión)")
    opciones = await get_localization_options(country=PAIS, language=IDIOMA)
    if not opciones:
        salir(ok=False, error=f"Cookidoo no ofrece {PAIS}/{IDIOMA}")
    ck = Cookidoo(session, CookidooConfig(email=email, password=password, localization=opciones[0]))
    await ck.login()
    return ck


VELOCIDADES = {"soft", "0.5", "1", "1.5", "2", "2.5", "3", "3.5", "4", "4.5", "5", "5.5", "6", "6.5", "7",
               "7.5", "8", "8.5", "9", "9.5", "10"}


def _pos(texto: str, trozo: str) -> dict | None:
    """Posición en unidades UTF-16, como la espera el editor de Cookidoo."""
    i = texto.find(trozo)
    if i < 0 or not trozo.strip():
        return None
    u16 = lambda t: len(t.encode("utf-16-le")) // 2  # noqa: E731
    return {"offset": u16(texto[:i]), "length": u16(trozo)}


def _tts(a: dict) -> dict | None:
    t, v = int(a.get("time") or 0), str(a.get("speed") or "1")
    if not 0 < t <= 5940 or v not in VELOCIDADES:
        return None
    d = {"time": t, "speed": v}
    temp = a.get("temperature")
    if temp and (v == "soft" or float(v) <= 6):
        d["temperature"] = {"value": str(temp), "unit": "C"}
    if a.get("direction"):
        d["direction"] = a["direction"]
    return d


def construir(r: dict, nivel: str) -> tuple:
    """Ingredientes e instrucciones en el formato de Cookidoo.
    nivel: completo (báscula + programas) | sin_cantidades | solo_programas | texto."""
    ingredientes = []
    for linea, cant in zip(r["ingredientes"], r.get("cantidades") or [None] * len(r["ingredientes"])):
        item = {"type": "INGREDIENT", "text": linea}
        pos = _pos(linea, cant["slot"]) if cant and nivel == "completo" else None
        if pos:
            data = {"amount": cant["amount"]}
            if cant.get("unit"):
                data["unit"] = cant["unit"]
            item["annotations"] = [{"type": "VOLUME", "data": data, "position": pos}]
        ingredientes.append(item)
    pasos = []
    for p in r["pasos"]:
        if p.get("ingrediente") and nivel == "solo_programas":
            continue  # sin báscula: el texto original ya dice qué añadir
        paso = {"type": "STEP", "text": p["texto"]}
        anot = []
        if nivel in ("completo", "sin_cantidades") and p.get("ingrediente"):
            pos = _pos(p["texto"], p["ingrediente"])
            if pos:
                anot.append({"type": "INGREDIENT", "data": {"description": p["ingrediente"]}, "position": pos})
        elif nivel != "texto":
            for a in p.get("ajustes", []):
                d, pos = _tts(a), _pos(p["texto"], a["slot"])
                if d and pos:
                    anot.append({"type": "TTS", "data": d, "position": pos})
        if anot:
            paso["annotations"] = anot
        pasos.append(paso)
    return ingredientes, pasos


def carga(r: dict, nivel: str) -> dict:
    ingredientes, pasos = construir(r, nivel)
    total = int(r["tiempo_total"])
    activo = min(int(r["tiempo_activo"]), total)
    return {"name": r["nombre"], "tools": [r.get("modelo", "TM6")],
            "yield": {"value": r.get("raciones", 2), "unitText": "portion"},
            "prepTime": activo, "cookTime": total - activo, "totalTime": total,
            "ingredients": ingredientes, "instructions": pasos, "hints": "\n".join(r.get("consejos", [])),
            "workStatus": "PRIVATE", "recipeMetadata": {"requiresAnnotationsCheck": False}}


NIVELES = ("completo", "sin_cantidades", "solo_programas", "texto")


async def rellenar(ck, rid: str, r: dict) -> str:
    """PATCH con el formato más completo que Cookidoo acepte."""
    ultimo = None
    for nivel in NIVELES:
        try:
            await ck._patch_custom_recipe(rid, carga(r, nivel), f"receta ({nivel})")
            return nivel
        except Exception as exc:  # noqa: BLE001
            ultimo = exc
    raise ultimo


async def subir(ruta: str) -> None:
    import aiohttp
    from cookidoo_api.types import CookidooCreateCustomRecipe

    r = json.loads(Path(ruta).read_text(encoding="utf-8"))
    async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as session:
        ck = await cliente(session)
        rid, actualizada = r.get("id"), False
        if rid:
            try:
                await ck.get_custom_recipe(rid)
                actualizada = True
            except Exception:  # noqa: BLE001 — la borrasteis en la app: se crea de nuevo
                rid = None
        if not rid:
            stub = await ck.create_custom_recipe(CookidooCreateCustomRecipe(
                name=r["nombre"], ingredients=list(r["ingredientes"]), instructions=[p["texto"] for p in r["pasos"]],
                serving_size=r.get("raciones", 2), total_time=r["tiempo_total"],
                active_time=min(r["tiempo_activo"], r["tiempo_total"]), tools=[r.get("modelo", "TM6")], work_status="PRIVATE"))
            rid = stub.id
        nivel = await rellenar(ck, rid, r)
        receta = await ck.get_custom_recipe(rid)
        extra = []
        if r.get("calendario"):
            try:
                await ck.add_custom_recipes_to_calendar(dt.date.fromisoformat(r["fecha"]), [rid])
                extra.append("calendario")
            except Exception as exc:  # noqa: BLE001
                extra.append(f"calendario falló: {type(exc).__name__}")
        if r.get("compra"):
            try:
                await ck.add_ingredient_items_for_custom_recipes([rid])
                extra.append("compra")
            except Exception as exc:  # noqa: BLE001
                extra.append(f"compra falló: {type(exc).__name__}")
        salir(ok=True, id=rid, url=getattr(receta, "url", ""), actualizada=actualizada, nivel=nivel, extra=extra)


def _nutricion(det) -> dict | None:
    """kcal, proteína, hidratos y grasa por ración, si la receta los trae."""
    for grupo in getattr(det, "nutrition_groups", None) or []:
        for rn in grupo.recipe_nutritions or []:
            q = rn.quantity or 1
            out = {}
            for n in rn.nutritions or []:
                t, u = (n.type or "").lower(), (n.unittype or "").lower()
                v = float(n.number or 0) / q
                if "kcal" in (t, u) or t in ("energy", "calories") and u != "kj":
                    out.setdefault("kcal", v)
                elif "prot" in t:
                    out["p"] = v
                elif "carb" in t or "hidrat" in t:
                    out["h"] = v
                elif "fat" in t or "grasa" in t or "lipid" in t:
                    out["g"] = v
            if out.get("kcal") and "p" in out:
                out.setdefault("h", 0.0)
                out.setdefault("g", 0.0)
                return {k: round(v, 1) for k, v in out.items()}
    return None


async def buscar(texto: str, n: int) -> None:
    import aiohttp
    async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as session:
        ck = await cliente(session)
        res = await ck.search_recipes(texto, page_size=n, tmv="TM6")
        sem = asyncio.Semaphore(4)

        async def detalle(hit):
            async with sem:
                try:
                    return hit, await ck.get_recipe_details(hit.id)
                except Exception:  # noqa: BLE001
                    return hit, None
        filas = []
        for hit, det in await asyncio.gather(*(detalle(h) for h in res.recipes)):
            if det is None:
                continue
            filas.append({"id": hit.id, "nombre": hit.name, "url": hit.url, "raciones": det.serving_size,
                          "tiempo": det.total_time, "nutricion": _nutricion(det),
                          "ingredientes": [i.description or i.name for i in det.ingredients][:25]})
        salir(ok=True, total=res.total, recetas=filas)


async def planificar(rid: str, fecha: str, compra: bool) -> None:
    import aiohttp
    async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as session:
        ck = await cliente(session)
        await ck.add_recipes_to_calendar(dt.date.fromisoformat(fecha), [rid])
        extra = ["calendario"]
        if compra:
            try:
                await ck.add_ingredient_items_for_recipes([rid])
                extra.append("compra")
            except Exception as exc:  # noqa: BLE001
                extra.append(f"compra falló: {type(exc).__name__}")
        salir(ok=True, id=rid, extra=extra)


async def probar() -> None:
    import aiohttp
    async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as session:
        ck = await cliente(session)
        info = await ck.get_user_info()
        propias = await ck.list_custom_recipes()
        salir(ok=True, usuario=getattr(info, "username", "") or getattr(info, "name", ""),
              recetas_propias=len(propias))


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in ("probar", "subir", "buscar", "planificar"):
        salir(ok=False, error="uso: cookidoo_sync.py probar | subir F.json | buscar TEXTO N | "
                              "planificar ID FECHA [compra]")
    try:
        if sys.argv[1] == "probar":
            asyncio.run(probar())
        elif sys.argv[1] == "subir":
            asyncio.run(subir(sys.argv[2]))
        elif sys.argv[1] == "buscar":
            asyncio.run(buscar(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 12))
        else:
            asyncio.run(planificar(sys.argv[2], sys.argv[3], len(sys.argv) > 4 and sys.argv[4] == "compra"))
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        nombre = type(exc).__name__
        msg = "usuario o contraseña de Cookidoo incorrectos" if "Auth" in nombre else str(exc)[:300]
        salir(ok=False, error=f"{nombre}: {msg}")


if __name__ == "__main__":
    main()
