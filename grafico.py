#!/usr/bin/env python3
"""Robôs de análise gráfica operando o dia todo (várias operações por dia).

9 métodos de candlestick, price action e indicadores, em velas de 15 ou 60 minutos
de BTC e ETH. Cada sinal entra na ABERTURA da vela seguinte; saída por stop ou
alvo medidos em ATR(14), ou após H velas. Comprado e vendido, uma posição por vez,
sem alavancagem. Teste encadeado ano a ano (2021-2026), parâmetros escolhidos só
nos 2 anos anteriores. Custos por lado: pessimista 0,10%, otimista 0,03%.

Uso: python3 grafico.py <metodo>   (ou "lista")
Dados: trader/data_5m (baixados por intraday.py). Nenhuma ordem é enviada.
"""
import csv, json, math, os, sys, datetime as dt

COINS = ["BTC", "ETH"]
DATA = "trader/data_5m"
TEST_YEARS = list(range(2021, 2027))
LAST_DAY = "2026-09-30"
COSTS = {"pessimista": 0.0010, "otimista": 0.0003}
GRID = [dict(tf=tf, ks=ks, kt=kt, H=H) for tf in (15, 60) for ks in (1.0, 2.0) for kt in (1.5, 3.0) for H in (8, 24)]


def months():
    y, m = 2019, 1
    while (y, m) <= (2026, 9):
        yield "%04d-%02d" % (y, m)
        m += 1
        if m == 13:
            y, m = y + 1, 1


_RAW = {}


def load(coin, tf):
    """Velas de tf minutos: lista de (t, o, h, l, c) com t em segundos UTC."""
    if coin in _RAW:
        return resample(_RAW[coin], tf)
    rows = []
    for ym in months():
        p = os.path.join(DATA, "%sUSDT-%s.csv" % (coin, ym))
        if not os.path.exists(p):
            continue
        with open(p) as fh:
            for t, o, h, l, c in csv.reader(fh):
                rows.append((int(t), float(o), float(h), float(l), float(c)))
    rows.sort()
    _RAW[coin] = rows
    return resample(rows, tf)


def resample(rows, tf):
    out, cur, key = [], None, None
    step = tf * 60
    for t, o, h, l, c in rows:
        k = t - t % step
        if k != key:
            if cur:
                out.append(tuple(cur))
            key, cur = k, [k, o, h, l, c]
        else:
            cur[2] = max(cur[2], h); cur[3] = min(cur[3], l); cur[4] = c
    if cur:
        out.append(tuple(cur))
    return out


# ------------------------------------------------------------------ indicadores

def ema(x, n):
    out, e, a = [None] * len(x), None, 2 / (n + 1)
    for i, v in enumerate(x):
        e = v if e is None else a * v + (1 - a) * e
        out[i] = e if i >= n - 1 else None
    return out


def atr(b, n=14):
    out, a = [None] * len(b), None
    for i in range(1, len(b)):
        tr = max(b[i][2] - b[i][3], abs(b[i][2] - b[i - 1][4]), abs(b[i][3] - b[i - 1][4]))
        a = tr if a is None else (a * (n - 1) + tr) / n
        out[i] = a if i >= n else None
    return out


def rsi(x, n):
    out = [None] * len(x); g = l = None
    for i in range(1, len(x)):
        d = x[i] - x[i - 1]; up, dn = max(d, 0), max(-d, 0)
        if g is None:
            g, l = up, dn
        else:
            g = (g * (n - 1) + up) / n; l = (l * (n - 1) + dn) / n
        if i >= n:
            out[i] = 100.0 if l == 0 else 100 - 100 / (1 + g / l)
    return out


def boll(x, n=20, k=2.0):
    up, lo, mid, bw = [None] * len(x), [None] * len(x), [None] * len(x), [None] * len(x)
    s = s2 = 0.0
    for i, v in enumerate(x):
        s += v; s2 += v * v
        if i >= n:
            s -= x[i - n]; s2 -= x[i - n] ** 2
        if i >= n - 1:
            m = s / n; sd = math.sqrt(max(s2 / n - m * m, 0))
            mid[i], up[i], lo[i] = m, m + k * sd, m - k * sd
            bw[i] = (2 * k * sd) / m if m else None
    return up, lo, mid, bw


