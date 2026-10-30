#!/usr/bin/env python3
"""Confluência em velas curtas (5 e 15 minutos) com VOLUME real.

Seis condições, medidas no fechamento de cada vela (só passado):
  C1 tendência: preço e média de 50 acima da média de 200 (venda: abaixo)
  C2 momento: RSI(14) ou histograma do MACD cruzou a linha do meio nesta vela, a favor
  C3 volume: volume da vela > 2x a média das 20 anteriores
  C4 VWAP do dia (com volume de verdade): preço acima (venda: abaixo)
  C5 vela forte: fecha no terço de cima (venda: de baixo) e corpo > metade da vela
  C6 fluxo: compradores agressivos > 55% do volume (venda: < 45%)
Sinal quando pelo menos k das 6 concordam no mesmo lado (k = 4, 5 ou 6).
Saída: stop ks*ATR, alvo kt*ATR ou H velas. Entrada a mercado (abertura seguinte) ou ordem
limitada 0,25 ATR atrás (motor causal). Mede primeiro o ganho SEM custo; depois com custo.
Escolha da configuração só com 2023-2024; teste em 2025-2026 (fora da amostra).
Nenhuma ordem real é enviada.
"""
import csv, json, math, os, sys, datetime as dt
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import grafico as G
import motor as M

DATA = os.path.join(HERE, "trader", "data_5m_vol")
TAKER, SLIP, MAKER = 0.0005, 0.0005, 0.0002
SPLIT = int(dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc).timestamp())


def carregar(c, tf):
    rows = [(int(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5]), float(r[6])) for r in csv.reader(open(os.path.join(DATA, c + ".csv")))]
    out, key, cur = [], None, None
    step = tf * 60
    for t, o, h, l, cl, v, bv in rows:
        k = t - t % step
        if k != key:
            if cur: out.append(tuple(cur))
            key, cur = k, [k, o, h, l, cl, v, bv]
        else:
            cur[2] = max(cur[2], h); cur[3] = min(cur[3], l); cur[4] = cl; cur[5] += v; cur[6] += bv
    if cur: out.append(tuple(cur))
    return out


def condicoes(b):
    n = len(b)
    c = [x[4] for x in b]; o = [x[1] for x in b]; h = [x[2] for x in b]; l = [x[3] for x in b]; v = [x[5] for x in b]; bv = [x[6] for x in b]
    e50, e200 = G.ema(c, 50), G.ema(c, 200)
    rsi = G.rsi(c, 14)
    e12, e26 = G.ema(c, 12), G.ema(c, 26)
    macd = [(a - b_) if (a is not None and b_ is not None) else None for a, b_ in zip(e12, e26)]
    sig = G.ema([x if x is not None else 0.0 for x in macd], 9)
    hist = [(m - s) if (m is not None and s is not None) else None for m, s in zip(macd, sig)]
    vw, day, pv, vv = [None] * n, None, 0.0, 0.0
    for i in range(n):
        d = b[i][0] // 86400
        if d != day: day, pv, vv = d, 0.0, 0.0
        pv += (h[i] + l[i] + c[i]) / 3 * v[i]; vv += v[i]
        vw[i] = pv / vv if vv else c[i]
    L, S = [0] * n, [0] * n            # quantas condições a favor da compra / da venda
    s20 = 0.0
    for i in range(n):
        if i >= 1: s20 += v[i - 1]
        if i >= 21: s20 -= v[i - 21]
        if i < 201 or e200[i] is None or rsi[i] is None or rsi[i - 1] is None or hist[i] is None or hist[i - 1] is None:
            continue
        rng = h[i] - l[i]
        avgv = s20 / 20
        vol = avgv > 0 and v[i] > 2 * avgv
        share = bv[i] / v[i] if v[i] else 0.5
        lu = (c[i] > e200[i] and e50[i] > e200[i]) + ((rsi[i - 1] <= 50 < rsi[i]) or (hist[i - 1] <= 0 < hist[i])) + vol + (c[i] > vw[i]) \
            + (rng > 0 and c[i] >= l[i] + rng * 2 / 3 and abs(c[i] - o[i]) > rng / 2 and c[i] > o[i]) + (share > 0.55)
        sd = (c[i] < e200[i] and e50[i] < e200[i]) + ((rsi[i - 1] >= 50 > rsi[i]) or (hist[i - 1] >= 0 > hist[i])) + vol + (c[i] < vw[i]) \
            + (rng > 0 and c[i] <= h[i] - rng * 2 / 3 and abs(c[i] - o[i]) > rng / 2 and c[i] < o[i]) + (share < 0.45)
        L[i], S[i] = lu, sd
    return L, S


