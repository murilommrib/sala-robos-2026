#!/usr/bin/env python3
"""Os robôs diários têm vantagem própria ou só acompanham o mercado?
Recria, com o MESMO código que roda ao vivo (sala.weights) e os mesmos custos, o retorno diário
de cada robô de 2020 até ontem; depois passa duas skills públicas (tradermonty, MIT):
 - residual-edge-analyzer: separa o retorno em "mercado" (cesta das 10 / BTC) e "vantagem própria";
 - backtest-expert: nota de robustez do teste.
Atenção: estes robôs foram escolhidos olhando esse mesmo período (análise "in_sample").
Financiamento: valor-padrão de 0,03%/dia (a Binance bloqueia a taxa real a partir do GitHub).
Simulação; nenhuma ordem real. Gerado pelo Claude."""
import sys, os, json, csv, math, subprocess, datetime as dt
HERE = os.path.dirname(os.path.abspath(__file__)); RAIZ = os.path.dirname(HERE)
sys.path.insert(0, RAIZ)
import sala as S
OUT = os.path.join(HERE, "vantagem"); os.makedirs(OUT, exist_ok=True)
INI, FIM = "2020-01-01", (dt.date.today() - dt.timedelta(days=1)).isoformat()
D = S.daily_closes(S.days_back(INI, 120)[0], FIM)
dias = []
d = dt.date.fromisoformat(INI)
while d.isoformat() <= FIM: dias.append(d.isoformat()); d += dt.timedelta(days=1)
ROB = [r for r in S.ROBOS if r["tipo"] == "diario"] + [r for r in S.ROBOS if r["id"] == "segurador"]
rets = {r["id"]: {} for r in ROB}; pesos = {r["id"]: {} for r in ROB}
cesta, btc = {}, {}
for day in dias:
    prev = S.days_back(day, 1)[0]
    r_dia = {c: D[c][day][3] / D[c][prev][3] - 1 for c in S.COINS if day in D[c] and prev in D[c]}
    if len(r_dia) < 5 or "BTC" not in r_dia: continue
    cesta[day] = sum(r_dia.values()) / len(r_dia); btc[day] = r_dia["BTC"]
    for r in ROB:
        atual = pesos[r["id"]]
        segunda = dt.date.fromisoformat(day).weekday() == 0
        if r["tipo"] == "referencia" and atual: w = atual
        elif r["id"] in S.SEMANAIS and atual and not segunda: w = atual
        else: w = S.weights(r, day, D)
        turn = sum(abs(w.get(c, 0) - atual.get(c, 0)) for c in set(w) | set(atual))
        ret = sum(x * r_dia.get(c, 0.0) for c, x in w.items())
        if r["tipo"] != "referencia": ret -= sum(x * S.FUNDING_DAY for x in w.values())
        ret -= (S.FEE if r["tipo"] != "referencia" else 0.0045) * turn
        pesos[r["id"]] = S.deriva(w, r_dia)
        rets[r["id"]][day] = ret
rets["gestor"] = {d0: sum(rets[k][d0] for k in ("tendo", "semanal", "calmo", "extremo")) / 4 for d0 in cesta if all(d0 in rets[k] for k in ("tendo", "semanal", "calmo", "extremo"))}
ops = [r["id"] for r in ROB if r["tipo"] == "diario"]
rets["carteira"] = {d0: sum(rets[k][d0] for k in ops) / len(ops) for d0 in cesta if all(d0 in rets[k] for k in ops)}
# regime de volatilidade: só com dados do passado
ds = sorted(cesta); vol, reg = {}, {}
for i, d0 in enumerate(ds):
    w = [cesta[x] for x in ds[max(0, i - 30):i]]
    if len(w) >= 20: m = sum(w) / len(w); vol[d0] = math.sqrt(sum((a - m) ** 2 for a in w) / len(w))
