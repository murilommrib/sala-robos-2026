#!/usr/bin/env python3
"""Motor causal dos robôs gráficos com ordem limitada.

O MESMO código roda no teste histórico e no robô ao vivo: recebe UMA vela
fechada por vez e só usa o que já aconteceu.

Auditoria (28/10/2026): o teste antigo (grafico_maker.trades_limit) decidia a
ordem seguinte depois de saber se a anterior tinha sido executada. Isso é olhar
o futuro e inflava o resultado (ETH +198% virou +35% com as mesmas regras feitas
de forma causal). Este motor corrige isso.

Regras, vela a vela (velas de 1 hora):
  1. Posição aberta: stop primeiro (hipótese conservadora), depois alvo (só se o
     preço PASSAR do alvo e não na vela de entrada), depois saída por tempo.
  2. Sem posição: cada sinal deixa a sua ordem limitada valendo por `wait` velas
     (podem existir várias ao mesmo tempo, como numa corretora). A primeira que
     executar abre a posição e cancela as outras. Se na vela da execução o preço
     também tocar o stop, considera stopado.
  3. No fechamento da vela, sem posição e com sinal: nova ordem em
     fechamento - lado * off * ATR.
Custos: entrada maker; saída maker no alvo, taker + slippage no stop/tempo.
Nenhuma ordem real é enviada.
"""
import datetime as dt

MAKER, TAKER, SLIP = 0.0002, 0.0005, 0.0005


def novo_estado():
    return {"ordens": [], "pos": None, "eq": 1.0, "ult_t": None, "trades": [], "perdidos": [], "dias": {}}


def passo(st, bar, sig, atr_i, p, tf=3600, pode_abrir=True, motivo=None):
    """Processa UMA vela fechada (t, o, h, l, c). Altera `st`. Devolve lista de eventos."""
    t, o, h, l, c = bar
    ev = []
    saiu = False
    wait = p.get("wait", 3)
    pos = st["pos"]
    if pos:
        sd, e, sp, tp = pos["lado"], pos["e"], pos["sp"], pos["tp"]
        x = how = None
        if (l <= sp) if sd == 1 else (h >= sp):
            x, how = (min(sp, o) if sd == 1 else max(sp, o)), "stop"
        elif (h > tp) if sd == 1 else (l < tp):
            x, how = tp, "alvo"
        elif t >= pos["t_fim"]:
            x, how = c, "tempo"
        if x is not None:
            _fechar(st, t + tf, x, how)
            ev.append(("saida", how, x))
            saiu = True
    else:
        vivas = [q for q in st["ordens"] if t <= q["t_sinal"] + wait * tf]
        if len(vivas) < len(st["ordens"]):
            ev.append(("expirou", len(st["ordens"]) - len(vivas)))
        st["ordens"] = vivas
        for q in vivas:                      # a mais antiga tem prioridade
            sd, L = q["lado"], q["L"]
            if (l < L) if sd == 1 else (h > L):
                e = min(L, o) if sd == 1 else max(L, o)
                sp = e - sd * p["ks"] * q["atr"]
                tp = e + sd * p["kt"] * q["atr"]
                st["pos"] = {"lado": sd, "e": e, "sp": sp, "tp": tp, "t_in": t, "t_fim": t + (p["H"] - 1) * tf}
                st["ordens"] = []
                ev.append(("entrada", sd, e))
                if (l <= sp) if sd == 1 else (h >= sp):      # tocou o stop na própria vela da entrada
                    _fechar(st, t + tf, sp, "stop")
                    ev.append(("saida", "stop", sp))
                    saiu = True
                break
    if not saiu and st["pos"] is None and sig and atr_i:
        if pode_abrir:
            q = {"lado": sig, "L": c - sig * p["off"] * atr_i, "atr": atr_i, "t_sinal": t}
            st["ordens"].append(q)
            ev.append(("ordem", sig, q["L"]))
        else:
            st["perdidos"].append([t, sig, motivo or "?"])
            ev.append(("perdido", motivo))
    st["ult_t"] = t
    st["dias"][dia(t)] = round(marcado(st, c), 8)
    return ev


def _fechar(st, t_saida, x, how):
    pos = st["pos"]
    sd, e = pos["lado"], pos["e"]
    g = sd * (x / e - 1)
    custo = MAKER + (MAKER if how == "alvo" else TAKER + SLIP)
    st["eq"] *= 1 + g - custo
    st["trades"].append([pos["t_in"], t_saida, sd, round(e, 6), round(x, 6), how, round(g - custo, 6)])
    st["pos"] = None


def marcado(st, preco):
    """Patrimônio (multiplicador) marcado a mercado: realizado x posição aberta."""
    pos = st["pos"]
    if not pos:
        return st["eq"]
    return st["eq"] * (1 + pos["lado"] * (preco / pos["e"] - 1) - MAKER)


def dia(t):
    return dt.datetime.utcfromtimestamp(t).strftime("%Y-%m-%d")


def rodar(bars, S, A, p, inicio_t=None):
    """Teste histórico: passa vela a vela. Devolve o estado final."""
    st = novo_estado()
    for i, b in enumerate(bars):
        if inicio_t is not None and b[0] < inicio_t:
            continue
        passo(st, b, S[i], A[i], p)
    return st
