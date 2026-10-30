#!/usr/bin/env python3
"""Robô Repórter (EXPERIMENTO, EUR 100 fictícios fora da carteira): opera notícias.

Quem lê as notícias é a tarefa agendada de hora em hora (Claude): ela procura as manchetes
da última hora que podem mexer com uma das 15 criptos (juros dos EUA, ETFs, hacks, regulação,
listagens...) e grava trader/vivo/noticias.json com sinais:
  {"sinais": [{"id", "criado_utc", "moeda", "lado": 1|-1, "confianca": 0-1, "motivo", "fonte"}]}
Este robô, que roda a cada 5 minutos no Mac:
  - entra a mercado (custo 0,05% + 0,05% de slippage) em cada sinal novo com confiança >= 0,6,
    se ainda não tem posição naquela moeda (no máximo 3 ao mesmo tempo, 1/3 do patrimônio cada);
    sinal com mais de 2 horas quando chega é ignorado (notícia velha já está no preço);
  - stop 2 ATR, alvo 3 ATR (ATR de velas de 1 hora), saída por tempo em 12 horas;
    confere stop/alvo com a máxima/mínima das velas de 1h fechadas e com o preço do momento.
Nenhuma ordem real é enviada.
"""
import json, os, time, datetime as dt
HERE = os.path.dirname(os.path.abspath(__file__))
ARQ = os.path.join(HERE, "trader", "vivo", "noticias.json")
TAKER, SLIP = 0.0005, 0.0005
K, KS, KT, HORAS, MAX_IDADE, CONF = 3, 2.0, 3.0, 12, 2 * 3600, 0.6


def _atr(rows, n=14):
    a = None
    for i in range(1, len(rows)):
        tr = max(rows[i][2] - rows[i][3], abs(rows[i][2] - rows[i - 1][4]), abs(rows[i][3] - rows[i - 1][4]))
        a = tr if a is None else (a * (n - 1) + tr) / n
    return a


def rodar(st_vivo, agora, precos, velas):
    """precos: {moeda: preço agora}; velas: {moeda: [(t,o,h,l,c,v), ...]} de 1h fechadas."""
    R = st_vivo["robos"].setdefault("reporter", {})
    of = R.setdefault("oficial", {"eq": 1.0, "pos": {}, "ordens": {}, "trades": [], "perdidos": [], "dias": {}, "vistos": [], "sinais": []})
    hoje = dt.datetime.utcfromtimestamp(agora).strftime("%Y-%m-%d")
    # 1) saídas
    for c in list(of["pos"]):
        p = of["pos"][c]; sd = p["lado"]
        rows = [r for r in velas.get(c, []) if r[0] >= p["t_vela"]]
        x = how = None
        for r in rows:                                   # velas de 1h fechadas desde a entrada
            if (r[3] <= p["sp"]) if sd == 1 else (r[2] >= p["sp"]):
                x, how = p["sp"], "stop"; break
            if (r[2] > p["tp"]) if sd == 1 else (r[3] < p["tp"]):
                x, how = p["tp"], "alvo"; break
        pr = precos.get(c)
        if x is None and pr:
            if (pr <= p["sp"]) if sd == 1 else (pr >= p["sp"]):
                x, how = pr, "stop"
            elif (pr >= p["tp"]) if sd == 1 else (pr <= p["tp"]):
                x, how = p["tp"], "alvo"
            elif agora >= p["t_in"] + HORAS * 3600:
                x, how = pr, "tempo"
        if x is not None:
            g = sd * (x / p["e"] - 1); cost = 2 * (TAKER + SLIP)
            of["eq"] += p["tam"] * (g - cost)
            of["trades"].append([p["t_in"], agora, sd, p["e"], x, how, round(g - cost, 6), c])
            del of["pos"][c]
    # 2) entradas
    try:
        sinais = json.load(open(ARQ)).get("sinais", [])
    except Exception:
        sinais = []
    for s in sinais:
        sid = str(s.get("id"))
        if not sid or sid in of["vistos"]:
            continue
        of["vistos"].append(sid); of["vistos"] = of["vistos"][-500:]
        of["sinais"].append({k: s.get(k) for k in ("id", "criado_utc", "moeda", "lado", "confianca", "motivo", "fonte")})
        of["sinais"] = of["sinais"][-60:]
        c, sd = s.get("moeda"), s.get("lado")
        try:
            criado = int(dt.datetime.fromisoformat(str(s.get("criado_utc")).replace("Z", "+00:00")).timestamp())
            conf = float(s.get("confianca", 0))
        except Exception:
            continue
        if c not in precos or sd not in (1, -1) or conf < CONF:
            continue
        if agora - criado > MAX_IDADE:
            of["perdidos"].append([agora, sd, "notícia velha (mais de 2h)", c]); continue
        if c in of["pos"] or len(of["pos"]) >= K:
            of["perdidos"].append([agora, sd, "sem vaga ou já posicionado", c]); continue
        a = _atr(velas.get(c, [])[-60:])
        if not a:
            continue
        e = precos[c] * (1 + sd * SLIP)
        of["pos"][c] = {"lado": sd, "e": e, "sp": e - sd * KS * a, "tp": e + sd * KT * a, "tam": of["eq"] / K,
                        "t_in": agora, "t_vela": agora - agora % 3600, "motivo": str(s.get("motivo", ""))[:200]}
    # 3) patrimônio marcado a mercado
    mtm = of["eq"] + sum(p["tam"] * p["lado"] * (precos.get(c, p["e"]) / p["e"] - 1) for c, p in of["pos"].items())
    of["dias"][hoje] = round(mtm, 8)
    of["ult_t"] = agora
    R["ideal"] = of                                       # notícias não têm versão "ideal" separada