def vwap_day(b):
    out, day, pv, vv = [None] * len(b), None, 0.0, 0.0
    for i, (t, o, h, l, c) in enumerate(b):
        d = t // 86400
        if d != day:
            day, pv, vv = d, 0.0, 0.0
        tp = (h + l + c) / 3
        pv += tp; vv += 1          # sem volume no cache: média do preço típico do dia (aproximação)
        out[i] = pv / vv
    return out


# ------------------------------------------------------------------ sinais (+1 compra, -1 venda, 0 nada) no fechamento da vela i

def signals(name, b):
    c = [x[4] for x in b]; o = [x[1] for x in b]; h = [x[2] for x in b]; l = [x[3] for x in b]
    e20, e50, e200 = ema(c, 20), ema(c, 50), ema(c, 200)
    S = [0] * len(b)
    if name == "engolfo":
        for i in range(1, len(b)):
            if e50[i] is None: continue
            bull = c[i - 1] < o[i - 1] and c[i] > o[i] and c[i] >= o[i - 1] and o[i] <= c[i - 1]
            bear = c[i - 1] > o[i - 1] and c[i] < o[i] and c[i] <= o[i - 1] and o[i] >= c[i - 1]
            S[i] = 1 if bull and c[i] > e50[i] else -1 if bear and c[i] < e50[i] else 0
    elif name == "pinbar":
        up, lo, _, _ = boll(c)
        for i in range(len(b)):
            if up[i] is None: continue
            body = abs(c[i] - o[i]); rng = h[i] - l[i] or 1e-12
            lower = min(o[i], c[i]) - l[i]; upper = h[i] - max(o[i], c[i])
            if lower >= 2 * body and (c[i] - l[i]) / rng >= 0.66 and l[i] <= lo[i]:
                S[i] = 1
            elif upper >= 2 * body and (h[i] - c[i]) / rng >= 0.66 and h[i] >= up[i]:
                S[i] = -1
    elif name == "insidebar":
        for i in range(2, len(b)):
            if e50[i] is None: continue
            inside = h[i - 1] <= h[i - 2] and l[i - 1] >= l[i - 2]
            if inside and c[i] > h[i - 1] and c[i] > e50[i]:
                S[i] = 1
            elif inside and c[i] < l[i - 1] and c[i] < e50[i]:
                S[i] = -1
    elif name == "rompimento":
        N = 48
        for i in range(N, len(b)):
            hi = max(h[i - N:i]); lo_ = min(l[i - N:i])
            S[i] = 1 if c[i] > hi else -1 if c[i] < lo_ else 0
    elif name == "rsi2":
        r = rsi(c, 2)
        for i in range(len(b)):
            if r[i] is None or e200[i] is None: continue
            S[i] = 1 if r[i] < 10 and c[i] > e200[i] else -1 if r[i] > 90 and c[i] < e200[i] else 0
    elif name == "vwap":
        vw = vwap_day(b)
        for i in range(1, len(b)):
            if e50[i] is None or e20[i] is None: continue
            if e20[i] > e50[i] and l[i] <= vw[i] < c[i] and c[i - 1] > vw[i - 1]:
                S[i] = 1
            elif e20[i] < e50[i] and h[i] >= vw[i] > c[i] and c[i - 1] < vw[i - 1]:
                S[i] = -1
    elif name == "macd":
        f, s_ = ema(c, 12), ema(c, 26)
        m = [None if f[i] is None or s_[i] is None else f[i] - s_[i] for i in range(len(c))]
        mm = [x if x is not None else 0.0 for x in m]
        sig = ema(mm, 9)
        for i in range(1, len(b)):
            if m[i] is None or m[i - 1] is None or sig[i] is None or sig[i - 1] is None or e200[i] is None: continue
            up_ = m[i - 1] <= sig[i - 1] and m[i] > sig[i]
            dn_ = m[i - 1] >= sig[i - 1] and m[i] < sig[i]
            S[i] = 1 if up_ and c[i] > e200[i] else -1 if dn_ and c[i] < e200[i] else 0
    elif name == "squeeze":
        up, lo, _, bw = boll(c)
        for i in range(100, len(b)):
            if bw[i - 1] is None: continue
            window = [x for x in bw[i - 100:i] if x is not None]
            if window and bw[i - 1] <= min(window) * 1.05:
                S[i] = 1 if c[i] > up[i] else -1 if c[i] < lo[i] else 0
    elif name == "tres":
        for i in range(3, len(b)):
            if e50[i] is None: continue
            soldiers = all(c[k] > o[k] and c[k] > c[k - 1] for k in (i - 2, i - 1, i))
            crows = all(c[k] < o[k] and c[k] < c[k - 1] for k in (i - 2, i - 1, i))
            S[i] = 1 if soldiers and c[i] > e50[i] else -1 if crows and c[i] < e50[i] else 0
    return S


