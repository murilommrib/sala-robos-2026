#!/usr/bin/env python3
"""Mesa ao vivo — roda a cada 5 minutos no Mac (agendamento do macOS).

A cada execução:
  1. Lê o mercado em tempo real (dados públicos): preço e variação 24h (Binance),
     melhor compra/venda, spread e contratos em aberto nos perpétuos da Kraken
     (onde as ordens seriam executadas), taxa de financiamento (Binance perpétuos),
     índice medo/ganância (alternative.me).
  2. Passa cada vela de 1 hora recém-fechada pelos robôs gráficos (motor.py, o
     mesmo código do teste). Cada robô roda em duas versões:
       - "oficial": só abre ordem se estava acordado na hora (até 20 min de atraso)
         e se o spread na Kraken estiver normal. É o que daria para fazer de verdade.
       - "ideal": abre sempre, como no teste histórico. A diferença entre as duas
         mostra quanto se perde na operação real (Mac dormindo, spread etc.).
  3. Quando fecha um dia UTC, roda a simulação diária (sala.py).
  4. Grava trader/vivo/estado_vivo.json, trader/vivo/vivo.log e atualiza dados.json.
NENHUMA ORDEM REAL É ENVIADA.
"""
import json, os, sys, time, datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sala as SALA
import motor as M
import grafico as G

VIVO = os.path.join(HERE, "trader", "vivo")
TOL_ATRASO = 20 * 60          # segundos depois do fechamento da vela para ainda valer como "ao vivo"
SPREAD_MAX = 0.0010           # 0,10%: acima disso não abre ordem nova
JANELA = 750                  # velas de 1h de histórico para os indicadores
KRAKEN = {"BTC": "PF_XBTUSD"}  # demais: PF_<MOEDA>USD


def agora_s():
    return int(time.time())


def iso(t):
    return dt.datetime.utcfromtimestamp(t).strftime("%Y-%m-%dT%H:%MZ")


def log(msg):
    os.makedirs(VIVO, exist_ok=True)
    linha = "%s %s" % (dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), msg)
    print(linha, flush=True)
    lp = os.path.join(VIVO, "vivo.log")
    if os.path.exists(lp) and os.path.getsize(lp) > 2_000_000:
        os.replace(lp, lp + ".1")          # guarda só o arquivo anterior
    with open(lp, "a") as fh:
        fh.write(linha + "\n")


def carregar():
    p = os.path.join(VIVO, "estado_vivo.json")
    if os.path.exists(p):
        with open(p) as fh:
            st = json.load(fh)
        if st.get("versao") == SALA.VERSAO:
            return st
        arq = os.path.join(VIVO, "estado_vivo_v%s_arquivo_%s.json" % (st.get("versao"), dt.date.today().isoformat()))
        os.rename(p, arq)
        log("estado ao vivo antigo arquivado em %s" % os.path.basename(arq))
    return {"versao": SALA.VERSAO, "robos": {}, "batidas": [], "fng": None, "lacunas": []}


def gravar(st):
    os.makedirs(VIVO, exist_ok=True)
    tmp = os.path.join(VIVO, "estado_vivo.json.tmp")
    with open(tmp, "w") as fh:
        json.dump(st, fh)
    os.replace(tmp, os.path.join(VIVO, "estado_vivo.json"))


# ------------------------------------------------------------------ mercado em tempo real

def mercado(st):
    out = {"t": iso(agora_s()), "moedas": {}, "fontes": {}}
    import urllib.parse
    syms = urllib.parse.quote(json.dumps([c + "USDT" for c in SALA.COINS], separators=(",", ":")))
    b24 = None
    for h in SALA.HOSTS:
        b24 = SALA.get_json("%s/api/v3/ticker/24hr?symbols=%s" % (h, syms))
        if isinstance(b24, list):
            break
    kt = SALA.get_json("https://futures.kraken.com/derivatives/api/v3/tickers")
    fu = SALA.get_json("https://fapi.binance.com/fapi/v1/premiumIndex")
    out["fontes"] = {"binance": isinstance(b24, list), "kraken": isinstance(kt, dict), "financiamento": isinstance(fu, list)}
    bmap = {x["symbol"]: x for x in b24} if isinstance(b24, list) else {}
    kmap = {x.get("symbol"): x for x in (kt or {}).get("tickers", [])} if isinstance(kt, dict) else {}
    fmap = {x["symbol"]: x for x in fu} if isinstance(fu, list) else {}
    for c in SALA.COINS:
        m = {}
        b = bmap.get(c + "USDT")
        if b:
            m["preco"] = float(b["lastPrice"])
            m["var24h_pct"] = round(float(b["priceChangePercent"]), 2)
            m["volume24h_usd_mi"] = round(float(b["quoteVolume"]) / 1e6, 1)
        k = kmap.get(KRAKEN.get(c, "PF_%sUSD" % c))
        if k and k.get("bid") and k.get("ask"):
            bid, ask = float(k["bid"]), float(k["ask"])
            m["kraken_spread_pct"] = round(100 * (ask - bid) / ((ask + bid) / 2), 4)
            if k.get("openInterest") and k.get("markPrice"):
                m["kraken_aberto_usd_mi"] = round(float(k["openInterest"]) * float(k["markPrice"]) / 1e6, 1)
            if k.get("vol24h") and k.get("markPrice"):
                m["kraken_volume24h_usd_mi"] = round(float(k["vol24h"]) * float(k["markPrice"]) / 1e6, 1)
        f = fmap.get(c + "USDT")
        if f:
            m["financiamento_8h_pct"] = round(100 * float(f["lastFundingRate"]), 4)
        out["moedas"][c] = m
    # medo/ganância muda 1x por dia: busca no máximo a cada hora
    fng = st.get("fng")
    if not fng or agora_s() - fng.get("buscado", 0) > 3600:
        d = SALA.get_json("https://api.alternative.me/fng/?limit=1")
        try:
            x = d["data"][0]
            fng = {"valor": int(x["value"]), "classe": x["value_classification"], "buscado": agora_s()}
            st["fng"] = fng
        except Exception:
            pass
    out["medo_ganancia"] = {k: v for k, v in (fng or {}).items() if k != "buscado"} or None
    return out


