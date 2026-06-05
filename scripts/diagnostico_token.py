"""Diagnostica o token Meta — mostra dono, permissões e o que falta."""
import os, sys, json, urllib.request, urllib.error

env_file = os.path.join(os.path.dirname(__file__), ".env.meta")
if os.path.exists(env_file):
    for line in open(env_file):
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

token = os.environ.get("WHATSAPP_BUSINESS_TOKEN")
if not token:
    print("Token não encontrado.")
    sys.exit(1)

def _get(url):
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())

print(f"Token tem {len(token)} chars.\n")

# 1) Quem é o dono?
status, me = _get(f"https://graph.facebook.com/v21.0/me?access_token={token}")
print(f"[/me] status={status}")
print(json.dumps(me, indent=2, ensure_ascii=False))

# 2) Permissões do token
print(f"\n[/debug_token]")
status, dbg = _get(
    f"https://graph.facebook.com/v21.0/debug_token?input_token={token}&access_token={token}"
)
print(json.dumps(dbg, indent=2, ensure_ascii=False))

# 3) Diagnóstico
print("\n========== DIAGNÓSTICO ==========")
scopes = (dbg.get("data") or {}).get("scopes") or []
print(f"Escopos: {scopes}")

requeridos = {"whatsapp_business_management", "business_management"}
faltantes = requeridos - set(scopes)
if faltantes:
    print(f"\n❌ Faltam escopos: {faltantes}")
    print("\nGere um novo token em https://developers.facebook.com/tools/explorer/")
    print("Marque essas permissões antes de gerar:")
    for s in requeridos:
        print(f"  - {s}")
else:
    print("\n✅ Escopos OK pra criar templates.")
    # Se OK mas /me/businesses tá vazio, problema é tipo de token
    print("\nTeste direto criar template no WABA do asset_id da URL (1878227826269282)?")
