#!/usr/bin/env python3
"""Robô "Abertura NY" (experimento, simulação, dinheiro fictício): a estratégia do vídeo.
  1. Marca máxima e mínima da vela de 15 min das 9:30 de Nova York (9:30-9:45).
  2. Em velas de 5 min, espera o rompimento desse nível deixando um FVG do lado de fora.
  3. Espera o preço voltar ao FVG e uma vela envolvente a favor; entra no fechamento dela.
  4. Stop atrás do FVG, alvo 3x o risco (3:1); se nada acontecer, sai às 16h de NY. Uma por dia.
Regras fixadas ANTES de ver o resultado ao vivo (a versão mais fiel ao vídeo, não a melhor do teste).
Opera o futuro do Nasdaq (NQ=F) e do S&P 500 (ES=F), metade do capital em cada; cada operação
arrisca 1% da sua metade (posição limitada a 4x). Custo: 0,02% por lado. Começa em 05/11/2026.
Preços: Yahoo Finance (velas de 5 min; podem chegar com ~10 min de atraso). NENHUMA ORDEM REAL.
Gerado pelo Claude."""
import json, os, time, urllib.request, datetime as dt
from zoneinfo import ZoneInfo
HERE = os.path.dirname(os.path.abspath(__file__))
PASTA = os.path.join(HERE, "trader", "mundo")
NY = ZoneInfo("America/New_York")
INICIO = "2026-11-05"
MERC = {"NQ": "NQ=F", "ES": "ES=F"}
NOME = {"NQ": "Nasdaq (futuro)", "ES": "S&P 500 (futuro)"}
CUSTO, RISCO, ALAV_MAX, RR, FIM_H = 0.0002, 0.01, 4.0, 3, 16

def _arq(c): return os.path.join(PASTA, "vivo_5m_%s.json" % c)

def velas(c, agora, max_idade=240):
    """Velas de 5 min guardadas (acumula, porque o Yahoo só devolve alguns dias de cada vez)."""
    fp = _arq(c)
    try: rows = {int(k): v for k, v in json.load(open(fp)).items()}
    except Exception: rows = {}
    if not os.path.exists(fp) or time.time() - os.path.getmtime(fp) > max_idade:
        try:
            url = "https://query1.finance.yahoo.com/v8/finance/chart/%s?range=5d&interval=5m" % urllib.request.quote(MERC[c])
            d = json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=20))["chart"]["result"][0]
            q = d["indicators"]["quote"][0]
            for t, o, h, l, cl in zip(d["timestamp"], q["open"], q["high"], q["low"], q["close"]):
                if None not in (o, h, l, cl) and t + 300 <= agora:          # só velas fechadas
                    rows[int(t)] = [o, h, l, cl]
            corte = agora - 40 * 86400
            rows = {t: v for t, v in rows.items() if t >= corte}
            os.makedirs(PASTA, exist_ok=True)
            tmp = fp + ".tmp"; json.dump({str(t): v for t, v in sorted(rows.items())}, open(tmp, "w")); os.replace(tmp, fp)
        except Exception:
            pass
    return [(t, *rows[t]) for t in sorted(rows)]

