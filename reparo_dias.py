#!/usr/bin/env python3
"""Reparo único (09/11/2026): de 30/10 a 08/11 os preços de ETFs e futuros não atualizaram no GitHub
(o cache usava a data do arquivo, que no GitHub é sempre a do checkout). Este script refaz o histórico
diário de Diversificado, Tático e Abertura NY com os preços certos, a partir das curvas recalculadas
pelos próprios robôs. Só roda se existir o arquivo reparo_dias.pedido; depois ele mesmo o apaga.
Não mexe em nenhum outro robô. Simulação; nenhuma ordem real. Gerado pelo Claude."""
import os, json, datetime as dt
HERE = os.path.dirname(os.path.abspath(__file__))
PEDIDO = os.path.join(HERE, "reparo_dias.pedido")
def main():
    if not os.path.exists(PEDIDO): return
    import sala as S, diversificado as DV, abertura_ny as ANY
    vp = os.path.join(HERE, "trader", "vivo", "estado_vivo.json"); st = json.load(open(vp))
    agora = int(dt.datetime.utcnow().timestamp())
    for t in DV.TICK.values():                              # força baixar tudo de novo
        try: os.remove(DV._arq(t))
        except OSError: pass
    for c in ANY.MERC:
        p = ANY._arq(c)
        try:
            d = json.load(open(p)); d["_baixado"] = 0; json.dump(d, open(p, "w"))
        except Exception: pass
    DV.rodar(st, agora); ANY.rodar(st, agora)
    json.dump(st, open(vp, "w"))
    with S.trava():
        est = S.load_state()
        for rid in ("diversificado", "tatico", "aberturany"):
            dias = st["robos"][rid]["oficial"]["dias"]; s = est["robos"][rid]
            cap0 = next(r for r in S.ROBOS if r["id"] == rid); cap = S.cap0(cap0)
            novo = []
            for h in s["historico"]:
                d0 = h["dia"]; ant = [k for k in dias if k < d0]
                ret = (dias.get(d0, dias[max(ant)] if ant else 1.0) / (dias[max(ant)] if ant else 1.0)) - 1
                pnl = cap * ret; cap += pnl
                novo.append(dict(h, ret_pct=round(100 * ret, 3), pnl_eur=round(pnl, 2), capital=round(cap, 2)))
            antes = s["capital"]; s["historico"] = novo; s["capital"] = cap
            print("%s: capital %.2f -> %.2f" % (rid, antes, cap))
        est.setdefault("reparos", []).append({"quando": dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%MZ"),
            "o_que": "histórico de Diversificado, Tático e Abertura NY refeito: preços de ETFs/futuros pararam de atualizar de 30/10 a 08/11"})
        S.save(est)
    os.remove(PEDIDO)
if __name__ == "__main__":
    main()
