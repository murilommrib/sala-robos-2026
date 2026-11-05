#!/usr/bin/env python3
"""Teste da estratégia do vídeo (abertura de NY + FVG), com custos e sem olhar o futuro.
Regras, como no vídeo:
 1. Marca máxima e mínima da vela de 15 min que abre às 9:30 de Nova York (9:30-9:45).
 2. Em velas de 5 min, depois das 9:45, espera o preço ROMPER esse nível criando um FVG
    (vazio entre a vela 1 e a vela 3 de um movimento forte) do lado de fora da faixa.
 3. Espera o preço VOLTAR até o FVG e aparecer uma vela ENVOLVENTE a favor do rompimento.
 4. Entra; stop atrás do FVG; alvo de 3x o risco (3:1). Uma operação por dia.
Variações testadas (todas reportadas): entrada no fechamento da envolvente ou na abertura seguinte;
stop atrás do FVG ou atrás da envolvente; alvo 3:1 ou 2:1; operações até 12h ou 16h de NY.
Simulação com dados públicos; nenhuma ordem real. Gerado pelo Claude."""
import json, sys, time, urllib.request, datetime as dt, itertools
from zoneinfo import ZoneInfo
NY = ZoneInfo("America/New_York")
UA = {"User-Agent": "Mozilla/5.0"}

def get(url):
    for i in range(4):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30))
        except Exception as e:
            err = e; time.sleep(2 + 3 * i)
    raise err

