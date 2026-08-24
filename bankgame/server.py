"""Local web server: JSON API + static UI. Standard library only.

Run with:  python3 run.py
Then open http://localhost:8321
"""

import json
import os
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .store import Store
from .sim import engine, ledger as L, statements, securities, competitors
from .sim import deposits as DEP, loans as LN, regulation as REG, funding as FUND
from .sim.newgame import new_game

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "web")

MIME = {".html": "text/html; charset=utf-8", ".js": "application/javascript",
        ".css": "text/css", ".png": "image/png", ".svg": "image/svg+xml",
        ".ico": "image/x-icon"}


class Game:
    def __init__(self):
        self.store = Store()
        self.state = None
        self.lock = threading.RLock()
        saves = self.store.list_saves()
        if saves:
            self.state = self.store.load(saves[0]["name"])

    # ------------- payload builders -------------
    def summary(self):
        s = self.state
        if s is None:
            return {"no_game": True, "saves": self.store.list_saves()}
        bank = s["bank"]
        ledger = bank["ledger"]
        econ = s["economy"]
        m = s["metrics"][-1] if s["metrics"] else {}
        mtd = statements.income_statement_mtd(s)
        curve = [(t, econ["curve"][str(t)]) for t in
                 [0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0, 20.0, 30.0]]
        return {
            "meta": s["meta"], "time": s["time"], "game_over": s["game_over"],
            "audit_alarm": s["audit_alarm"],
            "bank": {
                "name": bank["name"],
                "assets": L.total_assets(ledger),
                "loans": LN.total_loans(bank["loans"]),
                "deposits": L.total_deposits(ledger),
                "equity": L.total_equity(ledger),
                "cash": ledger["balances"]["1000"] + ledger["balances"]["1010"]
                        + ledger["balances"]["1100"],
                "ni_mtd": mtd["net_income"],
                "shares": bank["shares"],
                "aoci": -ledger["balances"]["3200"],
                "htm_unrealized": bank.get("cached_htm_unrealized", 0),
            },
            "metrics": m,
            "regulation": {
                "pca": s["regulation"]["pca"],
                "camels": s["regulation"]["camels"],
                "orders": s["regulation"]["orders"],
                "cra": s["regulation"]["cra"],
                "months_to_exam": s["regulation"]["months_to_exam"],
            },
            "econ": {
                "fed_funds": econ["fed_funds"], "inflation": econ["inflation"],
                "unemployment": econ["unemployment"], "gdp": econ["gdp_growth"],
                "oil": econ["oil"], "equity_index": round(econ["equity_index"], 1),
                "recession": econ["recession"], "stress": econ["credit_stress"],
                "curve": curve, "housing": round(econ["housing_index"], 1),
                "conf": econ["consumer_confidence"], "cattle": econ["cattle"],
                "cotton": econ["cotton"], "natgas": econ["natgas"],
            },
            "crisis": {"rumor": s["crisis"]["rumor"],
                       "run_active": s["crisis"]["run_active"],
                       "run_days": s["crisis"]["run_days"]},
            "pending": s["events"]["pending"],
            "log": s["events"]["log"][-20:],
            "counts": {"loan_queue": len(bank["loans"]["queue"]),
                       "fraud_cases": len([c for c in bank["fraud"]["cases"]
                                           if c["status"] == "open"])},
        }

    def section(self, name, args):
        s = self.state
        if s is None:
            return {"error": "no game loaded"}
        bank = s["bank"]
        ledger = bank["ledger"]
        econ = s["economy"]

        if name == "lending":
            home_rates = competitors.market_rates(s, "caprock")["loan"]
            return {
                "spreads": bank["loans"]["spreads"],
                "standards": bank["loans"]["standards"],
                "limits": bank["loans"]["limits"],
                "approval_threshold": bank["loans"]["approval_threshold"],
                "auto_policy": bank["loans"]["auto_policy"],
                "mortgage_sale_frac": bank["loans"]["mortgage_sale_frac"],
                "market_rates": home_rates,
                "queue": bank["loans"]["queue"],
                "portfolio": LN.portfolio_stats(s),
                "large": [l for l in bank["loans"]["large"]
                          if l["status"] not in ("paid", "defaulted")][-100:],
                "oreo": bank["loans"]["oreo"],
                "allowance": L.allowance(ledger),
                "reserve_required": bank["loans"]["reserve_required"],
                "capacity": LN.lender_capacity(s),
                "originated_mtd": bank["loans"]["stats"]["originated_mtd"],
                "products_enabled": bank["products_enabled"],
                "npl_balance": LN.npl_balance(bank["loans"]),
                "stats": bank["loans"]["stats"],
            }

        if name == "deposits":
            pools_by_market = {}
            for mid, mkt in bank["deposits"]["pools"].items():
                pools_by_market[mid] = {
                    "name": s["regions"][mid]["name"],
                    "products": {p: {"balance": mkt[p]["balance"],
                                     "accounts": mkt[p]["accounts"],
                                     "wavg_rate": mkt[p]["wavg_rate"]}
                                 for p in DEP.PRODUCTS},
                }
            return {
                "offsets_bp": bank["deposits"]["offsets_bp"],
                "effective_rates": {p: DEP.effective_rate(s, p) for p in DEP.PRODUCTS},
                "promo_cd_bonus": bank["deposits"]["promo_cd_bonus"],
                "fees": bank["deposits"]["fees"],
                "totals": DEP.totals(bank["deposits"]),
                "pools": pools_by_market,
                "market_rates": competitors.market_rates(s, "caprock")["deposit"],
                "mmf_rate": econ["mmf_rate"],
                "cost_of_deposits": DEP.cost_of_deposits(s),
                "uninsured": DEP.uninsured_share(s),
                "brokered": bank["funding"]["brokered"],
            }

        if name == "treasury":
            summ = securities.summary(s)
            lots = [dict(l) for l in bank["securities"]["lots"]]
            for l in lots:
                l["duration"] = securities.duration_lot(l, econ)
            lr, liquid = REG.liquidity_ratio(s)
            return {
                "lots": lots, "summary": summ,
                "hedges": bank["securities"]["hedges"],
                "curve": [(t, econ["curve"][str(t)]) for t in
                          [0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0, 20.0, 30.0]],
                "type_yields": {t: securities.type_yield(econ, t, 5.0)
                                for t in securities.TYPES},
                "funding": {"fhlb": bank["funding"]["fhlb"],
                            "brokered": bank["funding"]["brokered"],
                            "subdebt": bank["funding"]["subdebt"],
                            "fhlb_capacity": FUND.fhlb_capacity(s),
                            "ffp": -ledger["balances"]["2110"],
                            "dw": -ledger["balances"]["2120"],
                            "dw_uses": bank["funding"]["discount_window_uses"]},
                "cash": ledger["balances"]["1000"],
                "fed_funds_sold": ledger["balances"]["1100"],
                "liquidity_ratio": lr, "liquid_assets": liquid,
                "shares": bank["shares"],
                "tbv": L.total_equity(ledger) - ledger["balances"]["1600"],
                "dividend_payout": bank["policies"]["dividend_payout"],
                "aoci": -ledger["balances"]["3200"],
            }

        if name == "ops":
            unlocks = []
            for prod, (min_a, cost, label) in engine.UNLOCKS.items():
                unlocks.append({"product": prod, "label": label,
                                "min_assets": min_a, "cost": cost,
                                "enabled": prod in bank["products_enabled"],
                                "available": bank["cached_assets"] >= min_a})
            return {
                "branches": bank["ops"]["branches"],
                "staff": bank["ops"]["staff"],
                "salary_multiplier": bank["ops"]["salary_multiplier"],
                "marketing": bank["ops"]["marketing"],
                "brand": bank["ops"]["brand"],
                "digital_level": bank["ops"]["digital_level"],
                "core_system_age": bank["ops"]["core_system_age"],
                "cyber_spend": bank["ops"]["cyber_spend"],
                "audit_spend": bank["ops"]["audit_spend"],
                "service_quality": bank["ops"]["service_quality"],
                "unlocks": unlocks,
                "markets": {mid: {"name": r["name"], "kind": r["kind"]}
                            for mid, r in s["regions"].items()},
            }

        if name == "risk":
            ratios = REG.capital_ratios(s)
            lr, liquid = REG.liquidity_ratio(s)
            lots = bank["securities"]["lots"]
            sec_dur = securities.summary(s)["duration"]
            return {
                "capital": {k: v for k, v in ratios.items()},
                "pca": s["regulation"]["pca"],
                "camels": s["regulation"]["camels"],
                "orders": s["regulation"]["orders"],
                "cra": s["regulation"]["cra"],
                "months_to_exam": s["regulation"]["months_to_exam"],
                "exam_reports": s["regulation"]["exam_reports"][-6:],
                "liquidity_ratio": lr, "liquid_assets": liquid,
                "wholesale_dependence": REG.wholesale_dependence(s),
                "uninsured": DEP.uninsured_share(s),
                "sec_duration": sec_dur,
                "htm_unrealized": bank.get("cached_htm_unrealized", 0),
                "aoci": -ledger["balances"]["3200"],
                "fraud": {
                    "prevention_spend": bank["fraud"]["prevention_spend"],
                    "threshold": bank["fraud"]["threshold"],
                    "detection": LN and bank["fraud"].get("detection", 0.5),
                    "env": bank["fraud"]["env"],
                    "losses_by_channel": bank["fraud"]["losses_by_channel"],
                    "cases": bank["fraud"]["cases"][-20:],
                    "false_positive_drag": bank["fraud"]["false_positive_drag"],
                },
                "bsa": s["regulation"]["bsa"],
                "thresholds": {
                    "durbin": s["regulation"]["durbin_capped"],
                    "enhanced": s["regulation"]["enhanced_prudential"],
                    "lcr": s["regulation"]["lcr_required"],
                    "gsib": s["regulation"]["gsib"],
                },
                "crisis": s["crisis"],
            }

        if name == "markets":
            regions_out = {}
            for mid, r in s["regions"].items():
                pool = bank["deposits"]["pools"].get(mid)
                my_dep = sum(pool[p]["balance"] for p in DEP.PRODUCTS) if pool else 0
                regions_out[mid] = {
                    "name": r["name"], "kind": r["kind"], "pop": r["pop"],
                    "income": r["income"], "activity": r["local_activity"],
                    "deposit_pool": r["deposit_pool"], "competition": r["competition"],
                    "shock": r["shock"], "note": r["note"],
                    "housing": r["housing_index"],
                    "my_deposits": my_dep,
                    "my_share": my_dep / max(1, r["deposit_pool"]),
                    "my_branches": len([b for b in bank["ops"]["branches"]
                                        if b["market"] == mid and b["open"]]),
                    "brand": bank["ops"]["brand"].get(mid, 0),
                    "history": r["history"][-120:],
                }
            peers = competitors.peer_group(s)
            me_m = s["metrics"][-1] if s["metrics"] else {}
            return {
                "regions": regions_out,
                "econ_history": econ["history"][-360:],
                "competitors": [{k: b[k] for k in
                                 ("name", "strategy", "assets", "equity_ratio",
                                  "npa_ratio", "roa", "nim", "efficiency", "alive",
                                  "markets")}
                                for b in s["competitors"]["banks"]],
                "peers": [{k: b[k] for k in ("name", "assets", "roa", "nim",
                                             "efficiency", "npa_ratio", "equity_ratio")}
                          for b in peers],
                "me": {"roa": me_m.get("roa", 0), "nim": me_m.get("nim", 0),
                       "efficiency": me_m.get("efficiency", 0),
                       "npa_ratio": me_m.get("npa_ratio", 0),
                       "assets": bank["cached_assets"]},
                "failed": s["competitors"]["failed_log"][-20:],
            }

        if name == "reports":
            return {
                "balance_sheet": statements.balance_sheet(s),
                "income_mtd": statements.income_statement_mtd(s),
                "income_q": statements.income_statement(s, 3),
                "income_ttm": statements.income_statement(s, 12),
                "metrics_history": s["metrics"][-480:],
                "call_reports": [{"date": c["date"], "pca": c["pca"],
                                  "camels": c["camels"]["composite"]}
                                 for c in s["call_reports"][-40:]],
                "cash_flow": statements.cash_flow_statement(s),
                "months": ledger["months"][-24:],
            }

        if name == "call_report":
            idx = int(args.get("idx", ["-1"])[0])
            if s["call_reports"]:
                return s["call_reports"][idx]
            return {"error": "no call reports yet"}

        if name == "ledger":
            tag = args.get("tag", [""])[0]
            entries = ledger["entries"]
            if tag:
                entries = [e for e in entries if e["tag"] == tag]
            return {
                "balances": {code: {"name": L.CHART[code][0],
                                    "type": L.CHART[code][1],
                                    "balance": L.display_balance(ledger, code)}
                             for code in sorted(L.CHART)},
                "entries": entries[-300:],
                "trial_balance": L.trial_balance(ledger),
                "months": [{"month": m["month"], "net_income": m["net_income"]}
                           for m in ledger["months"][-36:]],
            }

        if name == "events":
            return {"log": s["events"]["log"], "pending": s["events"]["pending"]}

        if name == "saves":
            return {"saves": self.store.list_saves(),
                    "snapshots": self.store.list_snapshots(s["meta"]["name"])
                    if s else []}

        return {"error": "unknown section %s" % name}