# ------------------------------------------------------------------ robôs gráficos

def robos_graficos(st, merc):
    agora = agora_s()
    congelado = int(dt.datetime.fromisoformat(SALA.CONGELADO.replace("Z", "+00:00")).timestamp())
    inicio = SALA.ms(SALA.INICIO) // 1000
    for r in [x for x in SALA.ROBOS if x["tipo"] == "grafico"]:
        rs = st["robos"].setdefault(r["id"], {"oficial": M.novo_estado(), "ideal": M.novo_estado()})
        ult = min(x["ult_t"] for x in rs.values()) if all(x["ult_t"] for x in rs.values()) else None
        desde = (ult + 3600) if ult else inicio
        if desde + 3600 > agora:
            continue                                    # nenhuma vela nova fechou
        rows = SALA.klines(r["coin"] + "USDT", "1h", (desde - JANELA * 3600) * 1000, agora * 1000)
        B = [b for b in rows if b[0] + 3600 <= agora]   # só velas FECHADAS
        if not B:
            log("%s: sem velas (rede?)" % r["nome"])
            continue
        for i in range(1, len(B)):
            if B[i][0] - B[i - 1][0] != 3600 and B[i][0] >= desde:
                st["lacunas"].append([r["coin"], B[i - 1][0], B[i][0]])
                log("%s: falta vela entre %s e %s na fonte" % (r["coin"], iso(B[i - 1][0]), iso(B[i][0])))
        S = G.signals(r["metodo"], B)
        A = G.atr(B)
        sp = (merc["moedas"].get(r["coin"]) or {}).get("kraken_spread_pct")
        for i, b in enumerate(B):
            fecha = b[0] + 3600
            for nome, inst in rs.items():
                if inst["ult_t"] is not None and b[0] <= inst["ult_t"]:
                    continue
                if b[0] < inicio:
                    continue
                pode, motivo = True, None
                if nome == "oficial" and fecha > congelado:
                    if agora - fecha > TOL_ATRASO:
                        pode, motivo = False, "Mac desligado ou dormindo"
                    elif sp is None:
                        pode, motivo = False, "sem cotação da Kraken"
                    elif sp / 100 > SPREAD_MAX:
                        pode, motivo = False, "spread alto (%.3f%%)" % sp
                ev = M.passo(inst, b, S[i], A[i], r["params"], pode_abrir=pode, motivo=motivo)
                if nome == "oficial" and agora - fecha <= TOL_ATRASO:
                    for e in ev:
                        log("%s %s vela %s: %s" % (r["nome"], r["coin"], iso(b[0]), _txt(e)))


def _txt(e):
    k = e[0]
    if k == "ordem":
        return "ordem limitada de %s a %.2f" % ("COMPRA" if e[1] > 0 else "VENDA", e[2])
    if k == "entrada":
        return "executou %s a %.2f" % ("compra" if e[1] > 0 else "venda", e[2])
    if k == "saida":
        return "saiu por %s a %.2f" % (e[1], e[2])
    if k == "expirou":
        return "ordem expirou sem executar"
    if k == "perdido":
        return "sinal NÃO aproveitado: %s" % e[1]
    return str(e)


def _precos_extra(moedas):
    """Preço atual das moedas que não estão no painel de mercado (Binance)."""
    import urllib.parse
    syms = urllib.parse.quote(json.dumps([c + "USDT" for c in moedas], separators=(",", ":")))
    for h in SALA.HOSTS:
        d = SALA.get_json("%s/api/v3/ticker/price?symbols=%s" % (h, syms))
        if isinstance(d, list):
            return {x["symbol"][:-4]: float(x["price"]) for x in d}
    return {}