hist = []
for d0 in ds:
    if d0 in vol:
        h = hist[-365:]
        if len(h) >= 60: reg[d0] = "alta_vol" if vol[d0] > sorted(h)[len(h) // 2] else "baixa_vol"
        hist.append(vol[d0])
res = {}
VEND = os.path.join(HERE, "vendor_tradermonty")
for k in ops + ["gestor", "carteira", "segurador"]:
    dd = [d0 for d0 in ds if d0 in reg and d0 in rets[k]]
    fcsv, fcfg = os.path.join(OUT, k + ".csv"), os.path.join(OUT, k + ".json")
    with open(fcsv, "w", newline="") as f:
        wr = csv.writer(f); wr.writerow(["date", "strategy_return", "cesta_return", "btc_return", "volatility_regime"])
        for d0 in dd: wr.writerow([d0, rets[k][d0], cesta[d0], btc[d0], reg[d0]])
    json.dump({"schema_version": "1.0", "date_column": "date", "strategy_column": "strategy_return", "return_unit": "decimal",
               "frequency": "daily", "annualization_factor": 365,
               "primary_model": {"name": "cesta", "baseline_columns": ["cesta_return"]},
               "sensitivity_models": [{"name": "btc", "baseline_columns": ["btc_return"]}, {"name": "cesta_mais_btc", "baseline_columns": ["cesta_return", "btc_return"]}],
               "regime_columns": ["volatility_regime"], "rolling_window": 180, "minimum_observations": 250, "minimum_regime_observations": 60,
               "minimum_rolling_windows": 12, "hac_lags": "auto", "include_series": False,
               "data_declarations": {"baseline_selection": "predeclared", "strategy_return_basis": "net", "baseline_return_basis": "net",
                                     "analysis_scope": "in_sample", "universe_data": "not_applicable"}}, open(fcfg, "w"))
    rj = os.path.join(OUT, "residuo_" + k + ".json")
    subprocess.run([sys.executable, "-I", os.path.join(VEND, "analyze_residual_edge.py"), "--input", fcsv, "--config", fcfg,
                    "--output-json", rj, "--output-markdown", os.path.join(OUT, "residuo_" + k + ".md")], check=False)
    R = json.load(open(rj)) if os.path.exists(rj) else {}
    pm = (R.get("models") or {})
    x = [rets[k][d0] for d0 in dd]
    eq, pk, mdd = 1.0, 1.0, 0.0
    for v in x: eq *= 1 + v; pk = max(pk, eq); mdd = min(mdd, eq / pk - 1)
    ativos = [v for v in x if abs(v) > 1e-12]
    g = [v for v in ativos if v > 0]; p = [v for v in ativos if v < 0]
    bt_dir = os.path.join(OUT, "robustez_" + k); os.makedirs(bt_dir, exist_ok=True)
    if g and p:
        subprocess.run([sys.executable, "-I", os.path.join(VEND, "evaluate_backtest.py"), "--total-trades", str(len(ativos)),
                        "--win-rate", "%.2f" % (100 * len(g) / len(ativos)), "--avg-win-pct", "%.4f" % (100 * sum(g) / len(g)),
                        "--avg-loss-pct", "%.4f" % (-100 * sum(p) / len(p)), "--max-drawdown-pct", "%.2f" % (-100 * mdd),
                        "--years-tested", str(int(len(dd) / 365)), "--num-parameters", "2", "--slippage-tested", "--output-dir", bt_dir], check=False)
    bt = {}
    for fn in os.listdir(bt_dir):
        if fn.endswith(".json"): bt = json.load(open(os.path.join(bt_dir, fn)))
    res[k] = {"dias": len(dd), "inicio": dd[0], "fim": dd[-1], "total_pct": round(100 * (eq - 1), 1), "pior_queda_pct": round(100 * mdd, 1),
              "residuo": R.get("verdict"), "modelos": {m["name"]: {"r2": round(m["r_squared"], 3), "alpha_ano_pct": round(100 * m["alpha"]["annualized_arithmetic"], 1),
                                    "t_alpha": round(m["alpha"]["t_stat"], 2), "residual_edge_ratio": round(m["residual"]["residual_edge_ratio"], 2),
                                    "beta": {c["column"] if isinstance(c, dict) and "column" in c else str(i): c for i, c in enumerate(m.get("coefficients") or [])},
                                    "alpha_positivo_janelas": (m.get("rolling") or {}).get("positive_alpha_fraction"), "status": m["diagnostic_status"]} for m in pm} if isinstance(pm, list) else pm,
              "regimes": R.get("regime_analysis"), "robustez": {kk: bt.get(kk) for kk in ("decision", "verdict", "quality_score", "blocking_reasons", "profit_factor", "red_flags") if kk in bt}}
json.dump(res, open(os.path.join(OUT, "resumo.json"), "w"), ensure_ascii=False, indent=1)
print(json.dumps({k: [v["total_pct"], (v.get("residuo") or {}).get("status"), v["robustez"]] for k, v in res.items()}, ensure_ascii=False, indent=1))
