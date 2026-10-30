#!/usr/bin/env python3
"""Termômetro de risco: quanto cada robô pode perder AGORA e quão agitado está o mercado.
Não muda nenhuma decisão dos robôs; só mede. Simulação, dinheiro fictício. Gerado pelo Claude.
Medidas:
  - "dia ruim" (VaR 95%, 1 dia): perda que só deve ser ultrapassada em ~1 de cada 20 dias,
    estimada pela volatilidade e correlação dos últimos 60 dias (velas de 1h agregadas por dia).
  - "no stop": perda se a posição for até o stop (posições com stop).
  - nota 0-100 = maior das duas perdas em % do capital do robô x 12,5 (8% = 100).
    faixas: até 1,5% baixo · até 3% moderado · até 5% alto · acima extremo.
  - mercado: volatilidade dos últimos 7 dias contra a dos últimos 90 (x1,0 = normal)."""
import math, json, os, datetime as dt
HERE = os.path.dirname(os.path.abspath(__file__))
Z95 = 1.645
def _dias(velas):
    """fechamentos diários (00:00 UTC) a partir das velas de 1h fechadas."""
    out = {}
    for c, rows in velas.items():
        d = {}
        for r in rows:
            d[dt.datetime.utcfromtimestamp(r[0]).strftime("%Y-%m-%d")] = r[4]
        ks = sorted(d)
        out[c] = {k: d[k] for k in ks[:-1]}                     # o último dia está incompleto
    return out
def _rets(fech):
    R = {}
    for c, d in fech.items():
        ks = sorted(d); R[c] = {ks[i]: d[ks[i]] / d[ks[i - 1]] - 1 for i in range(1, len(ks))}
    return R
def _std(xs):
    if len(xs) < 2: return 0.0
    m = sum(xs) / len(xs); return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))
def _cov(R, moedas, n=60):
    dias = sorted(set.intersection(*[set(R[c]) for c in moedas]))[-n:]
    M = {c: [R[c][d] for d in dias] for c in moedas}
    mu = {c: sum(v) / len(v) for c, v in M.items()}
    return {(a, b): sum((x - mu[a]) * (y - mu[b]) for x, y in zip(M[a], M[b])) / (len(dias) - 1) for a in moedas for b in moedas}, dias
def var_pesos(w, R, n=60):
    w = {c: x for c, x in w.items() if abs(x) > 1e-9 and c in R}
    if not w: return 0.0, 0.0
    C, dias = _cov(R, list(w), n)
    v = sum(w[a] * w[b] * C[(a, b)] for a in w for b in w)
    pior = min(sum(w[c] * R[c][d] for c in w) for d in dias)        # pior dia real dessa carteira em 60 dias
    return Z95 * math.sqrt(max(v, 0)), pior
def nivel(p):
    return "baixo" if p < 1.5 else "moderado" if p < 3 else "alto" if p < 5 else "extremo"
def nota(p): return int(round(min(100, max(0, p * 12.5))))
def _item(rid, cap, var_pct, stop_pct, pior_pct, desc):
    base = max(var_pct, stop_pct or 0)
    return {"id": rid, "nota": nota(base), "nivel": nivel(base), "dia_ruim_pct": round(var_pct, 2),
            "dia_ruim_eur": round(cap * var_pct / 100, 2), "no_stop_pct": None if stop_pct is None else round(stop_pct, 2),
            "no_stop_eur": None if stop_pct is None else round(cap * stop_pct / 100, 2),
            "pior_dia_60d_pct": None if pior_pct is None else round(pior_pct, 2), "exposicao": desc}