def sessao(bs, fim_sessao):
    """bs: velas do dia [(dt_ny, o, h, l, c)]. Devolve None ou a operação {lado,e,sp,tp,t_in,t_out,x,como}."""
    abre = [b for b in bs if (b[0].hour, b[0].minute) in ((9, 30), (9, 35), (9, 40))]
    if len(abre) < 3: return None
    hi, lo = max(b[2] for b in abre), min(b[3] for b in abre)
    resto = [b for b in bs if (b[0].hour, b[0].minute) >= (9, 45) and b[0].hour < FIM_H]
    fvg = None; lado = 0
    for i in range(2, len(resto)):
        c1, c2, c3 = resto[i - 2], resto[i - 1], resto[i]
        if fvg is None:
            if c3[3] > c1[2] and c2[4] > hi and c3[3] > hi: fvg, lado = (c1[2], c3[3]), 1
            elif c3[2] < c1[3] and c2[4] < lo and c3[2] < lo: fvg, lado = (c3[2], c1[3]), -1
            continue
        b, ant = resto[i], resto[i - 1]; baixo, alto = fvg
        if (lado == 1 and b[4] < baixo) or (lado == -1 and b[4] > alto): return None
        tocou = ((b[3] <= alto) or (ant[3] <= alto)) if lado == 1 else ((b[2] >= baixo) or (ant[2] >= baixo))
        envolve = (b[4] > b[1] and ant[4] < ant[1] and b[4] >= ant[1] and b[1] <= ant[4]) if lado == 1 else \
                  (b[4] < b[1] and ant[4] > ant[1] and b[4] <= ant[1] and b[1] >= ant[4])
        if not (tocou and envolve): continue
        e = b[4]; sp = baixo if lado == 1 else alto
        if (e - sp) * lado <= 0: return None
        tp = e + lado * RR * (e - sp) * lado
        op = {"lado": lado, "e": e, "sp": sp, "tp": tp, "t_in": int(b[0].timestamp()) + 300, "t_out": None, "x": None, "como": None}
        for k in range(i + 1, len(resto)):
            h, l = resto[k][2], resto[k][3]
            if (l <= sp) if lado == 1 else (h >= sp): op.update(x=sp, como="stop", t_out=int(resto[k][0].timestamp()) + 300); break
            if (h >= tp) if lado == 1 else (l <= tp): op.update(x=tp, como="alvo", t_out=int(resto[k][0].timestamp()) + 300); break
        if op["x"] is None:
            ult = resto[-1]
            if fim_sessao: op.update(x=ult[4], como="16h", t_out=int(ult[0].timestamp()) + 300)
            else: op["ultimo"] = ult[4]                                        # ainda aberta
        return op
    return None

def rodar(st, agora):
    agora_ny = dt.datetime.fromtimestamp(agora, NY)
    ini = dt.date.fromisoformat(INICIO)
    eqs, trades, pos = {c: 1.0 for c in MERC}, [], {}
    dias_eq = {(ini - dt.timedelta(days=1)).isoformat(): 1.0}
    por_dia = {c: {} for c in MERC}
    for c in MERC:
        for t, o, h, l, cl in velas(c, agora):
            x = dt.datetime.fromtimestamp(t, NY)
            if x.date() >= ini: por_dia[c].setdefault(x.date(), []).append((x, o, h, l, cl))
    d = ini
    while d <= agora_ny.date():
        aberto_hoje = {}
        for c in MERC:
            bs = por_dia[c].get(d)
            if not bs: continue
            fim = d < agora_ny.date() or agora_ny.hour >= FIM_H
            op = sessao(bs, fim)
            if not op: continue
            dist = abs(op["e"] - op["sp"]) / op["e"]
            tam = min(ALAV_MAX, RISCO / dist) if dist else 0                   # fração da metade do capital
            if op["x"] is not None:
                net = tam * (op["lado"] * (op["x"] / op["e"] - 1) - 2 * CUSTO)
                eqs[c] *= 1 + net
                trades.append([op["t_in"], op["t_out"], op["lado"], round(op["e"], 2), round(op["x"], 2), op["como"], round(net, 6), c])
            else:
                aberto_hoje[c] = tam * (op["lado"] * (op["ultimo"] / op["e"] - 1) - CUSTO)
                pos[c] = {"lado": op["lado"], "e": op["e"], "sp": op["sp"], "tp": op["tp"], "tam": tam}
        dias_eq[d.isoformat()] = sum(eqs[c] * (1 + aberto_hoje.get(c, 0)) for c in MERC) / len(MERC)
        d += dt.timedelta(days=1)
    of = {"dias": dias_eq, "pos": pos, "ordens": {}, "trades": trades, "perdidos": []}
    st["robos"]["aberturany"] = {"oficial": of, "ideal": of}

def resumo(st):
    of = (st["robos"].get("aberturany") or {}).get("oficial") or {}
    return {"moeda": "futuros NQ e ES",
            "posicoes": [{"moeda": NOME[c], "lado": "comprado" if p["lado"] > 0 else "vendido", "entrada": round(p["e"], 2),
                          "stop": round(p["sp"], 2), "alvo": round(p["tp"], 2), "resultado_pct": None} for c, p in (of.get("pos") or {}).items()]}

if __name__ == "__main__":
    st = {"robos": {}}; rodar(st, time.time()); of = st["robos"]["aberturany"]["oficial"]
    print(list(of["dias"].items())[-3:], of["trades"][-3:], of["pos"])
