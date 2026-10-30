#!/usr/bin/env python3
"""Day trade em cripto (BTC, ETH) — 4 estratégias clássicas, comprado e vendido,
sempre zerado no fim do dia (UTC). Teste encadeado ano a ano, 2021 a 2026.

Estratégias (uma operação por dia no máximo):
  1. Rompimento da faixa de abertura (ORB): faixa dos primeiros 30 ou 60 min a
     partir da 00:00 UTC ou da abertura da bolsa de Nova York; entra no primeiro
     fechamento fora da faixa; stop no meio ou no outro lado da faixa; alvo 1R,
     2R ou só no fim do dia.
  2. Momentum intradiário: a direção do dia até a hora T (6h, 12h, 18h UTC)
     decide o lado até o fim do dia.
  3. Reversão: se até a hora T o preço se afastou da abertura mais que k vezes
     a amplitude média dos últimos 20 dias, aposta contra até o fim do dia.
  4. Sessões: a direção da sessão europeia (7h-13h UTC) decide o lado na
     sessão americana (13h até 21h ou 24h UTC), seguindo ou contrariando.

Custos por lado (premissas): pessimista 0,10% (taxa a mercado 0,05% + slippage
0,05%); otimista 0,03% (ordem limitada). Parâmetros escolhidos só nos 2 anos
anteriores a cada ano de teste, com o custo pessimista. Sem alavancagem.
Taxa de financiamento ignorada (posições de poucas horas; efeito pequeno).

Dados: velas de 5 min da Binance (data.binance.vision). Nenhuma ordem é enviada.
"""
import csv, io, json, math, os, time, zipfile, urllib.request, datetime as dt
from concurrent.futures import ThreadPoolExecutor

COINS = ["BTC", "ETH"]
START, END = (2019, 1), (2026, 9)
TEST_YEARS = list(range(2021, 2027))
LAST_DAY = "2026-09-30"
COSTS = {"pessimista": 0.0010, "otimista": 0.0003}
DATA = "trader/data_5m"
OUT = "trader/intraday.json"
UA = "Mozilla/5.0 (robo-trading backtest)"
BARS = 288


def months():
    y, m = START
    while (y, m) <= END:
        yield "%04d-%02d" % (y, m)
        m += 1
        if m == 13:
            y, m = y + 1, 1


def fetch(url):
    for i in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
        except Exception:
            pass
        time.sleep(2 * (i + 1))
    return None


def get_month(coin, ym):
    os.makedirs(DATA, exist_ok=True)
    sym = coin + "USDT"
    path = os.path.join(DATA, "%s-%s.csv" % (sym, ym))
    if os.path.exists(path):
        return
    blob = fetch("https://data.binance.vision/data/spot/monthly/klines/%s/5m/%s-5m-%s.zip" % (sym, sym, ym))
    rows = []
    if blob:
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            text = z.read(z.namelist()[0]).decode()
        for r in csv.reader(io.StringIO(text)):
            if not r or not r[0].strip().isdigit():
                continue
            t = int(r[0])
            t = t // 1000000 if t > 10**14 else t // 1000
            rows.append((t, r[1], r[2], r[3], r[4]))
    with open(path, "w", newline="") as fh:
        csv.writer(fh).writerows(rows)


def load(coin):
    """{dia: [(o,h,l,c) x 288]} só com dias completos."""
    days = {}
    for ym in months():
        with open(os.path.join(DATA, "%sUSDT-%s.csv" % (coin, ym))) as fh:
            for t, o, h, l, c in csv.reader(fh):
                t = int(t)
                d = dt.datetime.utcfromtimestamp(t)
                slot = (d.hour * 60 + d.minute) // 5
                days.setdefault(d.strftime("%Y-%m-%d"), {})[slot] = (float(o), float(h), float(l), float(c))
    full = {}
    for d, s in days.items():
        if len(s) == BARS:
            full[d] = [s[i] for i in range(BARS)]
    return full


def ny_open_slot(day):
    """Abertura de Nova York (9:30) em barras de 5 min UTC: 13:30 no horário de verão, 14:30 no inverno."""
    y = int(day[:4])
    d = dt.date.fromisoformat(day)
    mar = dt.date(y, 3, 8)
    dst_start = mar + dt.timedelta(days=(6 - mar.weekday()) % 7)
    nov = dt.date(y, 11, 1)
    dst_end = nov + dt.timedelta(days=(6 - nov.weekday()) % 7)
    return (13 * 60 + 30) // 5 if dst_start <= d < dst_end else (14 * 60 + 30) // 5