def resumo_vivo(st, merc, est_sala):
    agora = agora_s()
    bat = [t for t in st["batidas"] if t > agora - 86400]
    out = {"atualizado": iso(agora), "mercado": merc, "congelado": SALA.CONGELADO,
           "execucoes_24h": len(bat), "funcionando_24h_pct": round(min(100.0, 100 * len(bat) / 288), 1),
           "robos": {}, "diarios_hoje": {}}
    for r in [x for x in SALA.ROBOS if x["tipo"] == "grafico"]:
        rs = st["robos"].get(r["id"])
        if not rs:
            continue
        of, idl = rs["oficial"], rs["ideal"]
        preco = (merc["moedas"].get(r["coin"]) or {}).get("preco")
        pos = of["pos"]
        out["robos"][r["id"]] = {
            "moeda": r["coin"],
            "oficial_pct": round(100 * (M.marcado(of, preco) - 1), 2) if preco else round(100 * (of["eq"] - 1), 2),
            "ideal_pct": round(100 * (M.marcado(idl, preco) - 1), 2) if preco else round(100 * (idl["eq"] - 1), 2),
            "posicao": ({"lado": "comprado" if pos["lado"] > 0 else "vendido", "entrada": round(pos["e"], 2),
                         "stop": round(pos["sp"], 2), "alvo": round(pos["tp"], 2), "desde": iso(pos["t_in"]),
                         "resultado_pct": round(100 * pos["lado"] * (preco / pos["e"] - 1), 2) if preco else None} if pos else None),
            "ordens": [{"lado": "compra" if q["lado"] > 0 else "venda", "preco": round(q["L"], 2),
                        "vale_ate": iso(q["t_sinal"] + 3600 * (1 + r["params"].get("wait", 3)))} for q in of["ordens"]],
            "ultimas": [{"entrada": iso(x[0]), "saida": iso(x[1]), "lado": x[2], "como": x[5], "pct": round(100 * x[6], 2)} for x in of["trades"][-8:]][::-1],
            "operacoes": len(of["trades"]),
            "perdidos": len(of["perdidos"]),
            "ultimo_perdido": (lambda p: {"quando": iso(p[0]), "motivo": p[2]} if p else None)(of["perdidos"][-1] if of["perdidos"] else None),
            "ultima_vela": iso(of["ult_t"]) if of["ult_t"] else None,
            # para a página recalcular o resultado de hoje com o preço do momento
            "calc": {"eq": of["eq"], "eq_ontem": (lambda ds: of["dias"][max(ds)] if ds else 1.0)([k for k in of["dias"] if k < dt.datetime.utcnow().date().isoformat()]),
                     "lado": pos["lado"] if pos else 0, "e": pos["e"] if pos else None, "maker": M.MAKER},
        }
    hoje_d = dt.datetime.utcnow().date().isoformat()
    for r in [x for x in SALA.ROBOS if x["tipo"] == "experimento"]:
        rs = st["robos"].get(r["id"])
        if not rs:
            continue
        of, idl = rs["oficial"], rs["ideal"]
        ds = of.get("dias") or {}
        if not ds:
            continue
        ult_d = max(ds); ant = [k for k in ds if k < hoje_d]
        precos = {c: (merc["moedas"].get(c) or {}).get("preco") for c in of.get("pos", {})}
        out["robos"][r["id"]] = {
            "moeda": "15 moedas",
            "oficial_pct": round(100 * (ds[ult_d] - 1), 2),
            "ideal_pct": round(100 * ((idl.get("dias") or {}).get(ult_d, 1) - 1), 2),
            "posicao": None,
            "posicoes": [{"moeda": c, "lado": "comprado" if p["lado"] > 0 else "vendido", "entrada": p.get("e"),
                          "resultado_pct": round(100 * p["lado"] * (precos[c] / p["e"] - 1), 2) if p.get("e") and precos.get(c) else None}
                         for c, p in of.get("pos", {}).items()],
            "ordens": [{"lado": "compra" if q["lado"] > 0 else "venda", "preco": q["L"], "moeda": c, "vale_ate": iso(q["t_sinal"] + 4 * 3600)} for c, q in of.get("ordens", {}).items()],
            "ultimas": [{"entrada": iso(x[0]), "saida": iso(x[1]), "lado": x[2], "como": x[5], "pct": round(100 * x[6], 2), "moeda": x[7]} for x in of.get("trades", [])[-8:]][::-1],
            "operacoes": len(of.get("trades", [])),
            "perdidos": len(of.get("perdidos", [])),
            "calc": {"eq": ds[ult_d] if ult_d >= hoje_d else ds[ult_d], "eq_ontem": ds[max(ant)] if ant else 1.0, "lado": 0, "e": None, "maker": 0},
        }
    try:
        import diversificado as DV
        for rid in DV.ROBOS:
            if rid in out["robos"]:
                out["robos"][rid].update(DV.resumo(st, rid))
    except Exception:
        pass
    try:
        import risco as RISCO, experimentos as EXR
        out["risco"] = RISCO.medir(st, merc, est_sala, EXR.velas(agora), SALA.ROBOS)
    except Exception as e:
        out["risco"] = {"erro": repr(e)}
    try:
        import mesa as MESA
        out["mesa"] = MESA.resumo(st)
    except Exception:
        out["mesa"] = []
    rep = (st["robos"].get("reporter") or {}).get("oficial")
    if rep and "reporter" in out["robos"]:
        out["robos"]["reporter"]["sinais"] = rep.get("sinais", [])[-8:][::-1]
        out["robos"]["reporter"]["moeda"] = "notícias"
    # robôs diários: resultado parcial de hoje com preço ao vivo
    ph = (est_sala.get("pesos_hoje") or {})
    fe = est_sala.get("fech_ultimo") or {}
    out["posicoes_hoje"] = {"dia": ph.get("dia"), "pesos": ph.get("pesos") or {}, "fech": fe,
                            "capital": {k: v["capital"] for k, v in est_sala["robos"].items()}}
    if ph.get("dia") == dt.datetime.utcnow().date().isoformat():
        for rid, w in (ph.get("pesos") or {}).items():
            ret = 0.0
            ok = True
            for c, x in w.items():
                p_now = (merc["moedas"].get(c) or {}).get("preco")
                if not p_now or c not in fe:
                    ok = False
                    break
                ret += x * (p_now / fe[c] - 1)
            if ok:
                cap = est_sala["robos"][rid]["capital"]
                out["diarios_hoje"][rid] = {"pct": round(100 * ret, 2), "eur": round(cap * ret, 2),
                                            "posicao": SALA.describe(w) if rid != "segurador" else "segurando as 10 criptos"}
    try:
        with open(os.path.join(VIVO, "vivo.log")) as fh:
            out["eventos"] = [l.rstrip("\n") for l in fh.readlines()[-25:]][::-1]
    except OSError:
        out["eventos"] = []
    return out