METODOS = {
    "engolfo": "Engolfo (candlestick) a favor da tendência",
    "pinbar": "Pin bar (martelo / estrela cadente) nas bandas de Bollinger",
    "insidebar": "Inside bar: rompimento a favor da tendência",
    "rompimento": "Rompimento de suporte/resistência (máxima/mínima de 48 velas)",
    "rsi2": "RSI(2) em correção dentro da tendência",
    "vwap": "Pullback na VWAP do dia",
    "macd": "Cruzamento do MACD com filtro da média de 200",
    "squeeze": "Squeeze de Bollinger: rompimento após compressão",
    "tres": "Três soldados / três corvos a favor da tendência",
}


# ------------------------------------------------------------------ simulação

def trades(b, S, A, ks, kt, H):
    """Lista de (t_entrada, lado, ret_bruto). Entra na abertura da vela seguinte ao sinal."""
    out, i, n = [], 0, len(b)
    while i < n - 1:
        side = S[i]
        if not side or A[i] is None:
            i += 1; continue
        j = i + 1
        e = b[j][1]
        sp = e - side * ks * A[i]; tp = e + side * kt * A[i]
        x, k = None, j
        while k < n and k <= j + H - 1:
            o_, h_, l_, c_ = b[k][1], b[k][2], b[k][3], b[k][4]
            if (l_ <= sp) if side == 1 else (h_ >= sp):
                x = (min(sp, o_) if side == 1 else max(sp, o_)) if k > j else sp; break
            if (h_ >= tp) if side == 1 else (l_ <= tp):
                x = tp; break
            k += 1
        if x is None:
            k = min(j + H - 1, n - 1); x = b[k][4]
        out.append((b[j][0], side, side * (x / e - 1)))
        i = k + 1
    return out


def daily(trs, fee):
    d = {}
    for t, s, g in trs:
        day = dt.datetime.utcfromtimestamp(t).strftime("%Y-%m-%d")
        d[day] = (1 + d.get(day, 0.0)) * (1 + g - 2 * fee) - 1
    return d


def sharpe_days(dmap, start, end):
    d0, d1 = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    rs = []
    while d0 <= d1:
        rs.append(dmap.get(d0.isoformat(), 0.0)); d0 += dt.timedelta(days=1)
    n = len(rs) or 1; m = sum(rs) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in rs) / n) or 1e-12
    return m / sd * math.sqrt(365), rs


