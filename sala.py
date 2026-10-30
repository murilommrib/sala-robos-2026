#!/usr/bin/env python3
"""Sala de operações — motor diário de simulação (dinheiro fictício).

Carteira de EUR 500 fictícios dividida igualmente entre os robôs operadores
(Gestor e Segurador são carteiras de comparação de EUR 500). Regras congeladas
em CONGELADO: a partir daí nada é recalculado; mudança de código fica registrada.
Quem chama este arquivo normalmente é ao_vivo.py (a cada 5 minutos); rodar
`python3 sala.py` direto faz o mesmo ciclo completo. Grava:
  trader/sala/estado.json  — estado completo (posições, histórico)
  trader/sala/dados.json   — resumo que a sala publicada mostra

NENHUMA ORDEM REAL É ENVIADA. Só preços públicos da Binance.
Custos simulados: 0,10% por lado (contrato perpétuo + slippage) e 0,03%/dia
de financiamento sobre posições (valor-padrão de 0,01% a cada 8h).
"""
import json, os, sys, time, io, zipfile, csv, urllib.request, datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import intraday as I   # funções de day trade já testadas
import grafico as G    # métodos de análise gráfica (candlestick, price action)
import motor as MOTOR   # motor causal dos robôs gráficos (o mesmo do teste)
import hashlib, fcntl, contextlib

INICIO = "2026-10-01"
CONGELADO = "2026-10-29T00:00:00Z"   # regras e código congelados: teste prospectivo oficial
CARTEIRA = 500.0
VERSAO = 8
CAPITAL_REF = 500.0     # Gestor e Segurador: carteiras de comparação
FEE = 0.0010
FUNDING_DAY = 0.0003
COINS = ["BTC", "ETH", "BNB", "XRP", "ADA", "LINK", "LTC", "DOGE", "SOL", "TRX"]
DIR = os.path.join(HERE, "trader", "sala")
UA = "Mozilla/5.0 (robo-trading sala)"

