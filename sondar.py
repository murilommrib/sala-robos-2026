#!/usr/bin/env python3
"""Testa quais fontes de dados de mercado em tempo real este Mac alcança. Só leitura de dados públicos."""
import json, os, subprocess, time, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__))
URLS = {
    "binance_vision_book": "https://data-api.binance.vision/api/v3/ticker/bookTicker?symbol=BTCUSDT",
    "binance_vision_24h": "https://data-api.binance.vision/api/v3/ticker/24hr?symbol=BTCUSDT",
    "binance_vision_depth": "https://data-api.binance.vision/api/v3/depth?symbol=BTCUSDT&limit=20",
    "binance_vision_klines": "https://data-api.binance.vision/api/v3/klines?symbol=BTCUSDT&interval=1h&limit=3",
    "binance_api_book": "https://api.binance.com/api/v3/ticker/bookTicker?symbol=BTCUSDT",
    "binance_fut_funding": "https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT",
    "binance_fut_oi": "https://fapi.binance.com/fapi/v1/openInterest?symbol=BTCUSDT",
    "kraken_fut_tickers": "https://futures.kraken.com/derivatives/api/v3/tickers",
    "kraken_fut_instruments": "https://futures.kraken.com/derivatives/api/v3/instruments",
    "kraken_spot_ticker": "https://api.kraken.com/0/public/Ticker?pair=XBTEUR",
    "fear_greed": "https://api.alternative.me/fng/?limit=2",
    "coingecko_global": "https://api.coingecko.com/api/v3/global",
}
out = {}
for k, u in URLS.items():
    t0 = time.time()
    try:
        req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 (robo-trading sonda)"})
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read()
        txt = body.decode(errors="replace")
        out[k] = {"ok": True, "ms": int(1000 * (time.time() - t0)), "bytes": len(body), "amostra": txt[:600]}
        if k in ("kraken_fut_tickers", "kraken_fut_instruments"):
            d = json.loads(txt)
            arr = d.get("tickers") or d.get("instruments") or []
            keep = [x for x in arr if str(x.get("symbol", "")).upper() in ("PF_XBTUSD", "PF_ETHUSD", "PF_SOLUSD", "PF_XRPUSD", "PF_ADAUSD", "PF_LINKUSD", "PF_LTCUSD", "PF_DOGEUSD", "PF_BNBUSD", "PF_TRXUSD")]
            out[k]["selecionados"] = keep
            out[k]["amostra"] = txt[:200]
    except Exception as e:
        out[k] = {"ok": False, "ms": int(1000 * (time.time() - t0)), "erro": repr(e)[:300]}
    print("%-24s %s" % (k, "OK" if out[k]["ok"] else "FALHOU " + out[k]["erro"][:80]), flush=True)
for name, cmd in (("pmset", ["pmset", "-g"]), ("pmset_sched", ["pmset", "-g", "sched"]), ("pmset_assert", ["pmset", "-g", "assertions"]), ("launchctl", ["launchctl", "list"])):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20).stdout
        out[name] = "\n".join(l for l in r.splitlines() if name != "launchctl" or "robotrading" in l)[:4000]
    except Exception as e:
        out[name] = repr(e)
os.makedirs(os.path.join(HERE, "trader", "vivo"), exist_ok=True)
with open(os.path.join(HERE, "trader", "vivo", "sonda.json"), "w") as fh:
    json.dump(out, fh, ensure_ascii=False, indent=1)
print("Resultado salvo em trader/vivo/sonda.json. Nenhuma ordem enviada.")
