#!/usr/bin/env python3
"""Robôs EXPERIMENTAIS (reprovados no teste histórico), operando ao vivo só na simulação.

Ficam fora da carteira de EUR 500: cada um tem EUR 100 fictícios próprios. Servem para ver,
com dados novos, se o resultado ruim do teste se repete. Usam o mesmo código do teste
(cacador.py e tendencia15.py), rodado de novo a cada vela fechada com as velas guardadas.

  Caçador  — 15 criptos, velas de 1h, MACD com filtro de média de 200, até 3 posições.
  Squeeze  — 15 criptos, velas de 4h, squeeze de Bollinger, até 3 posições.
  Radar    — 15 criptos, fechamento diário: as 3 com maior alta em 14 dias entre as que
             estão acima da média de 100 dias.
"oficial": sinal que aparece com o Mac dormindo (vela vista mais de 20 min depois de fechar,
depois do congelamento) não vira ordem. "ideal": como no teste. Nenhuma ordem real é enviada.
"""
import json, os, sys, time, datetime as dt
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import sala as SALA
import cacador as C
import tendencia15 as TD

MOEDAS = ["BTC", "ETH", "BNB", "XRP", "ADA", "LINK", "LTC", "DOGE", "SOL", "TRX", "AVAX", "DOT", "BCH", "ATOM", "UNI"]
CACHE = os.path.join(HERE, "trader", "vivo", "velas_1h_15.json")
AQUEC = 130 * 86400            # histórico antes do início para médias e volume
CFG = {
    "cacador": {"tf": 1, "cfg": dict(m="macd", ex="lim25", ks=2.0, kt=3.0, H=24)},
    "squeeze": {"tf": 4, "cfg": dict(m="squeeze", ex="mercado", ks=1.0, kt=3.0, H=18)},
    "radar": {"tf": 24, "cfg": dict(modo="topK", n=100, L=14, K=3, sem=False)},
}
TOL = 20 * 60


def _fetch(sym, start_ms, end_ms):
    out = []
    for h in SALA.HOSTS:
        cur, rows, ok = start_ms, [], True
        while cur < end_ms:
            d = SALA.get_json("%s/api/v3/klines?symbol=%s&interval=1h&startTime=%d&endTime=%d&limit=1000" % (h, sym, cur, end_ms - 1))
            if d is None:
                ok = False; break
            if not d: break
            rows += d; cur = int(d[-1][0]) + 1
            if len(d) < 1000: break
        if ok:
            out = rows; break
    return [[int(r[0]) // 1000, float(r[1]), float(r[2]), float(r[3]), float(r[4]), round(float(r[7]))] for r in out]


def velas(agora):
    """Atualiza o arquivo de velas de 1h das 15 moedas e devolve só as FECHADAS."""
    ini = SALA.ms(SALA.INICIO) // 1000 - AQUEC
    try:
        cache = json.load(open(CACHE))
    except Exception:
        cache = {}
    mudou = False
    for c in MOEDAS:
        rows = cache.get(c) or []
        desde = rows[-1][0] + 3600 if rows else ini
        if desde + 3600 <= agora:
            novas = _fetch(c + "USDT", desde * 1000, agora * 1000)
            if novas:
                rows = [r for r in rows if r[0] < novas[0][0]] + novas
                cache[c] = rows; mudou = True
    if mudou:
        tmp = CACHE + ".tmp"
        json.dump(cache, open(tmp, "w")); os.replace(tmp, CACHE)
    return {c: [tuple(r) for r in rows if r[0] + 3600 <= agora] for c, rows in cache.items()}


def rodar(st_vivo, agora, congelado):
    """Atualiza os experimentos em st_vivo["robos"][id] = {"oficial": ..., "ideal": ...}."""
    V = velas(agora)
    if not V or min(len(v) for v in V.values()) < 500:
        return
    ult = max(r[0] for v in V.values() for r in v)
    if st_vivo.get("exp_ult") == ult and all(k in st_vivo["robos"] for k in CFG):
        return                                      # nenhuma vela nova
    visto = st_vivo.setdefault("exp_visto", {})    # quando cada vela foi vista pela 1a vez
    for tf in (1, 4):
        fim = (ult + 3600) - (ult + 3600) % (3600 * tf)
        for t in range(fim - 3600 * tf * 6, fim, 3600 * tf):
            visto.setdefault("%d:%d" % (tf, t), agora)
    corte = agora - 15 * 86400
    for k in [k for k, v in visto.items() if int(k.split(":")[1]) < corte]:
        del visto[k]
    inicio = SALA.ms(SALA.INICIO) // 1000
    t_ini = inicio - AQUEC
    t_ini -= t_ini % 86400
    for rid, spec in CFG.items():
        tf = spec["tf"]
        res = {}
        for nome in ("ideal", "oficial"):
            def pode(k, tf=tf, nome=nome):
                t_fecha = C.T0 + (k + 1) * C.STEP
                if t_fecha <= inicio:
                    return False, "antes do início"
                if nome == "ideal" or t_fecha <= congelado:
                    return True, None
                v = visto.get("%d:%d" % (tf, t_fecha - C.STEP))
                if v is None or v - t_fecha > TOL:
                    return False, "Mac desligado ou dormindo"
                return True, None
            if tf in (1, 4):
                fim = (ult + 3600) - (ult + 3600) % (3600 * tf)
                C.configurar(tf, t_ini, fim)
                C.carregar_linhas(V)
                est = {}
                dias, trades = C.simular(spec["cfg"], pode=pode, estado=est)
                r = {"trades": [[a, b, sd, round(e, 6), round(x, 6), how, round(g, 6), c] for (a, b, c, sd, e, x, how, g) in trades],
                     "perdidos": [[p[0], p[2], p[3], p[1]] for p in est.get("perdidos", []) if p[0] >= congelado],
                     "pos": est.get("pos", {}), "ordens": est.get("ordens", {})}
            else:
                D = {}
                for c, rows in V.items():
                    D[c] = {dt.datetime.utcfromtimestamp(x[0]).strftime("%Y-%m-%d"): x[4] for x in rows if (x[0] + 3600) % 86400 == 0}
                dias_ok = sorted(set.intersection(*[set(m) for m in D.values()]))
                dias = TD.simular(D, dias_ok, spec["cfg"])
                r = {"trades": [], "perdidos": [], "pos": {c: {"lado": 1} for c in _radar_carteira(D, dias_ok, spec["cfg"])}, "ordens": {}}
            antes = [d for d in dias if d < SALA.INICIO]
            base = dias[max(antes)] if antes else 1.0
            r["dias"] = {d: round(v / base, 8) for d, v in dias.items() if d >= SALA.INICIO}
            r["ult_t"] = ult
            res[nome] = r
        st_vivo["robos"][rid] = res
    st_vivo["exp_ult"] = ult


def _radar_carteira(D, dias, cfg):
    coins = sorted(D); i = len(dias) - 1; n, L, K = cfg["n"], cfg["L"], cfg["K"]
    Cc = {c: [D[c][d] for d in dias] for c in coins}
    acima = [c for c in coins if Cc[c][i] > sum(Cc[c][i - n + 1:i + 1]) / n]
    mom = sorted(((Cc[c][i] / Cc[c][i - L] - 1, c) for c in coins), reverse=True)
    return [c for _, c in mom if c in acima][:K]
