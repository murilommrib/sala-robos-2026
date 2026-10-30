#!/usr/bin/env python3
"""Caçador de tendência: varre 15 criptos todo dia, compra as que estão em tendência
(e, na versão comprado/vendido, vende as mais fracas). Decide no fechamento diário UTC
e opera ao preço de fechamento (custo 0,10% por lado + financiamento 0,03%/dia nos comprados).

Variantes testadas (grade):
  modo  "todas": comprado em todas as moedas acima da média de n dias (peso 1/15 cada; resto em caixa)
  modo  "topK":  entre as acima da média, as K com maior alta em L dias (peso 1/K)
  modo  "ls":    comprado nas K mais fortes e vendido nas K mais fracas (momento de L dias)
  rebalanceio diário ou semanal (segunda-feira, com o fechamento de domingo)
Teste encadeado: configuração escolhida só com os 2 anos anteriores; anos de teste 2023-2026.
Critérios (definidos antes de rodar): resultado encadeado > 0; Sharpe > 1; mais da metade dos
anos positivos; positivo com custo dobrado; Sharpe e pior queda melhores que comprar e segurar
as 15 moedas no mesmo período. Viés conhecido: as 15 moedas foram escolhidas hoje (sobreviventes).
Nenhuma ordem real é enviada.
"""
import csv, json, math, os, sys, datetime as dt
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "trader", "data_1h_multi")
FEE, FUND = 0.0010, 0.0003
TEST_YEARS = [2023, 2024, 2025, 2026]


def carregar():
    D = {}
    for f in sorted(os.listdir(DATA)):
        if not f.endswith(".csv"): continue
        c = f[:-4]; m = {}
        for r in csv.reader(open(os.path.join(DATA, f))):
            m[dt.datetime.utcfromtimestamp(int(r[0])).strftime("%Y-%m-%d")] = float(r[4])   # último fechamento do dia
        D[c] = m
    dias = sorted(set.intersection(*[set(m) for m in D.values()]))
    return D, dias


def simular(D, dias, cfg, fee=FEE):
    coins = sorted(D)
    C = {c: [D[c][d] for d in dias] for c in coins}
    n, L, K, modo, sem = cfg["n"], cfg["L"], cfg["K"], cfg["modo"], cfg["sem"]
    w = {}; eq = 1.0; out = {}
    start = max(n, L) + 1
    for i in range(start, len(dias)):
        # retorno do dia i com os pesos decididos no fechamento de i-1
        r = {c: C[c][i] / C[c][i - 1] - 1 for c in coins}
        R = sum(x * r[c] for c, x in w.items()) - sum(x * FUND for x in w.values())
        eq *= 1 + R
        out[dias[i]] = eq
        # pesos derivam com o preço
        if 1 + R > 0:
            w = {c: x * (1 + r[c]) / (1 + R) for c, x in w.items()}
        # decisão no fechamento de i (vale para i+1)
        wd = dt.date.fromisoformat(dias[i]).weekday()
        if sem and wd != 6:          # semanal: decide só com o fechamento de domingo
            continue
        acima = [c for c in coins if C[c][i] > sum(C[c][i - n + 1:i + 1]) / n]
        mom = sorted(((C[c][i] / C[c][i - L] - 1, c) for c in coins), reverse=True)
        if modo == "todas":
            alvo = {c: 1 / len(coins) for c in acima}
        elif modo == "topK":
            top = [c for _, c in mom if c in acima][:K]
            alvo = {c: 1 / K for c in top}
        else:
            alvo = {c: 0.5 / K for _, c in mom[:K]}
            alvo.update({c: -0.5 / K for _, c in mom[-K:]})
        turn = sum(abs(alvo.get(c, 0) - w.get(c, 0)) for c in set(alvo) | set(w))
        eq *= 1 - fee * turn
        out[dias[i]] = eq
        w = alvo
    return out


def stats(eqd, d0, d1):
    ks = sorted(d for d in eqd if d0 <= d <= d1)
    if len(ks) < 30: return None
    prev = [d for d in eqd if d < d0]
    base = eqd[max(prev)] if prev else 1.0
    e = [eqd[d] / base for d in ks]
    rs = [e[0] - 1] + [e[i] / e[i - 1] - 1 for i in range(1, len(e))]
    m = sum(rs) / len(rs); sd = (sum((x - m) ** 2 for x in rs) / len(rs)) ** .5 or 1e-12
    pk, mdd = 1.0, 0.0
    for v in e: pk = max(pk, v); mdd = min(mdd, v / pk - 1)
    return {"ret": e[-1] - 1, "sharpe": m / sd * 365 ** .5, "mdd": mdd, "rs": rs}