ROBOS = [
    {"id": "tendo", "nome": "Tendo", "estrategia": "Tendência só comprado", "tipo": "diario",
     "desc": "Compra as criptos que estão acima da média de 50 dias e fica fora das outras.",
     "params": {"n": 50, "short": False}, "teste": {"total_pct": 1774.6, "queda_pct": -54.0, "sharpe": 1.23, "periodo": "2020-2026"}},
    {"id": "vaivem", "nome": "Vaivém", "estrategia": "Tendência comprado e vendido", "tipo": "diario",
     "desc": "Comprado nas criptos acima da média de 50 dias, vendido nas que estão abaixo.",
     "params": {"n": 50, "short": True}, "teste": {"total_pct": -18.6, "queda_pct": -83.2, "sharpe": 0.27, "periodo": "2020-2026"}},
    {"id": "extremo", "nome": "Extremo", "estrategia": "Extremos comprado e vendido", "tipo": "diario",
     "desc": "Toda semana compra as 3 que mais subiram em 14 dias e vende as 3 que mais caíram.",
     "params": {"L": 14}, "teste": {"total_pct": 228.6, "queda_pct": -37.2, "sharpe": 0.74, "periodo": "2020-2026"}},
    {"id": "bitao", "nome": "Bitão", "estrategia": "BTC comprado e vendido", "tipo": "diario",
     "desc": "Só BTC: comprado acima da média de 50 dias, vendido abaixo.",
     "params": {"n": 50, "short": True, "coins": ["BTC"]}, "teste": {"total_pct": 105.1, "queda_pct": -67.8, "sharpe": 0.48, "periodo": "2020-2026"}},
    {"id": "candela", "nome": "Candela", "estrategia": "Três soldados / três corvos · ETH 1h · ordem limitada", "tipo": "grafico", "coin": "ETH", "exec": "motor",
     "desc": "Day trade no ETH em velas de 1 hora, decidindo a cada vela com dados ao vivo: depois de três velas seguidas na mesma direção (a favor da média de 50), deixa uma ordem limitada meio ATR atrás por até 3 horas; stop de 2 ATR, alvo de 1,5 ATR, no máximo 24 horas na posição. EXPERIMENTAL: depois da auditoria o teste ficou fraco (+47% em quase 6 anos, só 2 anos positivos).",
     "metodo": "tres", "params": {"tf": 60, "off": 0.5, "ks": 2.0, "kt": 1.5, "H": 24, "wait": 3},
     "teste": {"total_pct": 46.2, "queda_pct": -57.6, "sharpe": 0.37, "periodo": "2021-2026"}},
    {"id": "semanal", "nome": "Semanal", "estrategia": "Tendência só comprado · semanal", "tipo": "diario",
     "desc": "Igual ao Tendo, mas só revisa a carteira às segundas-feiras: compra as criptos acima da média de 50 dias e segura a semana toda.",
     "params": {"n": 50, "short": False, "weekly": True}, "teste": {"total_pct": 1656.7, "queda_pct": -48.6, "sharpe": 1.18, "periodo": "2020-2026"}},
    {"id": "calmo", "nome": "Calmo", "estrategia": "Cesta com volatilidade-alvo", "tipo": "diario",
     "desc": "Segura as 10 criptos em partes iguais, mas diminui a posição quando o mercado fica agitado (alvo de 40% de volatilidade ao ano). Em observação: empatou com a referência no teste de custo dobrado.",
     "params": {"target": 0.4}, "teste": {"total_pct": 1315.0, "queda_pct": -55.5, "sharpe": 1.09, "periodo": "2020-2026"}},
    {"id": "gestor", "nome": "Gestor", "estrategia": "Divide o dinheiro entre os 4 aprovados", "tipo": "gestor",
     "desc": "Não escolhe moedas: reparte o dinheiro em partes iguais entre os 4 robôs aprovados nos testes (Tendo, Semanal, Calmo e Extremo) e fica com o resultado médio deles.",
     "params": {}, "teste": {"total_pct": 1287.5, "queda_pct": -38.2, "sharpe": 1.36, "periodo": "2020-2026"}},
    {"id": "cacador", "nome": "Caçador", "estrategia": "Experimento: 15 criptos, velas de 1h, MACD", "tipo": "experimento",
     "desc": "EXPERIMENTO REPROVADO, fora da carteira (EUR 100 fictícios próprios). Varre 15 criptos a cada hora, escolhe as de tendência mais forte e opera até 3 ao mesmo tempo com o sinal do MACD; stop de 2 ATR, alvo de 3 ATR. No teste perdeu dinheiro: está aqui para ver se o ao vivo confirma.",
     "params": {}, "teste": {"total_pct": -64.8, "queda_pct": -88.8, "sharpe": -0.16, "periodo": "2021-2026"}},
    {"id": "squeeze", "nome": "Squeeze", "estrategia": "Experimento: 15 criptos, velas de 4h, squeeze de Bollinger", "tipo": "experimento",
     "desc": "EXPERIMENTO REPROVADO, fora da carteira (EUR 100 fictícios próprios). Procura moedas cujas bandas de Bollinger ficaram muito estreitas e entra no rompimento, até 3 ao mesmo tempo, em velas de 4 horas. Foi o único método com resultado mediano positivo, mas reprovou no teste encadeado.",
     "params": {}, "teste": {"total_pct": -36.2, "queda_pct": -59.5, "sharpe": -0.26, "periodo": "2021-2026"}},
    {"id": "radar", "nome": "Radar", "estrategia": "Experimento: caçador de tendência diário, 15 criptos", "tipo": "experimento",
     "desc": "EXPERIMENTO REPROVADO, fora da carteira (EUR 100 fictícios próprios). Todo dia compra as 3 criptos que mais subiram em 14 dias entre as que estão acima da média de 100 dias. No teste perdeu para o simples comprar e segurar.",
     "params": {}, "teste": {"total_pct": -21.9, "queda_pct": -89.9, "sharpe": 0.30, "periodo": "2021-2026"}},
    {"id": "reporter", "nome": "Repórter", "estrategia": "Experimento: opera notícias do mercado", "tipo": "experimento",
     "desc": "EXPERIMENTO, fora da carteira (EUR 100 fictícios próprios), começou em 29/10/2026. De hora em hora o Claude lê as notícias que podem mexer com as 15 criptos (juros dos EUA, ETFs, hacks, regulação) e, quando acha uma forte, manda um sinal de compra ou venda; o robô entra a mercado, com stop de 2 ATR, alvo de 3 ATR e no máximo 12 horas. Não tem teste histórico: só o ao vivo vai dizer se funciona.",
     "params": {}, "teste": {"total_pct": 0.0, "queda_pct": 0.0, "sharpe": 0.0, "periodo": "sem teste (novo)"}},
    {"id": "diversificado", "nome": "Diversificado", "estrategia": "Experimento: ações, títulos, ouro e bitcoin, fixo", "tipo": "experimento", "capital": 500.0,
     "desc": "EXPERIMENTO, fora da carteira (EUR 500 fictícios próprios), começou em 30/10/2026. Não opera cripto todo dia: mantém 50% em ações dos EUA, 25% em títulos do governo dos EUA, 15% em ouro e 10% em bitcoin, medido em euros, e só rebalanceia uma vez por ano. É a régua do investimento passivo diversificado.",
     "params": {}, "teste": {"total_pct": 354.5, "queda_pct": -15.0, "sharpe": 1.33, "periodo": "2017-2026"}},
    {"id": "tatico", "nome": "Tático", "estrategia": "Experimento: a mesma carteira com leitura de tendência", "tipo": "experimento", "capital": 500.0,
     "desc": "EXPERIMENTO, fora da carteira (EUR 500 fictícios próprios), começou em 30/10/2026. Mesma base do Diversificado, mas todo começo de mês lê cada ativo: se está abaixo da média dos últimos 10 meses, aquela parte vai para o caixa até voltar a subir. Não vende a descoberto, porque no teste isso piorou o resultado em todos os casos. No teste rendeu menos que o fixo, com quedas um pouco menores.",
     "params": {}, "teste": {"total_pct": 191.5, "queda_pct": -12.4, "sharpe": 1.26, "periodo": "2017-2026"}},
    {"id": "segurador", "nome": "Segurador", "estrategia": "Comprar e segurar (referência)", "tipo": "referencia",
     "desc": "Não opera: segura as 10 criptos em partes iguais desde o primeiro dia. É a régua para medir os outros.",
     "params": {}, "teste": {"total_pct": 5150.6, "queda_pct": -76.7, "sharpe": 1.17, "periodo": "2020-2026"}},
]