def medir(st, merc, est_sala, velas, robos_def):
    R = _rets(_dias(velas))
    cap = {k: v["capital"] for k, v in est_sala["robos"].items()}
    pesos = (est_sala.get("pesos_hoje") or {}).get("pesos") or {}
    out = {"robos": {}, "carteira": {}, "mercado": {}}
    expo = {}                                                     # euros líquidos por moeda (só carteira)
    for r in robos_def:
        rid, tipo = r["id"], r["tipo"]; c0 = cap.get(rid, 0)
        if tipo in ("diario", "referencia"):
            w = pesos.get(rid) or {}
            v, pior = var_pesos(w, R)
            bruto = sum(abs(x) for x in w.values())
            desc = "fora do mercado" if not bruto else "%d %s, %d%% comprado e %d%% vendido" % (
                len(w), "moeda" if len(w) == 1 else "moedas", round(100 * sum(x for x in w.values() if x > 0)), round(100 * sum(-x for x in w.values() if x < 0)))
            out["robos"][rid] = _item(rid, c0, 100 * v, None, 100 * pior if bruto else None, desc)
            if tipo == "diario":
                for c, x in w.items(): expo[c] = expo.get(c, 0) + x * c0
        elif tipo == "gestor":
            w = {}
            for k in ("tendo", "semanal", "calmo", "extremo"):
                for c, x in (pesos.get(k) or {}).items(): w[c] = w.get(c, 0) + x / 4
            v, pior = var_pesos(w, R)
            out["robos"][rid] = _item(rid, c0, 100 * v, None, 100 * pior if w else None, "média dos 4 aprovados")
        elif tipo in ("grafico", "experimento"):
            of = ((st["robos"].get(rid) or {}).get("oficial")) or {}
            if rid in ("diversificado", "tatico"):
                out["robos"][rid] = _etf(rid, c0, of)
                continue
            w, stop, partes, tem_stop = {}, 0.0, [], False
            if tipo == "grafico":
                p = of.get("pos")
                if p:
                    c = r["coin"]; w[c] = p["lado"]; stop = abs(p["e"] - p["sp"]) / p["e"]; tem_stop = True
                    partes.append("%s em %s" % ("comprado" if p["lado"] > 0 else "vendido", c))
                    expo[c] = expo.get(c, 0) + p["lado"] * c0
            else:
                eq = (of.get("dias") or {}); eqv = eq[max(eq)] if eq else 1.0
                for c, p in (of.get("pos") or {}).items():
                    frac = min(1.0, (p.get("tam") or eqv / 3) / eqv) if eqv else 1 / 3
                    w[c] = w.get(c, 0) + p["lado"] * frac
                    if p.get("sp") and p.get("e"): stop += frac * abs(p["e"] - p["sp"]) / p["e"]; tem_stop = True
                    partes.append("%s em %s" % ("comprado" if p["lado"] > 0 else "vendido", c))
            v, pior = var_pesos(w, R)
            out["robos"][rid] = _item(rid, c0, 100 * v, 100 * stop if (w and tem_stop) else None, 100 * pior if w else None,
                                      ", ".join(partes) if partes else "sem posição")
    # carteira inteira, com correlação entre robôs que apostam na mesma moeda
    tot = sum(cap.get(r["id"], 0) for r in robos_def if r["tipo"] in ("diario", "grafico"))
    wc = {c: x / tot for c, x in expo.items()} if tot else {}
    v, pior = var_pesos(wc, R)
    soma_sep = sum(out["robos"][r["id"]]["dia_ruim_eur"] for r in robos_def if r["tipo"] in ("diario", "grafico") and r["id"] in out["robos"])
    out["carteira"] = {"nota": nota(100 * v), "nivel": nivel(100 * v), "dia_ruim_pct": round(100 * v, 2), "dia_ruim_eur": round(tot * v, 2),
                       "pior_dia_60d_pct": round(100 * pior, 2) if wc else None, "soma_robos_eur": round(soma_sep, 2),
                       "liquido_por_moeda_eur": {c: round(x, 2) for c, x in sorted(expo.items(), key=lambda kv: -abs(kv[1])) if abs(x) >= 0.5}}
    # mercado: volatilidade recente contra a normal
    reg = {}
    for c in ("BTC", "ETH", "SOL", "XRP", "BNB"):
        if c in R:
            ks = sorted(R[c]); s7 = _std([R[c][k] for k in ks[-7:]]); s90 = _std([R[c][k] for k in ks[-90:]])
            if s90: reg[c] = round(s7 / s90, 2)
    media = round(sum(reg.values()) / len(reg), 2) if reg else None
    out["mercado"] = {"agitacao": media, "por_moeda": reg,
                      "nivel": None if media is None else ("calmo" if media < 0.8 else "normal" if media < 1.25 else "agitado" if media < 1.75 else "muito agitado"),
                      "medo_ganancia": ((merc.get("medo_ganancia") or {}).get("valor"))}
    return out

def _etf(rid, cap, of):
    """carteiras de ETFs: volatilidade dos últimos 60 pregões das próprias séries em euro."""
    try:
        import diversificado as DV
        w = of.get("carteira") or {}
        fx = dict(json.load(open(DV._arq(DV.TICK["fx"]))))
        S = {a: dict(json.load(open(DV._arq(DV.TICK[a])))) for a in w}
        dias = sorted(set.intersection(*[set(s) for s in S.values()]) & set(fx))[-61:]
        R = {a: {dias[i]: (S[a][dias[i]] / fx[dias[i]]) / (S[a][dias[i - 1]] / fx[dias[i - 1]]) - 1 for i in range(1, len(dias))} for a in w}
        v, pior = var_pesos(w, R)
        desc = ", ".join("%s %d%%" % (DV.NOME[a], round(100 * x)) for a, x in sorted(w.items(), key=lambda kv: -kv[1]))
        return _item(rid, cap, 100 * v, None, 100 * pior, desc)
    except Exception as e:
        return _item(rid, cap, 0.0, None, None, "sem dados (%s)" % type(e).__name__)

def calibrar(velas, n=30):
    """Conferência: com a cesta igual das 10 moedas, em quantos dias a perda passou do 'dia ruim' previsto?"""
    R = _rets(_dias(velas)); moedas = [c for c in ("BTC", "ETH", "BNB", "XRP", "ADA", "LINK", "LTC", "DOGE", "SOL", "TRX") if c in R]
    dias = sorted(set.intersection(*[set(R[c]) for c in moedas])); w = {c: 1 / len(moedas) for c in moedas}
    passou = tot = 0
    for i in range(n, len(dias)):
        sub = {c: {d: R[c][d] for d in dias[i - n:i]} for c in moedas}
        v, _ = var_pesos(w, sub, n)
        real = sum(w[c] * R[c][dias[i]] for c in moedas)
        tot += 1; passou += real < -v
    return passou, tot

if __name__ == "__main__":
    V = json.load(open(os.path.join(HERE, "trader", "vivo", "velas_1h_15.json")))
    p, t = calibrar(V)
    print("calibração: a perda passou do 'dia ruim' em %d de %d dias (%.1f%%; o esperado é ~5%%)" % (p, t, 100 * p / t))