def agg(rs):
    e, pk, mdd = 1.0, 1.0, 0.0
    for v in rs: e *= 1 + v; pk = max(pk, e); mdd = min(mdd, e / pk - 1)
    m = sum(rs) / len(rs); sd = (sum((x - m) ** 2 for x in rs) / len(rs)) ** .5 or 1e-12
    return {"ret_pct": round(100 * (e - 1), 1), "sharpe": round(m / sd * 365 ** .5, 2), "queda_pct": round(100 * mdd, 1)}


def main():
    D, dias = carregar()
    GRID = []
    for sem in (False, True):
        for n in (20, 50, 100):
            GRID.append(dict(modo="todas", n=n, L=14, K=0, sem=sem))
            for K in (3, 5):
                for L in (14, 30, 60):
                    GRID.append(dict(modo="topK", n=n, L=L, K=K, sem=sem))
        for K in (2, 3):
            for L in (14, 30, 60):
                GRID.append(dict(modo="ls", n=20, L=L, K=K, sem=sem))
    R = [(g, simular(D, dias, g)) for g in GRID]
    # referência: comprar e segurar as 15 (pesos iguais, sem rebalancear)
    C = {c: [D[c][d] for d in dias] for c in D}
    bh = {dias[i]: sum(C[c][i] / C[c][0] for c in C) / len(C) for i in range(len(dias))}
    chain, chain_x, por_ano, chain_bh = [], [], [], []
    for y in TEST_YEARS:
        sel = lambda gr: (stats(gr[1], "%d-01-01" % (y - 2), "%d-12-31" % (y - 1)) or {"sharpe": -9})["sharpe"]
        g, eqd = max(R, key=sel)
        s = stats(eqd, "%d-01-01" % y, "%d-12-31" % y); chain += s["rs"]
        sx = stats(simular(D, dias, g, fee=2 * FEE), "%d-01-01" % y, "%d-12-31" % y); chain_x += sx["rs"]
        sb = stats(bh, "%d-01-01" % y, "%d-12-31" % y); chain_bh += sb["rs"]
        por_ano.append({"ano": y, "cfg": g, "ret_pct": round(100 * s["ret"], 1), "sharpe": round(s["sharpe"], 2), "queda_pct": round(100 * s["mdd"], 1),
                        "segurar_pct": round(100 * sb["ret"], 1)})
        print("  %d: %s -> %+.1f%% (Sharpe %.2f, queda %.1f%%) | custo dobrado %+.1f%% | segurar %+.1f%%"
              % (y, g, 100 * s["ret"], s["sharpe"], 100 * s["mdd"], 100 * sx["ret"], 100 * sb["ret"]), flush=True)
    A, X, B = agg(chain), agg(chain_x), agg(chain_bh)
    crit = [A["ret_pct"] > 0, A["sharpe"] > 1, sum(1 for p in por_ano if p["ret_pct"] > 0) > len(por_ano) / 2, X["ret_pct"] > 0,
            A["sharpe"] > B["sharpe"] and A["queda_pct"] > B["queda_pct"]]
    todas = []
    for g, eqd in R:
        s = stats(eqd, "2023-01-01", "2026-12-31")
        todas.append((round(s["sharpe"], 2), round(100 * s["ret"], 1), round(100 * s["mdd"], 1), g))
    todas.sort(key=lambda x: -x[0])
    pos = sum(1 for t in todas if t[1] > 0)
    res = {"encadeado": A, "custo_dobrado": X, "segurar_15": B, "por_ano": por_ano, "criterios": crit, "aprovado": all(crit),
           "configs_positivas_2023_2026": "%d de %d" % (pos, len(todas)), "top5_olhando_o_teste": todas[:5],
           "sharpe_mediano_configs": sorted(t[0] for t in todas)[len(todas) // 2]}
    print(json.dumps({k: v for k, v in res.items() if k != "por_ano"}, ensure_ascii=False))
    json.dump(res, open(os.path.join(HERE, "trader", "grafico", "tendencia15.json"), "w"), ensure_ascii=False)


if __name__ == "__main__":
    main()