# ------------------------------------------------------------------ dados

def get_json(url):
    for i in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())
        except Exception:
            time.sleep(2 * (i + 1))
    return None


HOSTS = ["https://data-api.binance.vision", "https://api.binance.com"]


def klines(symbol, interval, start_ms, end_ms):
    out = []
    for h in HOSTS:
        cur, rows = start_ms, []
        ok = True
        while cur < end_ms:
            d = get_json("%s/api/v3/klines?symbol=%s&interval=%s&startTime=%d&endTime=%d&limit=1000"
                         % (h, symbol, interval, cur, end_ms - 1))
            if d is None:
                ok = False
                break
            if not d:
                break
            rows += d
            cur = int(d[-1][0]) + 1
            if len(d) < 1000:
                break
        if ok:
            out = rows
            break
    return [(int(r[0]) // 1000, float(r[1]), float(r[2]), float(r[3]), float(r[4])) for r in out]


def ms(day):
    return int(dt.datetime.fromisoformat(day).replace(tzinfo=dt.timezone.utc).timestamp() * 1000)


def daily_closes(first_needed, last_day):
    """{coin: {dia: (o,h,l,c)}} de first_needed até last_day."""
    out = {}
    end = ms(last_day) + 86400000
    for c in COINS:
        rows = klines(c + "USDT", "1d", ms(first_needed), end)
        out[c] = {dt.datetime.utcfromtimestamp(t).strftime("%Y-%m-%d"): (o, h, l, cl) for t, o, h, l, cl in rows}
    return out


def five_min(coin, day):
    rows = klines(coin + "USDT", "5m", ms(day), ms(day) + 86400000)
    bars = {}
    for t, o, h, l, c in rows:
        d = dt.datetime.utcfromtimestamp(t)
        if d.strftime("%Y-%m-%d") == day:
            bars[(d.hour * 60 + d.minute) // 5] = (o, h, l, c)
    return [bars[i] for i in range(288)] if len(bars) == 288 else None


# ------------------------------------------------------------------ regras dos robôs (decididas com dados até a véspera)

def days_back(day, n):
    d = dt.date.fromisoformat(day)
    return [(d - dt.timedelta(days=k)).isoformat() for k in range(n, 0, -1)]


def weights(robo, day, D):
    """Pesos para o dia `day`, usando fechamentos até a véspera."""
    p = robo["params"]
    prev = days_back(day, 1)[0]
    if robo["id"] == "segurador":
        return {c: 1 / len(COINS) for c in COINS}
    if robo["id"] == "extremo":
        # rebalanceia às segundas-feiras; nos outros dias mantém o peso da última segunda
        d = dt.date.fromisoformat(day)
        monday = (d - dt.timedelta(days=d.weekday())).isoformat()
        ref = days_back(monday, 1)[0]
        base = days_back(monday, p["L"] + 1)[0]
        mom = []
        for c in COINS:
            if ref in D[c] and base in D[c]:
                mom.append((D[c][ref][3] / D[c][base][3] - 1, c))
        mom.sort()
        if len(mom) < 6:
            return {}
        w = {c: -1 / 6 for _, c in mom[:3]}
        w.update({c: 1 / 6 for _, c in mom[-3:]})
        return w
    if "target" in p:
        prev = days_back(day, 1)[0]
        vols = []
        for c in COINS:
            hist30 = days_back(prev, 30) + [prev]
            if not all(h in D[c] for h in hist30):
                continue
            r = [D[c][hist30[k]][3] / D[c][hist30[k - 1]][3] - 1 for k in range(1, len(hist30))]
            m = sum(r) / len(r)
            vols.append((c, (sum((x - m) ** 2 for x in r) / len(r)) ** 0.5 * 365 ** 0.5))
        if not vols:
            return {}
        est = sum(v for _, v in vols) / len(vols)
        k = min(1.0, p["target"] / est)
        return {c: k / len(vols) for c, _ in vols}
    if p.get("weekly"):
        d = dt.date.fromisoformat(day)
        day = (d - dt.timedelta(days=d.weekday())).isoformat()   # decide com o fechamento de domingo e segura a semana
        prev = days_back(day, 1)[0]
    coins = p.get("coins", COINS)
    hist = days_back(day, p["n"])
    live = [c for c in coins if all(h in D[c] for h in hist)]
    w = {}
    for c in live:
        avg = sum(D[c][h][3] for h in hist) / p["n"]
        s = 1 if D[c][prev][3] > avg else -1
        if s < 0 and not p["short"]:
            s = 0
        if s:
            w[c] = s / len(live)
    return w


def describe(w):
    if not w:
        return "fora do mercado"
    longs = sorted(c for c, x in w.items() if x > 0)
    shorts = sorted(c for c, x in w.items() if x < 0)
    parts = []
    if longs:
        parts.append("comprado em " + ", ".join(longs))
    if shorts:
        parts.append("vendido em " + ", ".join(shorts))
    return "; ".join(parts)


# ------------------------------------------------------------------ estado

OPERADORES = [r["id"] for r in ROBOS if r["tipo"] not in ("gestor", "referencia", "experimento")]
CAPITAL_EXP = 100.0                         # experimentos: fora da carteira
CAPITAL = CARTEIRA / len(OPERADORES)        # parte de cada robô operador
SEMANAIS = ("semanal", "extremo")           # só mexem na carteira às segundas
CODIGO = ("sala.py", "motor.py", "grafico.py", "ao_vivo.py")


def cap0(r):
    if r["tipo"] == "experimento":
        return r.get("capital", CAPITAL_EXP)
    return CAPITAL_REF if r["tipo"] in ("gestor", "referencia") else CAPITAL


def hash_codigo():
    h = {}
    for f in CODIGO:
        fp = os.path.join(HERE, f)
        if os.path.exists(fp):
            with open(fp, "rb") as fh:
                h[f] = hashlib.sha256(fh.read()).hexdigest()[:12]
    return h


@contextlib.contextmanager
def trava():
    """Impede duas execuções ao mesmo tempo (agendamento + clique manual)."""
    os.makedirs(DIR, exist_ok=True)
    fh = open(os.path.join(DIR, ".trava"), "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        raise SystemExit("Outra execução em andamento; saindo.")
    try:
        yield
    finally:
        fcntl.flock(fh, fcntl.LOCK_UN)
        fh.close()


def novo_estado():
    return {"versao": VERSAO, "inicio": INICIO, "congelado": CONGELADO, "ultimo_dia": None, "precos": {"BTC": {}, "ETH": {}},
            "codigo": hash_codigo(), "mudancas": [], "fech_ultimo": {}, "pesos_hoje": {},
            "robos": {r["id"]: {"capital": cap0(r), "pesos": {}, "historico": []} for r in ROBOS}}


def load_state():
    path = os.path.join(DIR, "estado.json")
    if os.path.exists(path):
        with open(path) as fh:
            st = json.load(fh)
        if st.get("versao") == VERSAO:
            agora = hash_codigo()
            if agora != st.get("codigo") and dt.datetime.utcnow().isoformat() + "Z" >= CONGELADO:
                diff = sorted(k for k in set(agora) | set(st.get("codigo", {})) if agora.get(k) != st.get("codigo", {}).get(k))
                st.setdefault("mudancas", []).append({"quando": dt.datetime.utcnow().isoformat(timespec="minutes") + "Z", "arquivos": diff})
            st["codigo"] = agora
            for r in ROBOS:                       # robô novo entra a partir de hoje, sem recalcular os outros
                if r["id"] not in st["robos"]:
                    st["robos"][r["id"]] = {"capital": cap0(r), "pesos": {}, "historico": []}
                    st.setdefault("mudancas", []).append({"quando": dt.datetime.utcnow().isoformat(timespec="minutes") + "Z", "arquivos": ["novo robô: " + r["nome"]]})
            return st
        # versão antiga: guarda o arquivo (nunca apaga histórico) e recomeça
        arq = os.path.join(DIR, "estado_v%s_arquivo_%s.json" % (st.get("versao"), dt.date.today().isoformat()))
        os.rename(path, arq)
        print("Estado da versão %s arquivado em %s; recalculando desde %s." % (st.get("versao"), os.path.basename(arq), INICIO))
    return novo_estado()


def resumo(state, vivo=None):
    """Grava trader/sala/dados.json (o que a sala publicada mostra)."""
    dias = sorted({h["dia"] for s in state["robos"].values() for h in s["historico"]})
    faixas = {}
    fp = os.path.join(DIR, "faixas.json")
    if os.path.exists(fp):
        with open(fp) as fh:
            faixas = json.load(fh)
    robos = []
    for r in ROBOS:
        s = state["robos"][r["id"]]
        h = s["historico"]
        last = h[-1] if h else None
        hc = [x for x in h if x["dia"] >= CONGELADO[:10]]
        base = None
        if hc:
            i0 = h.index(hc[0])
            base = h[i0 - 1]["capital"] if i0 > 0 else cap0(r)
        robos.append({k: r[k] for k in ("id", "nome", "estrategia", "tipo", "desc", "teste")} | {
            "capital": round(s["capital"], 2),
            "capital_inicial": round(cap0(r), 2),
            "resultado_pct": round(100 * (s["capital"] / cap0(r) - 1), 2),
            "desde_congelado_pct": round(100 * (s["capital"] / base - 1), 2) if base else None,
            "hoje_pct": last["ret_pct"] if last else None,
            "hoje_eur": last["pnl_eur"] if last else None,
            "posicao": last["posicao"] if last else "aguardando o primeiro dia",
            "historico": [{k: x[k] for k in x if k not in ("pnl_eur", "posicao")} for x in h],
            "faixa": (faixas.get(r["id"]) or {}).get("faixas"),
        })
    dados = {"atualizado_utc": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z", "inicio": state["inicio"],
             "congelado": CONGELADO, "mudancas_codigo": state.get("mudancas", []),
             "ultimo_dia": state["ultimo_dia"], "capital_inicial": CAPITAL, "carteira_inicial": CARTEIRA,
             "n_operadores": len(OPERADORES), "dias": dias, "robos": robos,
             "custos": {"por_lado_pct": 100 * FEE, "financiamento": "taxa real da Binance (perpétuos) por dia; 0,03%/dia se faltar"},
             "precos": {c: [[d, v] for d, v in sorted(state["precos"][c].items())] for c in state["precos"]},
             "vivo": vivo,
             "aviso": "Simulação com dinheiro fictício. Nenhuma ordem real é enviada."}
    tmp = os.path.join(DIR, "dados.json.tmp")
    with open(tmp, "w") as fh:
        json.dump(dados, fh, ensure_ascii=False)
    os.replace(tmp, os.path.join(DIR, "dados.json"))


def save(state, vivo=None):
    os.makedirs(DIR, exist_ok=True)
    tmp = os.path.join(DIR, "estado.json.tmp")
    with open(tmp, "w") as fh:
        json.dump(state, fh, ensure_ascii=False)
    os.replace(tmp, os.path.join(DIR, "estado.json"))      # gravação atômica: não corrompe se o Mac dormir no meio
    resumo(state, vivo)


FUT = "https://fapi.binance.com"


def funding_por_dia(first, last):
    """{moeda: {dia: soma das taxas de financiamento do dia}} (perpétuos da Binance). Vazio se falhar."""
    out = {}
    for c in COINS:
        d = get_json("%s/fapi/v1/fundingRate?symbol=%sUSDT&startTime=%d&endTime=%d&limit=1000"
                     % (FUT, c, ms(first), ms(last) + 86400000 - 1))
        if not isinstance(d, list):
            continue
        m = {}
        for x in d:
            day = dt.datetime.utcfromtimestamp(int(x["fundingTime"]) // 1000).strftime("%Y-%m-%d")
            m[day] = m.get(day, 0.0) + float(x["fundingRate"])
        out[c] = m
    return out


def deriva(w, r):
    """Pesos depois de um dia de variação r (as posições crescem/encolhem com o preço)."""
    R = sum(x * r.get(c, 0.0) for c, x in w.items())
    return {c: x * (1 + r.get(c, 0.0)) / (1 + R) for c, x in w.items()} if 1 + R > 0 else dict(w)


def processar_dias(state, vivo_estado=None):
    """Processa os dias UTC fechados que faltam. Devolve True se processou algo."""
    today = dt.datetime.utcnow().date()
    last_closed = (today - dt.timedelta(days=1)).isoformat()
    first = state["inicio"] if not state["ultimo_dia"] else \
        (dt.date.fromisoformat(state["ultimo_dia"]) + dt.timedelta(days=1)).isoformat()
    if first > last_closed:
        return False
    print("Processando %s a %s" % (first, last_closed), flush=True)
    D = daily_closes(days_back(first, 80)[0], last_closed)
    missing = [c for c in COINS if not D[c] or last_closed not in D[c]]
    if missing:
        print("Sem preços para %s (rede?). Tento de novo na próxima execução." % ", ".join(missing))
        return False
    FUND = funding_por_dia(first, last_closed)
    d = dt.date.fromisoformat(first)
    while d.isoformat() <= last_closed:
        day = d.isoformat()
        prev = days_back(day, 1)[0]
        faltando = [r["nome"] for r in ROBOS if r["tipo"] == "grafico" and day not in
                    ((((vivo_estado or {}).get("robos") or {}).get(r["id"]) or {}).get("oficial") or {}).get("dias", {})]
        if faltando:
            print("  %s: o motor ao vivo ainda não fechou %s (%s); espero a próxima execução." % (day, day, ", ".join(faltando)))
            break
        for c in state["precos"]:
            if day in D[c]:
                state["precos"][c][day] = D[c][day][3]
        r_dia = {c: D[c][day][3] / D[c][prev][3] - 1 for c in COINS if day in D[c] and prev in D[c]}
        rets = {}
        for r in ROBOS:
            extra = {}
            s = state["robos"][r["id"]]
            if r["tipo"] == "gestor":
                ops = [k for k in ("tendo", "semanal", "calmo", "extremo") if k in rets]
                ret = sum(rets[k] for k in ops) / len(ops) if ops else 0.0
                pos = "repartido entre Tendo, Semanal, Calmo e Extremo"
            elif r["tipo"] in ("diario", "referencia"):
                atual = s["pesos"]                      # pesos já com a variação de ontem
                segunda = d.weekday() == 0
                if r["tipo"] == "referencia" and atual:
                    w = atual                           # comprar e segurar de verdade: não rebalanceia
                elif r["id"] in SEMANAIS and atual and not segunda:
                    w = atual                           # segura a semana toda
                else:
                    w = weights(r, day, D)
                turn = sum(abs(w.get(c, 0) - atual.get(c, 0)) for c in set(w) | set(atual))
                ret = sum(x * r_dia.get(c, 0.0) for c, x in w.items())
                fund_real = 0
                if r["tipo"] != "referencia":
                    for c, x in w.items():
                        if c in FUND and FUND[c]:
                            ret -= x * FUND[c].get(day, 0.0); fund_real += 1
                        else:
                            ret -= x * FUNDING_DAY      # comprado paga, vendido recebe
                cost = (FEE if r["tipo"] != "referencia" else 0.0045) * turn
                ret -= cost
                s["pesos"] = deriva(w, r_dia)
                pos = describe(w) if r["tipo"] != "referencia" else "segurando as 10 criptos"
                extra = {"comprado_pct": round(100 * sum(x for x in w.values() if x > 0), 1),
                         "vendido_pct": round(100 * sum(-x for x in w.values() if x < 0), 1),
                         "trocas_pct": round(100 * turn, 1)}
            elif r["tipo"] in ("grafico", "experimento"):
                vs = ((vivo_estado or {}).get("robos") or {}).get(r["id"]) or {}
                of = vs.get("oficial") or {}
                dias_eq = of.get("dias") or {}
                if day not in dias_eq:                 # experimento sem dados: não trava os outros
                    prev_k = [k for k in dias_eq if k < day]
                    dias_eq = dict(dias_eq); dias_eq[day] = dias_eq[max(prev_k)] if prev_k else 1.0
                antes = [k for k in dias_eq if k < day]
                eq0 = dias_eq[max(antes)] if antes else 1.0
                ret = dias_eq[day] / eq0 - 1
                t0, t1 = ms(day) // 1000, ms(day) // 1000 + 86400
                fechadas = [x for x in of.get("trades", []) if t0 < x[1] <= t1]
                perd = [x for x in of.get("perdidos", []) if t0 <= x[0] < t1]
                n_ok = sum(1 for x in fechadas if x[6] > 0)
                pos = ("%d operações fechadas no dia (%d ganharam, %d perderam)" % (len(fechadas), n_ok, len(fechadas) - n_ok)) if fechadas else "nenhuma operação fechada no dia"
                if perd:
                    pos += "; %d sinais perdidos (%s)" % (len(perd), perd[-1][2])
                extra = {"moeda": r.get("coin") or "15 moedas", "ops": len(fechadas), "ops_ganhas": n_ok,
                         "ops_lista": [[x[2], round(100 * x[6], 3)] for x in fechadas][:30], "perdidos": len(perd)}
            else:
                continue
            rets[r["id"]] = ret
            pnl = s["capital"] * ret
            s["capital"] += pnl
            s["historico"].append({"dia": day, "ret_pct": round(100 * ret, 3), "pnl_eur": round(pnl, 2),
                                   "capital": round(s["capital"], 2), "posicao": pos, **extra})
        state["ultimo_dia"] = day
        print("  %s ok" % day, flush=True)
        d += dt.timedelta(days=1)
    # para o acompanhamento ao vivo do dia corrente
    state["fech_ultimo"] = {c: D[c][last_closed][3] for c in COINS if last_closed in D[c]}
    hoje = today.isoformat()
    ph = {}
    for r in ROBOS:
        if r["tipo"] in ("diario", "referencia"):
            s = state["robos"][r["id"]]
            if r["tipo"] == "referencia" or (r["id"] in SEMANAIS and today.weekday() != 0):
                ph[r["id"]] = s["pesos"]
            else:
                ph[r["id"]] = weights(r, hoje, D)
    state["pesos_hoje"] = {"dia": hoje, "pesos": ph}
    tot = sum(state["robos"][k]["capital"] for k in OPERADORES)
    print("Atualizado até %s. Carteira dos %d robôs: EUR %.2f. Nenhuma ordem real enviada." % (state["ultimo_dia"], len(OPERADORES), tot))
    return True


def main():
    import ao_vivo
    ao_vivo.rodar()


if __name__ == "__main__":
    main()
