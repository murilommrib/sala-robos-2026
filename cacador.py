#!/usr/bin/env python3
"""Robô Caçador: varre várias criptos em velas de 1 hora, escolhe as melhores e opera
mais de uma moeda no mesmo dia, sempre que há sinal gráfico.

Regras (simulação vela a vela, só usando o que já aconteceu):
  - Até K posições abertas ao mesmo tempo (cada uma usa 1/K do patrimônio na hora da entrada).
  - No fechamento de cada vela: junta os sinais de todas as moedas sem posição/ordem,
    descarta moedas com pouco volume (média de 30 dias < US$ 10 mi/dia) e ordena pela
    força da tendência ((preço - média de 50) / ATR, a favor do lado). As melhores ocupam
    as vagas livres.
  - Entrada: ordem limitada `off` ATR atrás (maker, vale 3 velas) ou a mercado na abertura
    seguinte (taker + slippage). Saída: stop ks*ATR (taker+slip), alvo kt*ATR (maker), ou
    tempo H velas (taker+slip). Stop primeiro, alvo só depois da vela de entrada.
Teste encadeado: configuração escolhida só com os 2 anos anteriores; anos de teste 2023-2026.
Critérios (definidos antes de rodar): resultado encadeado > 0, Sharpe > 1, mais da metade dos
anos positivos, positivo com +0,07% de custo extra por operação, pior queda melhor que -40%.
Nenhuma ordem real é enviada.
"""
import csv, json, math, os, sys, datetime as dt
from multiprocessing import Pool
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import grafico as G

DATA = os.path.join(HERE, "trader", "data_1h_multi")
MAKER, TAKER, SLIP = 0.0002, 0.0005, 0.0005
EXTRA = 0.0007
K = 3
TF = int(os.environ.get("TF", "1"))      # horas por vela (1 ou 4)
STEP = 3600 * TF
VOL_MIN = 10e6
METODOS = list(G.METODOS)
GRID = [dict(m=m, ex=ex, ks=ks, kt=kt, H=H) for m in METODOS for ex in ("lim25", "lim50", "mercado")
        for ks in (1.0, 2.0) for kt in (1.5, 3.0) for H in ((8, 24) if os.environ.get("TF", "1") == "1" else (6, 18))]
TEST_YEARS = [2023, 2024, 2025, 2026]
T0 = int(dt.datetime(2021, 1, 1, tzinfo=dt.timezone.utc).timestamp())
T1 = int(dt.datetime(2026, 10, 1, tzinfo=dt.timezone.utc).timestamp())
NT = (T1 - T0) // (3600 * int(os.environ.get("TF", "1")))

COINS, BARS, IDX, SIG, ATR, SCORE, VOLOK = [], {}, {}, {}, {}, {}, {}


def configurar(tf, t0, t1):
    """Ajusta a grade de tempo (usado pelo robô ao vivo)."""
    global TF, STEP, T0, T1, NT
    TF, STEP, T0, T1 = tf, 3600 * tf, t0, t1
    NT = (T1 - T0) // STEP


def carregar_linhas(linhas):
    """Mesmo que carregar(), mas com as velas já em memória: {moeda: [(t,o,h,l,c,vol_usd), ...]}."""
    for L in (COINS, BARS, IDX, SIG, ATR, SCORE, VOLOK):
        L.clear()
    for c in sorted(linhas):
        _preparar(c, linhas[c], minimo=200)


