#!/usr/bin/env python3
"""Mesa do trader: o robô aponta configurações e VOCÊ decide (na página) se entraria.

Configuração = as 6 condições da confluência (tendência, RSI/MACD, volume, VWAP, vela forte,
fluxo comprador/vendedor) concordando numa vela de 15 minutos de BTC, ETH, SOL ou XRP.
Cada uma recebe entrada (fechamento da vela), stop (2 ATR), alvo (3 ATR) e validade de 12 horas.
O robô acompanha TODAS até o fim (stop, alvo ou tempo) e calcula o resultado com custo de
0,20% ida e volta (operação manual a mercado). A página compara: suas escolhas x entrar em todas.
Nenhuma ordem real é enviada.
"""
import time
import sala as SALA
import grafico as G
from confluencia import condicoes

MOEDAS = ["BTC", "ETH", "SOL", "XRP"]
K, KS, KT, HORAS, CUSTO, TOL = 6, 2.0, 3.0, 12, 0.0020, 20 * 60


def _velas15(sym, n=400):
    for h in SALA.HOSTS:
        d = SALA.get_json("%s/api/v3/klines?symbol=%s&interval=15m&limit=%d" % (h, sym, n))
        if isinstance(d, list):
            return [(int(r[0]) // 1000, float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[7]), float(r[10])) for r in d]
    return None


def rodar(st_vivo, agora):
    M = st_vivo.setdefault("mesa", {"setups": [], "ult": {}})
    for c in MOEDAS:
        b = _velas15(c + "USDT")
        if not b:
            continue
        b = [x for x in b if x[0] + 900 <= agora]          # só velas fechadas
        if len(b) < 250:
            continue
        L, S = condicoes(b)
        A = G.atr([x[:5] for x in b])
        ult = M["ult"].get(c, 0)
        for i in range(len(b) - 8, len(b)):
            t = b[i][0]
            if t <= ult:
                continue
            M["ult"][c] = t
            sd = 1 if (L[i] >= K and L[i] > S[i]) else -1 if (S[i] >= K and S[i] > L[i]) else 0
            if not sd or not A[i] or agora - (t + 900) > TOL:
                continue
            e = b[i][4]
            M["setups"].append({"id": "%s-%d" % (c, t), "moeda": c, "lado": sd, "entrada": e,
                                "stop": e - sd * KS * A[i], "alvo": e + sd * KT * A[i],
                                "criado": t + 900, "expira": t + 900 + HORAS * 3600, "status": "aberta"})
        # acompanha as abertas
        for s in M["setups"]:
            if s["moeda"] != c or s["status"] != "aberta":
                continue
            sd = s["lado"]; x = how = None; tx = None
            for r in b:
                if r[0] < s["criado"]:
                    continue
                if (r[3] <= s["stop"]) if sd == 1 else (r[2] >= s["stop"]):
                    x, how, tx = s["stop"], "stop", r[0] + 900; break
                if (r[2] > s["alvo"]) if sd == 1 else (r[3] < s["alvo"]):
                    x, how, tx = s["alvo"], "alvo", r[0] + 900; break
                if r[0] + 900 >= s["expira"]:
                    x, how, tx = r[4], "tempo", r[0] + 900; break
            if x is not None:
                s.update(status=how, saida=x, resolvido=tx, pct=round(100 * (sd * (x / s["entrada"] - 1) - CUSTO), 3))
            else:
                s["agora_pct"] = round(100 * sd * (b[-1][4] / s["entrada"] - 1), 3)
    M["setups"] = M["setups"][-120:]


def resumo(st_vivo):
    M = st_vivo.get("mesa") or {}
    out = []
    for s in reversed(M.get("setups", [])[-60:]):
        out.append({k: (round(v, 6) if isinstance(v, float) else v) for k, v in s.items()})
    return out