GAME = Game()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass  # quiet

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}

    def do_GET(self):
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)
        path = parsed.path
        args = parse_qs(parsed.query)
        try:
            if path == "/api/summary":
                with GAME.lock:
                    return self._json(GAME.summary())
            if path == "/api/section":
                with GAME.lock:
                    return self._json(GAME.section(args.get("name", [""])[0], args))
            if path == "/api/saves":
                with GAME.lock:
                    name = GAME.state["meta"]["name"] if GAME.state else None
                    return self._json({
                        "saves": GAME.store.list_saves(),
                        "current": name,
                        "snapshots": GAME.store.list_snapshots(name) if name else []})
            return self._static(path)
        except BrokenPipeError:
            pass
        except Exception:
            traceback.print_exc()
            try:
                self._json({"error": "server error", "detail": traceback.format_exc()}, 500)
            except Exception:
                pass

    def do_POST(self):
        body = self._read_body()
        try:
            if self.path == "/api/new":
                name = str(body.get("name") or "First National Bank of Caprock")[:60]
                seed = body.get("seed")
                if not isinstance(seed, int):
                    seed = int.from_bytes(os.urandom(4), "big")
                with GAME.lock:
                    GAME.state = new_game(name, seed)
                    GAME.store.create_save(name, seed)
                    GAME.store.snapshot(GAME.state)
                return self._json({"ok": True, "seed": seed})

            if self.path == "/api/load":
                with GAME.lock:
                    st = GAME.store.load(str(body.get("name", "")))
                    if st is None:
                        return self._json({"error": "save not found"}, 404)
                    GAME.state = st
                return self._json({"ok": True})

            if self.path == "/api/rollback":
                with GAME.lock:
                    if GAME.state is None:
                        return self._json({"error": "no game"}, 400)
                    st = GAME.store.load(GAME.state["meta"]["name"],
                                         int(body.get("day_index", 0)))
                    if st is None:
                        return self._json({"error": "snapshot not found"}, 404)
                    GAME.state = st
                return self._json({"ok": True})

            if self.path == "/api/delete_save":
                with GAME.lock:
                    GAME.store.delete_save(str(body.get("name", "")))
                return self._json({"ok": True})

            if self.path == "/api/advance":
                unit = str(body.get("unit", "day"))
                with GAME.lock:
                    if GAME.state is None:
                        return self._json({"error": "no game"}, 400)
                    res = engine.advance(GAME.state, unit)
                    GAME.store.snapshot(GAME.state)
                return self._json({"ok": True, "result":
                                   {"days": res["days"], "date": res["date"],
                                    "events": [{"id": e["id"], "title": e["title"],
                                                "blocking": e.get("blocking", False)}
                                               for e in res["events"]]}})

            if self.path == "/api/set":
                with GAME.lock:
                    if GAME.state is None:
                        return self._json({"error": "no game"}, 400)
                    try:
                        res = engine.set_policy(GAME.state, str(body.get("path", "")),
                                                body.get("value"))
                    except engine.ActionError as e:
                        return self._json({"error": str(e)}, 400)
                    GAME.store.snapshot(GAME.state)
                return self._json({"ok": True, "result": res})

            if self.path == "/api/action":
                with GAME.lock:
                    if GAME.state is None:
                        return self._json({"error": "no game"}, 400)
                    try:
                        res = engine.perform_action(GAME.state,
                                                    str(body.get("action", "")),
                                                    body.get("payload") or {})
                    except engine.ActionError as e:
                        return self._json({"error": str(e)}, 400)
                    GAME.store.snapshot(GAME.state)
                return self._json({"ok": True, "result": res})

            return self._json({"error": "unknown endpoint"}, 404)
        except BrokenPipeError:
            pass
        except Exception:
            traceback.print_exc()
            try:
                self._json({"error": "server error", "detail": traceback.format_exc()}, 500)
            except Exception:
                pass

    def _static(self, path):
        if path == "/":
            path = "/index.html"
        fname = os.path.normpath(os.path.join(WEB_DIR, path.lstrip("/")))
        if not fname.startswith(os.path.normpath(WEB_DIR)) or not os.path.isfile(fname):
            self._json({"error": "not found"}, 404)
            return
        ext = os.path.splitext(fname)[1]
        with open(fname, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", MIME.get(ext, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main(port=8321, open_browser=True):
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = "http://localhost:%d" % port
    print("=" * 56)
    print("  BANK GAME is running.")
    print("  Open %s in your browser." % url)
    print("  Press Ctrl+C here to quit. Your game autosaves.")
    print("=" * 56)
    if open_browser:
        import webbrowser
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down. Goodbye.")


if __name__ == "__main__":
    main()