def rodar():
    with SALA.trava():
        st = carregar()
        st["batidas"] = [t for t in st["batidas"] if t > agora_s() - 10 * 86400] + [agora_s()]
        merc = mercado(st)
        if not any(merc["fontes"].values()):
            log("sem internet ou fontes fora do ar; nada feito")
            gravar(st)
            return
        robos_graficos(st, merc)
        try:
            import experimentos as EX
            congelado = int(dt.datetime.fromisoformat(SALA.CONGELADO.replace("Z", "+00:00")).timestamp())
            EX.rodar(st, agora_s(), congelado)
        except Exception as e:
            log("experimentos: erro %r (os outros robôs seguem normais)" % (e,))
        try:
            import noticias_robo as NR, experimentos as EX2
            precos = {c: (merc["moedas"].get(c) or {}).get("preco") for c in EX2.MOEDAS}
            if not all(precos.values()):
                for c, pr in _precos_extra(EX2.MOEDAS).items():
                    precos[c] = precos.get(c) or pr
            velas = EX2.velas(agora_s())
            antes = len(st["robos"].get("reporter", {}).get("oficial", {}).get("trades", []))
            NR.rodar(st, agora_s(), {c: v for c, v in precos.items() if v}, velas)
            rep = st["robos"]["reporter"]["oficial"]
            for x in rep["trades"][antes:]:
                log("Repórter %s: saiu por %s (%+.2f%%)" % (x[7], x[5], 100 * x[6]))
        except Exception as e:
            log("repórter: erro %r (os outros robôs seguem normais)" % (e,))
        try:
            import diversificado as DV
            DV.rodar(st, agora_s())
        except Exception as e:
            log("diversificado: erro %r (os outros robôs seguem normais)" % (e,))
        try:
            import mesa as MESA
            n0 = len((st.get("mesa") or {}).get("setups", []))
            MESA.rodar(st, agora_s())
            for x in st["mesa"]["setups"][n0:]:
                log("Mesa: configuração de %s em %s a %.4g (stop %.4g, alvo %.4g)" % ("COMPRA" if x["lado"] > 0 else "VENDA", x["moeda"], x["entrada"], x["stop"], x["alvo"]))
        except Exception as e:
            log("mesa: erro %r (os outros robôs seguem normais)" % (e,))
        gravar(st)
        est = SALA.load_state()
        SALA.processar_dias(est, st)
        SALA.save(est, resumo_vivo(st, merc, est))


if __name__ == "__main__":
    rodar()