# ------------------------------------------------------------------ estratégias
# Cada uma devolve (lado, preço_entrada, preço_saída) ou None.

def orb(D, day, ctx, start, n, stop, target):
    s0 = 0 if start == "utc" else ny_open_slot(day)
    if s0 + n >= BARS:
        return None
    hi = max(b[1] for b in D[s0:s0 + n])
    lo = min(b[2] for b in D[s0:s0 + n])
    for i in range(s0 + n, BARS - 1):
        c = D[i][3]
        side = 1 if c > hi else -1 if c < lo else 0
        if not side:
            continue
        sp = (hi + lo) / 2 if stop == "meio" else (lo if side == 1 else hi)
        risk = (c - sp) * side
        if risk <= 0:
            return None
        tp = c + side * target * risk if target else None
        for b in D[i + 1:]:
            if (b[2] <= sp) if side == 1 else (b[1] >= sp):
                fill = min(sp, b[0]) if side == 1 else max(sp, b[0])   # abriu além do stop: sai na abertura
                return side, c, fill
            if tp is not None and ((b[1] >= tp) if side == 1 else (b[2] <= tp)):
                return side, c, tp
        return side, c, D[-1][3]
    return None


def momentum(D, day, ctx, hour):
    k = hour * 12
    move = D[k - 1][3] / D[0][0] - 1
    if move == 0:
        return None
    side = 1 if move > 0 else -1
    return side, D[k - 1][3], D[-1][3]


def reversal(D, day, ctx, hour, k):
    rng = ctx.get("avg_range")
    if not rng:
        return None
    j = hour * 12
    move = D[j - 1][3] / D[0][0] - 1
    if abs(move) < k * rng:
        return None
    side = -1 if move > 0 else 1
    return side, D[j - 1][3], D[-1][3]


def sessions(D, day, ctx, mode, end_h):
    eu = D[13 * 12 - 1][3] / D[7 * 12][0] - 1
    if eu == 0:
        return None
    side = 1 if eu > 0 else -1
    if mode == "contra":
        side = -side
    return side, D[13 * 12 - 1][3], D[end_h * 12 - 1][3]


STRATS = {
    "Rompimento da abertura": (orb, [dict(start=s, n=n, stop=st, target=t)
                                     for s in ("utc", "ny") for n in (6, 12) for st in ("meio", "lado") for t in (1, 2, None)]),
    "Momentum intradiário": (momentum, [dict(hour=h) for h in (6, 12, 18)]),
    "Reversão após exagero": (reversal, [dict(hour=h, k=k) for h in (6, 12, 18) for k in (0.5, 1.0)]),
    "Sessões Europa → EUA": (sessions, [dict(mode=m, end_h=e) for m in ("seguir", "contra") for e in (21, 24)]),
}


# ------------------------------------------------------------------ simulação

def day_gross(data, fn, p):
    """{dia: (operou, retorno bruto)}."""
    out = {}
    ranges = []
    for d in sorted(data):
        D = data[d]
        ctx = {"avg_range": (sum(ranges[-20:]) / 20) if len(ranges) >= 20 else None}
        r = fn(D, d, ctx, **p)
        if r:
            side, e, x = r
            out[d] = (True, side * (x / e - 1))
        else:
            out[d] = (False, 0.0)
        ranges.append(max(b[1] for b in D) / min(b[2] for b in D) - 1)
    return out


def net(g, fee):
    return {d: (v - 2 * fee if t else 0.0) for d, (t, v) in g.items()}


def sharpe(rs):
    n = len(rs) or 1
    m = sum(rs) / n
    sd = math.sqrt(sum((r - m) ** 2 for r in rs) / n) or 1e-12
    return m / sd * math.sqrt(365)


def in_year(d, y):
    return d.startswith(str(y)) and d <= LAST_DAY