def run(metodo):
    res = {"metodo": metodo, "descricao": METODOS[metodo], "custos": COSTS, "moedas": {}}
    for coin in COINS:
        bars = {tf: load(coin, tf) for tf in (15, 60)}
        sig = {tf: signals(metodo, bars[tf]) for tf in (15, 60)}
        A = {tf: atr(bars[tf]) for tf in (15, 60)}
        cache = {}
        for p in GRID:
            trs = trades(bars[p["tf"]], sig[p["tf"]], A[p["tf"]], p["ks"], p["kt"], p["H"])
            cache[json.dumps(p, sort_keys=True)] = trs
        chains = {k: [] for k in list(COSTS) + ["bruto"]}
        per_year, all_tr = [], []
        for y in TEST_YEARS:
            s, e = "%d-01-01" % y, (LAST_DAY if y == 2026 else "%d-12-31" % y)
            best = max(cache, key=lambda k: sharpe_days(daily(cache[k], COSTS["pessimista"]), "%d-01-01" % (y - 2), "%d-12-31" % (y - 1))[0])
            for cname, fee in list(COSTS.items()) + [("bruto", 0.0)]:
                chains[cname] += sharpe_days(daily(cache[best], fee), s, e)[1]
            yr = [t for t in cache[best] if s <= dt.datetime.utcfromtimestamp(t[0]).strftime("%Y-%m-%d") <= e]
            all_tr += yr
            eq = 1.0
            for v in sharpe_days(daily(yr, COSTS["pessimista"]), s, e)[1]:
                eq *= 1 + v
            per_year.append({"ano": y, "param": json.loads(best), "return_pct": round(100 * (eq - 1), 1), "trades": len(yr)})
        st = {}
        for cname, rs in chains.items():
            eq, peak, mdd = 1.0, 1.0, 0.0
            for v in rs:
                eq *= 1 + v; peak = max(peak, eq); mdd = min(mdd, eq / peak - 1)
            n = len(rs) or 1; m = sum(rs) / n; sd = math.sqrt(sum((x - m) ** 2 for x in rs) / n) or 1e-12
            st[cname] = {"return_pct": round(100 * (eq - 1), 1), "max_drawdown_pct": round(100 * mdd, 1), "sharpe": round(m / sd * math.sqrt(365), 2)}
        g = [t[2] for t in all_tr]
        st["trades"] = len(g)
        st["trades_por_dia"] = round(len(g) / len(chains["bruto"]), 2) if chains["bruto"] else 0
        st["acerto_bruto_pct"] = round(100 * sum(1 for x in g if x > 0) / len(g), 1) if g else None
        st["media_bruta_por_trade_pct"] = round(100 * sum(g) / len(g), 3) if g else None
        st["anos_com_lucro"] = sum(1 for x in per_year if x["return_pct"] > 0)
        st["anos"] = len(per_year)
        st["por_ano"] = per_year
        res["moedas"][coin] = st
        P, O, B = st["pessimista"], st["otimista"], st["bruto"]
        print("  %s %-4s bruto %+9.1f%% | otimista %+9.1f%% | pessimista %+8.1f%% (Sharpe %5.2f, queda %6.1f%%) | %5.2f trades/dia | acerto %4.1f%% | média bruta %+.3f%% | anos+ %d/6"
              % (metodo, coin, B["return_pct"], O["return_pct"], P["return_pct"], P["sharpe"], P["max_drawdown_pct"],
                 st["trades_por_dia"], st["acerto_bruto_pct"] or 0, st["media_bruta_por_trade_pct"] or 0, st["anos_com_lucro"]), flush=True)
    A_ = [res["moedas"][c] for c in COINS]
    res["criterios"] = [all(a["pessimista"]["return_pct"] > 0 for a in A_),
                        all(a["anos_com_lucro"] > a["anos"] / 2 for a in A_),
                        all(a["pessimista"]["sharpe"] > 1 for a in A_)]
    res["aprovado"] = all(res["criterios"])
    print("  VEREDITO %s: %s [%s]" % (metodo, "APROVADO" if res["aprovado"] else "reprovado", " ".join("ok" if c else "x" for c in res["criterios"])))
    os.makedirs("trader/grafico", exist_ok=True)
    with open("trader/grafico/%s.json" % metodo, "w") as fh:
        json.dump(res, fh, ensure_ascii=False)


if __name__ == "__main__":
    m = sys.argv[1] if len(sys.argv) > 1 else "lista"
    if m == "lista":
        for k, v in METODOS.items():
            print(k, "-", v)
    else:
        run(m)