def carregar():
    for f in sorted(os.listdir(DATA)):
        if not f.endswith(".csv"):
            continue
        c = f[:-4]
        rows = [(int(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])) for r in csv.reader(open(os.path.join(DATA, f)))]
        _preparar(c, rows, minimo=20000 // TF)


def _preparar(c, rows, minimo):
        rows = [r for r in rows if T0 <= r[0] < T1]
        if TF > 1:
            agg = []
            for r in rows:
                k0 = r[0] - (r[0] - T0) % STEP
                if agg and agg[-1][0] == k0:
                    a = agg[-1]; agg[-1] = (k0, a[1], max(a[2], r[2]), min(a[3], r[3]), r[4], a[5] + r[5])
                else:
                    agg.append((k0,) + tuple(r[1:]))
            rows = agg
        if len(rows) < minimo:
            return
        COINS.append(c)
        b = [r[:5] for r in rows]
        BARS[c] = b
        ix = [-1] * NT
        for i, r in enumerate(rows):
            ix[(r[0] - T0) // STEP] = i
        IDX[c] = ix
        A = G.atr(b); ATR[c] = A
        e50 = G.ema([x[4] for x in b], 50)
        SCORE[c] = [((b[i][4] - e50[i]) / A[i]) if (A[i] and e50[i]) else 0.0 for i in range(len(b))]
        v = [r[5] for r in rows]; s = 0.0; ok = []
        for i in range(len(v)):
            s += v[i]
            if i >= 720 // TF: s -= v[i - 720 // TF]
            ok.append(i >= 720 // TF and s / 30 >= VOL_MIN)
        VOLOK[c] = ok
        SIG[c] = {m: G.signals(m, b) for m in METODOS}


def simular(cfg, extra=0.0, pode=None, estado=None):
    """pode(k) -> (bool, motivo): se False, o sinal da vela k não vira ordem (ex.: Mac dormindo).
    estado: dict que recebe posições/ordens finais e sinais perdidos (para o robô ao vivo)."""
    """Devolve ({dia: patrimônio marcado a mercado}, lista de operações)."""
    m, ks, kt, H = cfg["m"], cfg["ks"], cfg["kt"], cfg["H"]
    off = {"lim25": 0.25, "lim50": 0.5}.get(cfg["ex"])
    eq = 1.0
    pos = {}        # moeda -> dict(lado, e, sp, tp, tam, i_in, i_fim)
    ordens = {}     # moeda -> dict(lado, L, atr, k_sinal, tam?)
    trades, dias = [], {}
    for k in range(NT):
        # 1) posições abertas
        for c in list(pos):
            i = IDX[c][k]
            if i < 0: continue
            p = pos[c]; o, h, l, cl = BARS[c][i][1:5]; sd = p["lado"]
            x = how = None
            if (l <= p["sp"]) if sd == 1 else (h >= p["sp"]):
                x, how = (min(p["sp"], o) if sd == 1 else max(p["sp"], o)) if i > p["i_in"] else p["sp"], "stop"
            elif i > p["i_in"] and ((h > p["tp"]) if sd == 1 else (l < p["tp"])):
                x, how = p["tp"], "alvo"
            elif i >= p["i_fim"]:
                x, how = cl, "tempo"
            if x is not None:
                g = sd * (x / p["e"] - 1)
                cost = p["c_in"] + (MAKER if how == "alvo" else TAKER + SLIP) + extra
                eq += p["tam"] * (g - cost)
                trades.append((BARS[c][p["i_in"]][0], BARS[c][i][0] + STEP, c, sd, p["e"], x, how, g - cost))
                del pos[c]
                p["saiu_k"] = k
        # 2) ordens pendentes (mais antigas primeiro)
        for c in sorted(ordens, key=lambda c: ordens[c]["k"]):
            q = ordens[c]; i = IDX[c][k]
            if k > q["k"] + 3:
                del ordens[c]; continue
            if i < 0 or k == q["k"]: continue
            o, h, l, cl = BARS[c][i][1:5]; sd = q["lado"]
            if q["L"] is None:
                e, c_in = o * (1 + sd * SLIP), TAKER          # a mercado na abertura
                fill = True
            else:
                fill = (l < q["L"]) if sd == 1 else (h > q["L"])
                e = (min(q["L"], o) if sd == 1 else max(q["L"], o)); c_in = MAKER
            if not fill: continue
            del ordens[c]
            if len(pos) >= K: continue
            sp = e - sd * ks * q["atr"]; tp = e + sd * kt * q["atr"]
            p = {"lado": sd, "e": e, "sp": sp, "tp": tp, "tam": eq / K, "i_in": i, "i_fim": i + H - 1, "c_in": c_in}
            if (l <= sp) if sd == 1 else (h >= sp):
                g = sd * (sp / e - 1); eq += p["tam"] * (g - c_in - TAKER - SLIP - extra)
                trades.append((BARS[c][i][0], BARS[c][i][0] + STEP, c, sd, e, sp, "stop", g - c_in - TAKER - SLIP - extra))
            else:
                pos[c] = p
        # 3) sinais novos no fechamento desta vela
        livres = K - len(pos) - len(ordens)
        if livres > 0:
            cand = []
            for c in COINS:
                if c in pos or c in ordens: continue
                i = IDX[c][k]
                if i < 1: continue
                s = SIG[c][m][i]
                if not s or not ATR[c][i] or not VOLOK[c][i]: continue
                cand.append((s * SCORE[c][i], c, s, i))
            cand.sort(reverse=True)
            if cand and pode is not None:
                ok, motivo = pode(k)
                if not ok:
                    if estado is not None:
                        estado.setdefault("perdidos", []).extend([[T0 + k * STEP, c, s, motivo] for _, c, s, _ in cand[:livres]])
                    cand = []
            for sc, c, s, i in cand[:livres]:
                cl = BARS[c][i][4]
                ordens[c] = {"lado": s, "L": None if off is None else cl - s * off * ATR[c][i], "atr": ATR[c][i], "k": k}
        # patrimônio marcado a mercado no fim do dia
        if (k + 1) % (24 // TF) == 0:
            mtm = eq
            for c, p in pos.items():
                i = IDX[c][k]
                if i >= 0: mtm += p["tam"] * (p["lado"] * (BARS[c][i][4] / p["e"] - 1))
            dias[dt.datetime.utcfromtimestamp(T0 + k * STEP).strftime("%Y-%m-%d")] = mtm
    if NT and NT % (24 // TF) != 0:                 # dia em andamento: marca a mercado até a última vela
        k = NT - 1; mtm = eq
        for c, p in pos.items():
            i = IDX[c][k]
            if i >= 0: mtm += p["tam"] * (p["lado"] * (BARS[c][i][4] / p["e"] - 1))
        dias[dt.datetime.utcfromtimestamp(T0 + k * STEP).strftime("%Y-%m-%d")] = mtm
    if estado is not None:
        estado["pos"] = {c: {"lado": p["lado"], "e": p["e"], "sp": p["sp"], "tp": p["tp"], "tam": p["tam"], "t_in": BARS[c][p["i_in"]][0]} for c, p in pos.items()}
        estado["ordens"] = {c: {"lado": q["lado"], "L": q["L"], "t_sinal": T0 + q["k"] * STEP} for c, q in ordens.items()}
        estado["eq_realizado"] = eq
    return dias, trades


def stats(dias, d0, d1):
    ks = sorted(d for d in dias if d0 <= d <= d1)
    if len(ks) < 2: return None
    prev = [d for d in dias if d < d0]
    base = dias[max(prev)] if prev else 1.0
    eq = [dias[d] / base for d in ks]
    rs = [eq[0] - 1] + [eq[i] / eq[i - 1] - 1 for i in range(1, len(eq))]
    m = sum(rs) / len(rs); sd = (sum((x - m) ** 2 for x in rs) / len(rs)) ** .5 or 1e-12
    pk, mdd = 1.0, 0.0
    for v in eq: pk = max(pk, v); mdd = min(mdd, v / pk - 1)
    return {"ret": eq[-1] - 1, "sharpe": m / sd * 365 ** .5, "mdd": mdd, "rs": rs}


def run_cfg(i):
    cfg = GRID[i]
    d, tr = simular(cfg)
    out = {"cfg": cfg, "anos": {}}
    for y in range(2021, 2027):
        s = stats(d, "%d-01-01" % y, "%d-12-31" % y)
        out["anos"][y] = {k: s[k] for k in ("ret", "sharpe", "mdd")} if s else None
    out["dias"] = d
    out["n"] = len(tr)
    out["bruto_medio"] = sum(t[-1] for t in tr) / len(tr) if tr else None
    return out


def main():
    carregar()
    print("Moedas:", ", ".join(COINS), "| configurações:", len(GRID), flush=True)
    with Pool(max(1, os.cpu_count() or 1)) as pool:
        R = pool.map(run_cfg, range(len(GRID)))
    # escolha encadeada: melhor Sharpe nos 2 anos anteriores
    chain, chain_x, por_ano = [], [], []
    for y in TEST_YEARS:
        def sel(r):
            s = stats(r["dias"], "%d-01-01" % (y - 2), "%d-12-31" % (y - 1))
            return s["sharpe"] if s else -9
        best = max(R, key=sel)
        s = stats(best["dias"], "%d-01-01" % y, "%d-12-31" % y)
        chain += s["rs"]
        dx, _ = simular(best["cfg"], extra=EXTRA)
        sx = stats(dx, "%d-01-01" % y, "%d-12-31" % y); chain_x += sx["rs"]
        por_ano.append({"ano": y, "cfg": best["cfg"], "ret_pct": round(100 * s["ret"], 1), "sharpe": round(s["sharpe"], 2),
                        "queda_pct": round(100 * s["mdd"], 1), "sharpe_escolha": round(sel(best), 2)})
        print("  %d: %s -> %+.1f%% (Sharpe %.2f, queda %.1f%%); estresse %+.1f%%" % (y, best["cfg"], 100 * s["ret"], s["sharpe"], 100 * s["mdd"], 100 * sx["ret"]), flush=True)
    def agg(rs):
        e, pk, mdd = 1.0, 1.0, 0.0
        for v in rs: e *= 1 + v; pk = max(pk, e); mdd = min(mdd, e / pk - 1)
        m = sum(rs) / len(rs); sd = (sum((x - m) ** 2 for x in rs) / len(rs)) ** .5 or 1e-12
        return {"ret_pct": round(100 * (e - 1), 1), "sharpe": round(m / sd * 365 ** .5, 2), "queda_pct": round(100 * mdd, 1)}
    A, X = agg(chain), agg(chain_x)
    crit = [A["ret_pct"] > 0, A["sharpe"] > 1, sum(1 for p in por_ano if p["ret_pct"] > 0) > len(por_ano) / 2, X["ret_pct"] > 0, A["queda_pct"] > -40]
    # visão geral: quantas configurações ficaram positivas em 2023-2026 (sem escolha)
    pos_all = 0; best_all = None
    for r in R:
        s = stats(r["dias"], "2023-01-01", "2026-12-31")
        if s and s["ret"] > 0: pos_all += 1
        if s and (best_all is None or s["sharpe"] > best_all[0]): best_all = (s["sharpe"], r["cfg"], s["ret"])
    por_metodo = {}
    for r in R:
        s = stats(r["dias"], "2021-01-01", "2026-12-31")
        if s: por_metodo.setdefault(r["cfg"]["m"], []).append(s["ret"])
    res = {"moedas": COINS, "K": K, "encadeado": A, "estresse": X, "por_ano": por_ano, "criterios": crit, "aprovado": all(crit),
           "configs_positivas_2023_2026": "%d de %d" % (pos_all, len(R)),
           "melhor_olhando_o_teste": {"sharpe": round(best_all[0], 2), "cfg": best_all[1], "ret_pct": round(100 * best_all[2], 1)},
           "mediana_por_metodo_2021_2026_pct": {m: round(100 * sorted(v)[len(v) // 2], 1) for m, v in por_metodo.items()},
           "ops_por_dia_media": round(sum(r["n"] for r in R) / len(R) / (NT * TF / 24), 2)}
    print(json.dumps({k: v for k, v in res.items() if k != "por_ano"}, ensure_ascii=False, indent=1))
    os.makedirs(os.path.join(HERE, "trader", "grafico"), exist_ok=True)
    res["velas_horas"] = TF
    json.dump(res, open(os.path.join(HERE, "trader", "grafico", "cacador_%dh.json" % TF), "w"), ensure_ascii=False)


if __name__ == "__main__":
    main()