def main():
    print("### Baixando velas de 5 minutos (BTC e ETH, 2019-2026)", flush=True)
    jobs = [(c, ym) for c in COINS for ym in months()]
    with ThreadPoolExecutor(max_workers=6) as ex:
        list(ex.map(lambda j: get_month(*j), jobs))
    out = {"generated_utc": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z", "costs": COSTS,
           "test_years": TEST_YEARS, "results": {}}
    for coin in COINS:
        data = load(coin)
        print("\n### %s: %d dias completos" % (coin, len(data)), flush=True)
        res = {}
        for name, (fn, grid) in STRATS.items():
            runs = {}
            for p in grid:
                key = json.dumps(p, sort_keys=True)
                g = day_gross(data, fn, p)
                runs[key] = {c: net(g, f) for c, f in COSTS.items()}
                runs[key]["bruto"] = net(g, 0.0)
            chain = {c: [] for c in list(COSTS) + ["bruto"]}
            dates = []
            per_year, trades_g = [], []
            for y in TEST_YEARS:
                best = max(runs, key=lambda k: sharpe([v for d, v in runs[k]["pessimista"].items()
                                                       if d[:4] in (str(y - 2), str(y - 1))]))
                for c in chain:
                    chain[c] += [v for d, v in sorted(runs[best][c].items()) if in_year(d, y)]
                dates += [d for d in sorted(runs[best]["pessimista"]) if in_year(d, y)]
                yr = [v for d, v in sorted(runs[best]["pessimista"].items()) if in_year(d, y)]
                eq = 1.0
                for v in yr:
                    eq *= 1 + v
                per_year.append({"ano": y, "param": json.loads(best), "return_pct": round(100 * (eq - 1), 1)})
            st = {}
            for c, rs in chain.items():
                eq, peak, mdd, curve = 1.0, 1.0, 0.0, []
                for v in rs:
                    eq *= 1 + v
                    peak = max(peak, eq)
                    mdd = min(mdd, eq / peak - 1)
                    curve.append(eq)
                st[c] = {"return_pct": round(100 * (eq - 1), 1), "max_drawdown_pct": round(100 * mdd, 1),
                         "sharpe": round(sharpe(rs), 2), "dias_operados": sum(1 for v in rs if v != 0),
                         "curva": [[d, round(e, 4)] for d, e in zip(dates, curve)]}
            nz = [v for v in chain["bruto"] if v != 0]
            st["media_bruta_por_trade_pct"] = round(100 * sum(nz) / len(nz), 3) if nz else None
            st["acerto_bruto_pct"] = round(100 * sum(1 for v in nz if v > 0) / len(nz), 1) if nz else None
            st["anos_com_lucro"] = sum(1 for x in per_year if x["return_pct"] > 0)
            st["anos"] = len(per_year)
            st["por_ano"] = per_year
            res[name] = st
            P, O, B = st["pessimista"], st["otimista"], st["bruto"]
            print("  %-24s bruto %+8.1f%% | otimista %+8.1f%% | pessimista %+8.1f%% (queda %6.1f%%, Sharpe %5.2f) | "
                  "média bruta/trade %+.3f%% | trades %d | anos+ %d/%d"
                  % (name, B["return_pct"], O["return_pct"], P["return_pct"], P["max_drawdown_pct"], P["sharpe"],
                     st["media_bruta_por_trade_pct"] or 0, P["dias_operados"], st["anos_com_lucro"], st["anos"]), flush=True)
        out["results"][coin] = res

    print("\n### VEREDITO (lucro com custo pessimista nos 2 ativos, lucro na maioria dos anos, Sharpe > 1)")
    out["verdict"] = {}
    for name in STRATS:
        A = [out["results"][c][name] for c in COINS]
        checks = [all(a["pessimista"]["return_pct"] > 0 for a in A),
                  all(a["anos_com_lucro"] > a["anos"] / 2 for a in A),
                  all(a["pessimista"]["sharpe"] > 1 for a in A)]
        out["verdict"][name] = {"criterios": checks, "aprovada": all(checks)}
        print("  %-24s %s  [%s]" % (name, "APROVADA" if all(checks) else "reprovada", " ".join("ok" if c else "x" for c in checks)))
    with open(OUT, "w") as fh:
        json.dump(out, fh)
    print("\nCusto de ida e volta: pessimista %.2f%%, otimista %.2f%% por operação. Nenhuma ordem enviada."
          % (200 * COSTS["pessimista"], 200 * COSTS["otimista"]))


if __name__ == "__main__":
    main()
