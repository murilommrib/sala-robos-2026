#!/usr/bin/env python3
"""Robôs de carteira diversificada (simulação, dinheiro fictício, medido em euros).
  diversificado: 50% ações EUA (SPY), 25% títulos EUA 7-10a (IEF), 15% ouro (GLD), 10% bitcoin;
                 rebalanceia uma vez por ano (1º dia útil de janeiro).
  tatico:        a mesma base, mas no 1º dia de cada mês olha cada ativo: se o fechamento do mês
                 anterior está abaixo da média dos últimos 10 fechamentos mensais, aquela fatia vai
                 para o caixa (títulos curtos, SHY) até voltar para cima. Não vende a descoberto
                 (no teste, vender a descoberto piorou em todos os casos).
Começam em 30/10/2026 com EUR 500 fictícios cada. Preços: Yahoo Finance (fechamento ajustado),
convertidos para euro. Custo 0,2% sobre o valor trocado. NENHUMA ORDEM REAL. Gerado pelo Claude."""
import json, os, time, urllib.request, datetime as dt
HERE = os.path.dirname(os.path.abspath(__file__))
PASTA = os.path.join(HERE, "trader", "mundo")
INICIO = "2026-10-30"
CUSTO = 0.002
BASE = {"acoes": 0.50, "tit": 0.25, "ouro": 0.15, "btc": 0.10}
TICK = {"acoes": "SPY", "tit": "IEF", "ouro": "GLD", "btc": "BTC-USD", "caixa": "SHY", "fx": "EURUSD=X"}
NOME = {"acoes": "ações EUA (SPY)", "tit": "títulos EUA (IEF)", "ouro": "ouro (GLD)", "btc": "bitcoin", "caixa": "caixa (SHY)"}
ROBOS = ("diversificado", "tatico")

def _arq(t): return os.path.join(PASTA, "vivo_%s.json" % t.replace("^", "").replace("=", "_"))

def baixar(t, max_idade=3600):
    """Preços diários ajustados dos últimos 2 anos; cache de 1 hora. Em erro, usa o cache."""
    fp = _arq(t)
    if os.path.exists(fp) and time.time() - os.path.getmtime(fp) < max_idade:
        return dict(json.load(open(fp)))
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/%s?range=2y&interval=1d" % urllib.request.quote(t)
        d = json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=20))["chart"]["result"][0]
        adj = (d["indicators"].get("adjclose") or [{}])[0].get("adjclose") or d["indicators"]["quote"][0]["close"]
        rows = [(dt.datetime.utcfromtimestamp(a).strftime("%Y-%m-%d"), b) for a, b in zip(d["timestamp"], adj) if b]
        os.makedirs(PASTA, exist_ok=True)
        tmp = fp + ".tmp"; json.dump(rows, open(tmp, "w")); os.replace(tmp, fp)
        return dict(rows)
    except Exception:
        if os.path.exists(fp):
            return dict(json.load(open(fp)))
        raise

def _ate(serie, dia):
    ks = [k for k in serie if k <= dia]
    return serie[max(ks)] if ks else None

def _fim_de_mes(serie_eur, ate_mes):
    """fechamentos de fim de mês (em euro) de todos os meses ANTERIORES a ate_mes (AAAA-MM)."""
    o = {}
    for k in sorted(serie_eur):
        if k[:7] < ate_mes: o[k[:7]] = serie_eur[k]
    return [o[m] for m in sorted(o)]

def pesos_tatico(eur, mes):
    w = {}
    for a, p in BASE.items():
        fm = _fim_de_mes(eur[a], mes)[-10:]
        acima = len(fm) < 10 or fm[-1] > sum(fm) / 10
        if acima: w[a] = w.get(a, 0) + p
        else: w["caixa"] = w.get("caixa", 0) + p
    return w

def rodar(st, agora):
    hoje = dt.datetime.utcfromtimestamp(agora).date()
    usd = {a: baixar(t) for a, t in TICK.items()}
    fx = usd.pop("fx")
    eur = {a: {d: v / _ate(fx, d) for d, v in s.items() if _ate(fx, d)} for a, s in usd.items()}
    dias = []
    d = dt.date.fromisoformat(INICIO) - dt.timedelta(days=1)
    while d <= hoje:
        dias.append(d.isoformat()); d += dt.timedelta(days=1)
    for rid in ROBOS:
        eq, w, curva, trocas = 1.0, None, {dias[0]: 1.0}, []
        for d0, d1 in zip(dias, dias[1:]):
            novo = None
            if w is None:
                novo = dict(BASE) if rid == "diversificado" else pesos_tatico(eur, d1[:7])
            elif rid == "diversificado" and d1[5:] == "01-01":
                novo = dict(BASE)
            elif rid == "tatico" and d1[8:] == "01":
                novo = pesos_tatico(eur, d1[:7])
            if novo is not None:
                giro = sum(abs(novo.get(a, 0) - (w or {}).get(a, 0)) for a in set(novo) | set(w or {})) / 2 if w else 0.0
                eq *= 1 - CUSTO * 2 * giro
                if w is not None and giro > 1e-9:
                    trocas.append({"dia": d1, "de": {a: round(x, 3) for a, x in w.items()}, "para": novo})
                w = novo
            r = 0.0
            for a, x in w.items():
                p0, p1 = _ate(eur[a], d0), _ate(eur[a], d1)
                if p0 and p1: r += x * (p1 / p0 - 1)
            eq *= 1 + r
            tot = sum(x * ((_ate(eur[a], d1) or 1) / (_ate(eur[a], d0) or 1)) for a, x in w.items())
            w = {a: x * ((_ate(eur[a], d1) or 1) / (_ate(eur[a], d0) or 1)) / tot for a, x in w.items()} if tot else w
            curva[d1] = eq
        of = {"dias": curva, "pos": {}, "ordens": {}, "trades": [], "perdidos": [],
              "carteira": {a: round(x, 4) for a, x in (w or {}).items()}, "trocas": trocas[-12:],
              "precos_ate": {a: max(s) for a, s in usd.items()}}
        st["robos"][rid] = {"oficial": of, "ideal": of}

def resumo(st, rid):
    of = (st["robos"].get(rid) or {}).get("oficial") or {}
    cart = of.get("carteira") or {}
    ativos = [a for a in cart if a != "caixa" and cart[a] > 0.001]
    return {"moeda": "ETFs em euro",
            "posicoes": [{"moeda": NOME[a], "lado": "comprado", "peso_pct": round(100 * cart[a], 1), "entrada": None, "resultado_pct": None} for a in ativos],
            "caixa_pct": round(100 * cart.get("caixa", 0), 1),
            "trocas": of.get("trocas", [])[::-1][:5], "precos_ate": of.get("precos_ate")}

if __name__ == "__main__":
    st = {"robos": {}}
    rodar(st, time.time())
    for rid in ROBOS:
        of = st["robos"][rid]["oficial"]; print(rid, of["carteira"], list(of["dias"].items())[-3:], resumo(st, rid)["caixa_pct"])
