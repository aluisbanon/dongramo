#!/usr/bin/env python3
"""Ayuda de instalación: muestra los chats y usuarios que han escrito al bot.

Uso (con el puente PARADO, si no se come los mensajes):
  1. Añade el bot al grupo (o escríbele por privado) y escribe "/ayuda".
  2. bot/install.sh ids
  3. Guarda el id del chat con `bot/install.sh chat <ID>`. Cada persona se vincula después con `/soy <nombre>`.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_config, secreto, tg_api  # noqa: E402

cfg = load_config()
token = secreto(cfg["telegram"]["secreto_token"])
if not token:
    sys.exit("No encuentro el token del bot. Guárdalo con: bot/install.sh token")
me = tg_api(token, "getMe")["result"]
print(f"Bot: @{me['username']} (id {me['id']})\n")
chats, users = {}, {}
for u in tg_api(token, "getUpdates", timeout=0).get("result", []):
    m = u.get("message") or {}
    c, f = m.get("chat") or {}, m.get("from") or {}
    if c:
        chats[c["id"]] = f"{c.get('type')} · {c.get('title') or c.get('first_name')}"
    if f and not f.get("is_bot"):
        users[f["id"]] = f"{f.get('first_name', '')} {f.get('last_name', '')} @{f.get('username', '')}".strip()
print("Chats:"); [print(f"  {k}  {v}") for k, v in chats.items()]
print("Usuarios:"); [print(f"  {k}  {v}") for k, v in users.items()]
if not chats:
    print("\nNo hay mensajes. ¿Has escrito /ayuda en el chat? ¿Está el puente parado (bot/install.sh parar)?")