def stats(trs, t0, t1):
    g = [x for x in trs if t0 <= x[0] < t1]
    if not g: return None
    net = [x[2] for x in g]; gross = [x[1] for x in g]
    eq = 1.0
    for x in net: eq *= 1 + x
    return {"ops": len(g), "bruto_op_pct": round(100 * sum(gross) / len(g), 4), "liq_op_pct": round(100 * sum(net) / len(g), 4),
            "acerto_pct": round(100 * sum(1 for x in net if x > 0) / len(g), 1), "total_pct": round(100 * (eq - 1), 1)}


def main():
    coins = sorted(f[:-4] for f in os.listdir(DATA) if f.endswith(".csv"))
    res = []
    for tf in (5, 15):
        for c in coins:
            b = carregar(c, tf)
            bb = [x[:5] for x in b]
            A = G.atr(bb)
            Lc, Sc = condicoes(b)
            for k in (4, 5, 6):
                SIG = [1 if (Lc[i] >= k and Lc[i] > Sc[i]) else -1 if (Sc[i] >= k and Sc[i] > Lc[i]) else 0 for i in range(len(b))]
                for ks in (1.0, 2.0):
                    for kt in (1.5, 3.0):
                        for H in (12, 48):
                            # a mercado: entra na abertura seguinte
                            trs = [(t, g, g - 2 * (TAKER + SLIP)) for t, sd, g in G.trades(bb, SIG, A, ks, kt, H)]
                            res.append({"tf": tf, "moeda": c, "k": k, "ks": ks, "kt": kt, "H": H, "ent": "mercado",
                                        "dentro": stats(trs, 0, SPLIT), "fora": stats(trs, SPLIT, 2 ** 40)})
                            # ordem limitada (motor causal)
                            st = M.rodar(bb, SIG, A, dict(off=0.25, ks=ks, kt=kt, H=H, wait=3), inicio_t=0)
                            trs = []
                            for x in st["trades"]:
                                cost = MAKER + (MAKER if x[5] == "alvo" else TAKER + SLIP)
                                trs.append((x[0], x[6] + cost, x[6]))
                            res.append({"tf": tf, "moeda": c, "k": k, "ks": ks, "kt": kt, "H": H, "ent": "limite",
                                        "dentro": stats(trs, 0, SPLIT), "fora": stats(trs, SPLIT, 2 ** 40)})
            print("tf %d %s ok" % (tf, c), flush=True)
    ok = [r for r in res if r["dentro"] and r["fora"] and r["dentro"]["ops"] >= 50]
    def med(v):
        v = sorted(v); return v[len(v) // 2] if v else None
    resumo = {
        "configs": len(ok),
        "bruto_op_mediano_pct_2023_2024": med([r["dentro"]["bruto_op_pct"] for r in ok]),
        "bruto_op_mediano_pct_2025_2026": med([r["fora"]["bruto_op_pct"] for r in ok]),
        "configs_bruto_acima_custo_mercado_2023_2024": sum(1 for r in ok if r["ent"] == "mercado" and r["dentro"]["bruto_op_pct"] > 0.2),
        "configs_liquido_positivo_2025_2026": sum(1 for r in ok if r["fora"]["total_pct"] > 0),
    }
    # escolha honesta: melhor resultado líquido em 2023-2024 por moeda e tempo de vela; olhar 2025-2026
    escolhidas = []
    for tf in (5, 15):
        for c in coins:
            cand = [r for r in ok if r["tf"] == tf and r["moeda"] == c]
            if not cand: continue
            best = max(cand, key=lambda r: r["dentro"]["total_pct"])
            escolhidas.append({k: best[k] for k in ("tf", "moeda", "k", "ks", "kt", "H", "ent")} | {"2023_2024": best["dentro"], "2025_2026": best["fora"]})
    resumo["escolhidas"] = escolhidas
    por_k = {}
    for r in ok:
        por_k.setdefault((r["tf"], r["k"]), []).append(r["dentro"]["bruto_op_pct"])
    resumo["bruto_op_mediano_por_tf_k"] = {"%dmin k=%d" % key: round(med(v), 4) for key, v in sorted(por_k.items())}
    print(json.dumps(resumo, ensure_ascii=False, indent=1))
    os.makedirs(os.path.join(HERE, "trader", "grafico"), exist_ok=True)
    json.dump({"resumo": resumo, "todas": res}, open(os.path.join(HERE, "trader", "grafico", "confluencia.json"), "w"), ensure_ascii=False)


if __name__ == "__main__":
    main()