def binance_5m(sym, ini, fim):
    out, t = [], int(ini.timestamp() * 1000)
    end = int(fim.timestamp() * 1000)
    while t < end:
        rows = get("https://data-api.binance.vision/api/v3/klines?symbol=%s&interval=5m&startTime=%d&limit=1000" % (sym, t))
        if not rows: break
        out += [(r[0] // 1000, float(r[1]), float(r[2]), float(r[3]), float(r[4])) for r in rows]
        t = rows[-1][0] + 300000
    return out

def yahoo_5m(tk):
    d = get("https://query1.finance.yahoo.com/v8/finance/chart/%s?range=60d&interval=5m" % urllib.request.quote(tk))["chart"]["result"][0]
    q = d["indicators"]["quote"][0]
    return [(t, o, h, l, c) for t, o, h, l, c in zip(d["timestamp"], q["open"], q["high"], q["low"], q["close"]) if None not in (o, h, l, c)]

def por_dia(bars):
    dias = {}
    for b in bars:
        x = dt.datetime.fromtimestamp(b[0], NY)
        dias.setdefault(x.date(), []).append((x, ) + b[1:])
    return dias

def dia(bs, cfg, custo):
    """Uma sessão: devolve o resultado em R e em % (já com custos) ou None se não houve entrada."""
    entrada_mod, stop_mod, rr, fim_h = cfg
    abre = [b for b in bs if (b[0].hour, b[0].minute) in ((9, 30), (9, 35), (9, 40))]
    if len(abre) < 3: return None
    hi, lo = max(b[2] for b in abre), min(b[3] for b in abre)
    resto = [b for b in bs if (b[0].hour, b[0].minute) >= (9, 45) and b[0].hour < fim_h]
    fvg = None; lado = 0
    for i in range(2, len(resto)):
        c1, c2, c3 = resto[i - 2], resto[i - 1], resto[i]
        if fvg is None:
            if c3[3] > c1[2] and c2[4] > hi and c3[3] > hi:          # FVG de alta acima da máxima
                fvg, lado, ifv = (c1[2], c3[3]), 1, i; continue
            if c3[2] < c1[3] and c2[4] < lo and c3[2] < lo:          # FVG de baixa abaixo da mínima
                fvg, lado, ifv = (c3[2], c1[3]), -1, i; continue
            continue
        # já existe FVG: espera voltar e a envolvente
        b, ant = resto[i], resto[i - 1]
        baixo, alto = fvg
        if lado == 1 and b[4] < baixo: return None                   # fechou abaixo do FVG: invalida
        if lado == -1 and b[4] > alto: return None
        tocou = (b[3] <= alto) if lado == 1 else (b[2] >= baixo)
        if not tocou and not ((ant[3] <= alto) if lado == 1 else (ant[2] >= baixo)): continue
        envolve = (b[4] > b[1] and ant[4] < ant[1] and b[4] >= ant[1] and b[1] <= ant[4]) if lado == 1 else \
                  (b[4] < b[1] and ant[4] > ant[1] and b[4] <= ant[1] and b[1] >= ant[4])
        if not envolve: continue
        if entrada_mod == "fech": e, j0 = b[4], i + 1
        else:
            if i + 1 >= len(resto): return None
            e, j0 = resto[i + 1][1], i + 1
        sp = (baixo if stop_mod == "fvg" else min(b[3], ant[3])) if lado == 1 else (alto if stop_mod == "fvg" else max(b[2], ant[2]))
        risco = (e - sp) * lado
        if risco <= 0: return None
        tp = e + lado * rr * risco
        x = None
        for k in range(j0, len(resto)):
            h, l = resto[k][2], resto[k][3]
            if (l <= sp) if lado == 1 else (h >= sp): x = sp; break        # stop primeiro (conservador)
            if (h >= tp) if lado == 1 else (l <= tp): x = tp; break
        if x is None: x = resto[-1][4]                                     # sai no fim da janela
        pct = lado * (x / e - 1) - 2 * custo
        return {"lado": lado, "R": round(lado * (x - e) / risco - 2 * custo * e / risco, 3), "pct": pct, "dia": str(b[0].date())}
    return None

def testar(nome, bars, custo, so_uteis):
    D = por_dia(bars); res = {}
    for cfg in itertools.product(("fech", "prox"), ("fvg", "env"), (3, 2), (12, 16)):
        ts = []
        for d0 in sorted(D):
            if so_uteis and d0.weekday() >= 5: continue
            r = dia(D[d0], cfg, custo)
            if r: ts.append(r)
        eq = 1.0; anos = {}
        for t in ts:
            eq *= 1 + t["pct"]; anos.setdefault(t["dia"][:4], 1.0); anos[t["dia"][:4]] *= 1 + t["pct"]
        n = len(ts); g = sum(1 for t in ts if t["R"] > 0)
        res["entrada=%s stop=%s alvo=%d:1 ate=%dh" % cfg] = {
            "operacoes": n, "acerto_pct": round(100 * g / n, 1) if n else None,
            "R_medio": round(sum(t["R"] for t in ts) / n, 3) if n else None,
            "total_pct_risco_1x": round(100 * (eq - 1), 1), "por_ano_pct": {a: round(100 * (v - 1), 1) for a, v in sorted(anos.items())}}
    return {"dias": len(D), "inicio": str(min(D)), "fim": str(max(D)), "custo_por_lado_pct": 100 * custo, "configs": res}

if __name__ == "__main__":
    out = {"gerado": dt.datetime.utcnow().isoformat() + "Z", "obs": "total_pct_risco_1x = posição de 100% do capital por operação (sem alavancagem)"}
    for tk in ("SPY", "QQQ", "ES=F", "NQ=F"):
        try: out[tk] = testar(tk, yahoo_5m(tk), 0.0002, True)
        except Exception as e: out[tk] = {"erro": repr(e)}
    ini, fim = dt.datetime(2023, 1, 1, tzinfo=dt.timezone.utc), dt.datetime.now(dt.timezone.utc)
    for s in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
        try: out[s] = testar(s, binance_5m(s, ini, fim), 0.001, True)
        except Exception as e: out[s] = {"erro": repr(e)}
    json.dump(out, open("estudos/resultado_orb_fvg.json", "w"), ensure_ascii=False, indent=1)
    for k, v in out.items():
        if isinstance(v, dict) and "configs" in v:
            best = sorted(v["configs"].items(), key=lambda kv: -(kv[1]["R_medio"] or -9))
            print(k, v["inicio"], v["fim"], "positivas:", sum(1 for _, c in v["configs"].items() if (c["R_medio"] or 0) > 0), "de", len(v["configs"]))
