import json
from typing import Any
import requests

import core_services
import rag_engine

RAG_SYSTEM_PROMPT = """You are GL Assistant, a concise Oracle General Ledger support assistant.

Use the retrieved knowledge snippets when they are relevant.
If database result data is provided, treat it as the source of truth for numeric answers.
Do not invent balances, ledger IDs, package behavior, or API capabilities.
If the knowledge base does not support the answer, say so briefly.
Keep answers short, direct, and useful.
"""

def generate_rag_reply(question: str, api_path: str, result: dict[str, Any]) -> str:
    if api_path not in {"/api/db/none", "/api/db/unsupported"}:
        return format_chat_reply(api_path, result)
    if not question or not core_services.GEMINI_API_KEY:
        return format_chat_reply(api_path, result)

    try:
        rag_context = rag_engine.build_rag_context(question)
    except Exception:
        rag_context = ""

    if not rag_context:
        return format_chat_reply(api_path, result)

    prompt = (
        f"User question: {question}\n\n"
        f"API path: {api_path}\n\n"
        f"Database/API result JSON:\n{json.dumps(result, default=str)}\n\n"
        f"Retrieved knowledge:\n{rag_context}\n\n"
        "Answer the user using the database result when present and the retrieved knowledge when relevant."
    )
    session = requests.Session(); session.trust_env = False
    try:
        resp = session.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{core_services.GEMINI_MODEL}:generateContent",
            headers={"x-goog-api-key": core_services.GEMINI_API_KEY, "Content-Type": "application/json"},
            json={"systemInstruction": {"parts": [{"text": RAG_SYSTEM_PROMPT}]}, "contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.1}},
            timeout=60,
        )
        resp.raise_for_status()
        text = resp.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        return text.strip() or format_chat_reply(api_path, result)
    except Exception:
        return format_chat_reply(api_path, result)

def get_account_for_ccid(ccid: int) -> str | None:
    row = core_services.query_one("SELECT gcc.segment3 FROM gl_code_combinations gcc WHERE gcc.code_combination_id = :ccid", {"ccid": ccid})
    return row[0] if row else None

def get_ledger_name(ledger_id: int | None) -> str | None:
    if ledger_id is None: return None
    if ledger_id == core_services.DEFAULT_LEDGER_ID: return core_services.DEFAULT_LEDGER_NAME
    row = core_services.query_one("SELECT name FROM gl_ledgers WHERE ledger_id = :ledger_id", {"ledger_id": ledger_id})
    return row[0] if row else str(ledger_id)

def annotate_ledger_metadata(result: dict[str, Any]) -> dict[str, Any]:
    ledger_id = result.get("ledger_id")
    if ledger_id is None: return result
    enriched = dict(result)
    enriched["ledger_name"] = get_ledger_name(ledger_id)
    return enriched

def db_balance_by_ccid(params: dict[str, Any]) -> dict[str, Any]:
    ledger_name = get_ledger_name(params["ledger_id"])
    account_str = str(get_account_for_ccid(params["ccid"]) or params["ccid"])
    period_name = params["period_name"]
    currency_code = params.get("currency_code", "USD")

    if not core_services.validate_ledger(ledger_name):
        return {"error": f"Invalid ledger name: {ledger_name}"}
    if not core_services.validate_period(period_name, ledger_name):
        return {"error": f"Invalid period '{period_name}' for ledger '{ledger_name}'"}
    if not core_services.validate_currency(currency_code):
        return {"error": f"Invalid currency code: {currency_code}"}

    hid = params.get("hierarchy_id")
    ytd, ytd_msg = core_services.call_glc_balance(ledger_name=ledger_name, period_name=period_name, actual_flag=params.get("actual_flag", "A"), account_string=account_str, period_type="YTD", hierarchy_id=hid, currency_code=currency_code)
    period_activity, activity_msg = core_services.call_glc_balance(ledger_name=ledger_name, period_name=period_name, actual_flag=params.get("actual_flag", "A"), account_string=account_str, period_type="PTD", hierarchy_id=hid, currency_code=currency_code)
    return {"lookup_type": "ccid", "ledger_id": params["ledger_id"], "ledger_name": ledger_name, "period_name": period_name, "ccid": params["ccid"], "account_number": account_str, "actual_flag": params.get("actual_flag", "A"), "ytd_balance": ytd, "period_activity": period_activity, "status_msg": ytd_msg or activity_msg, "resolved_from_seed": params.get("resolved_from_seed", False), "hierarchy_id": hid}

def db_balance_by_account(params: dict[str, Any]) -> dict[str, Any]:
    ledger_name = get_ledger_name(params["ledger_id"])
    period_name = params["period_name"]
    currency_code = params.get("currency_code", "USD")

    if not core_services.validate_ledger(ledger_name):
        return {"error": f"Invalid ledger name: {ledger_name}"}
    if not core_services.validate_period(period_name, ledger_name):
        return {"error": f"Invalid period '{period_name}' for ledger '{ledger_name}'"}
    if not core_services.validate_currency(currency_code):
        return {"error": f"Invalid currency code: {currency_code}"}

    hid = params.get("hierarchy_id")
    ytd, ytd_msg = core_services.call_glc_balance(ledger_name=ledger_name, period_name=period_name, actual_flag=params.get("actual_flag", "A"), account_string=params["account_number"], period_type="YTD", hierarchy_id=hid, currency_code=currency_code)
    period_activity, activity_msg = core_services.call_glc_balance(ledger_name=ledger_name, period_name=period_name, actual_flag=params.get("actual_flag", "A"), account_string=params["account_number"], period_type="PTD", hierarchy_id=hid, currency_code=currency_code)
    seed = core_services.seed_lookup(account_number=params["account_number"], ledger_id=params["ledger_id"], period_name=period_name, actual_flag=params.get("actual_flag", "A"))
    return {"lookup_type": "account_number", "ledger_id": params["ledger_id"], "period_name": period_name, "account_number": params["account_number"], "ccid": seed["ccid"] if seed else None, "actual_flag": params.get("actual_flag", "A"), "ytd_balance": float(ytd) if ytd is not None else None, "period_activity": float(period_activity) if period_activity is not None else None, "status_msg": ytd_msg or activity_msg, "resolved_from_seed": params.get("resolved_from_seed", False), "hierarchy_id": hid}

def db_balance_explain(params: dict[str, Any]) -> dict[str, Any]:
    where_filter = ["gb.ledger_id = :ledger_id", "gb.period_name = :period_name", "gb.actual_flag = :actual_flag"]
    bind = {"ledger_id": params["ledger_id"], "period_name": params["period_name"], "actual_flag": params.get("actual_flag", "A")}
    if params.get("ccid") is not None: where_filter.append("gb.code_combination_id = :ccid"); bind["ccid"] = params["ccid"]
    else: where_filter.append("gcc.segment3 = :account_number"); bind["account_number"] = params["account_number"]
    row = core_services.query_one(f"SELECT SUM(NVL(gb.begin_balance_dr,0)), SUM(NVL(gb.begin_balance_cr,0)), SUM(NVL(gb.period_net_dr,0)), SUM(NVL(gb.period_net_cr,0)) FROM gl_balances gb JOIN gl_code_combinations gcc ON gcc.code_combination_id = gb.code_combination_id WHERE {' AND '.join(where_filter)}", bind)
    begin_dr, begin_cr, net_dr, net_cr = row
    ytd = (begin_dr or 0) - (begin_cr or 0) + (net_dr or 0) - (net_cr or 0)
    return {"ledger_id": params["ledger_id"], "period_name": params["period_name"], "actual_flag": params.get("actual_flag", "A"), "ccid": params.get("ccid"), "account_number": params.get("account_number"), "begin_balance_dr": float(begin_dr or 0), "begin_balance_cr": float(begin_cr or 0), "period_net_dr": float(net_dr or 0), "period_net_cr": float(net_cr or 0), "ytd_balance": float(ytd), "resolved_from_seed": params.get("resolved_from_seed", False)}

def db_balance_diff(params: dict[str, Any]) -> dict[str, Any]:
    base = {"ledger_id": params["ledger_id"], "actual_flag": params.get("actual_flag", "A"), "resolved_from_seed": params.get("resolved_from_seed", False)}
    if params.get("ccid") is not None:
        before = db_balance_by_ccid({**base, "period_name": params["period_from"], "ccid": params["ccid"]})
        after = db_balance_by_ccid({**base, "period_name": params["period_to"], "ccid": params["ccid"]})
        ident = {"ccid": params["ccid"], "account_number": before.get("account_number")}
    else:
        before = db_balance_by_account({**base, "period_name": params["period_from"], "account_number": params["account_number"]})
        after = db_balance_by_account({**base, "period_name": params["period_to"], "account_number": params["account_number"]})
        ident = {"account_number": params["account_number"], "ccid": after.get("ccid")}
    return {**ident, "ledger_id": params["ledger_id"], "actual_flag": params.get("actual_flag", "A"), "period_from": params["period_from"], "period_to": params["period_to"], "ytd_from": before.get("ytd_balance"), "ytd_to": after.get("ytd_balance"), "period_activity_from": before.get("period_activity"), "period_activity_to": after.get("period_activity"), "ytd_delta": (after.get("ytd_balance") or 0) - (before.get("ytd_balance") or 0), "period_activity_delta": (after.get("period_activity") or 0) - (before.get("period_activity") or 0), "resolved_from_seed": params.get("resolved_from_seed", False)}

def db_balance_trend(params: dict[str, Any]) -> dict[str, Any]:
    bind = {"ledger_id": params["ledger_id"], "actual_flag": params.get("actual_flag", "A")}
    if params.get("ccid") is not None:
        rows = core_services.query_all("SELECT gb.period_name, SUM(NVL(gb.begin_balance_dr,0) - NVL(gb.begin_balance_cr,0) + NVL(gb.period_net_dr,0) - NVL(gb.period_net_cr,0)) AS ytd_balance, SUM(NVL(gb.period_net_dr,0) - NVL(gb.period_net_cr,0)) AS period_activity FROM gl_balances gb WHERE gb.ledger_id = :ledger_id AND gb.actual_flag = :actual_flag AND gb.code_combination_id = :ccid GROUP BY gb.period_name", {**bind, "ccid": params["ccid"]})
    else:
        rows = core_services.query_all("WITH target_ccids AS (SELECT code_combination_id FROM gl_code_combinations WHERE segment3 = :account_number) SELECT gb.period_name, SUM(NVL(gb.begin_balance_dr,0) - NVL(gb.begin_balance_cr,0) + NVL(gb.period_net_dr,0) - NVL(gb.period_net_cr,0)) AS ytd_balance, SUM(NVL(gb.period_net_dr,0) - NVL(gb.period_net_cr,0)) AS period_activity FROM gl_balances gb JOIN target_ccids tc ON tc.code_combination_id = gb.code_combination_id WHERE gb.ledger_id = :ledger_id AND gb.actual_flag = :actual_flag GROUP BY gb.period_name", {**bind, "account_number": params["account_number"]})
    sorted_rows = sorted(rows, key=lambda i: core_services.period_sort_key(i[0]))
    if params.get("period_name"):
        cutoff = core_services.normalize_period(params["period_name"])
        sorted_rows = [r for r in sorted_rows if core_services.period_sort_key(r[0]) <= core_services.period_sort_key(cutoff)]
    n = int(params.get("n") or 5); selected = sorted_rows[-n:]
    return {"ledger_id": params["ledger_id"], "ccid": params.get("ccid"), "account_number": params.get("account_number"), "actual_flag": params.get("actual_flag", "A"), "periods": [{"period_name": r[0], "ytd_balance": float(r[1] or 0), "period_activity": float(r[2] or 0)} for r in selected], "resolved_from_seed": params.get("resolved_from_seed", False)}

def db_balance_highlights(params: dict[str, Any]) -> dict[str, Any]:
    limit = int(params.get("limit") or 5)
    sort_expr = "ABS(SUM(NVL(gb.period_net_dr,0) - NVL(gb.period_net_cr,0)))" if params.get("sort_by") == "activity" else "ABS(SUM(NVL(gb.begin_balance_dr,0) - NVL(gb.begin_balance_cr,0) + NVL(gb.period_net_dr,0) - NVL(gb.period_net_cr,0)))"
    rows = core_services.query_all(f"SELECT gcc.segment3 AS account_number, SUM(NVL(gb.begin_balance_dr,0) - NVL(gb.begin_balance_cr,0) + NVL(gb.period_net_dr,0) - NVL(gb.period_net_cr,0)) AS ytd_balance, SUM(NVL(gb.period_net_dr,0) - NVL(gb.period_net_cr,0)) AS period_activity FROM gl_balances gb JOIN gl_code_combinations gcc ON gcc.code_combination_id = gb.code_combination_id WHERE gb.ledger_id = :ledger_id AND gb.period_name = :period_name AND gb.actual_flag = :actual_flag AND gcc.segment3 IS NOT NULL GROUP BY gcc.segment3 ORDER BY {sort_expr} DESC FETCH FIRST :limit ROWS ONLY", {"ledger_id": params["ledger_id"], "period_name": params["period_name"], "actual_flag": params.get("actual_flag", "A"), "limit": limit})
    return {"ledger_id": params["ledger_id"], "period_name": params["period_name"], "actual_flag": params.get("actual_flag", "A"), "top_accounts": [{"account_number": r[0], "ytd_balance": float(r[1] or 0), "period_activity": float(r[2] or 0)} for r in rows]}

def db_balance_diagnostics(params: dict[str, Any]) -> dict[str, Any]:
    res = {"ledger_id": params.get("ledger_id"), "period_name": params.get("period_name"), "actual_flag": params.get("actual_flag", "A"), "ccid": params.get("ccid"), "account_number": params.get("account_number")}
    if params.get("ccid") is not None:
        res["ccid_exists"] = bool(core_services.query_one("SELECT 1 FROM gl_code_combinations WHERE code_combination_id = :ccid", {"ccid": params["ccid"]}))
        res["balance_row_exists"] = bool(core_services.query_one("SELECT 1 FROM gl_balances WHERE ledger_id = :ledger_id AND period_name = :period_name AND code_combination_id = :ccid AND actual_flag = :actual_flag FETCH FIRST 1 ROW ONLY", {"ledger_id": params["ledger_id"], "period_name": params["period_name"], "ccid": params["ccid"], "actual_flag": params.get("actual_flag", "A")}))
    elif params.get("account_number") is not None:
        res["account_exists"] = bool(core_services.query_one("SELECT 1 FROM gl_code_combinations WHERE segment3 = :account FETCH FIRST 1 ROW ONLY", {"account": params["account_number"]}))
        res["balance_row_exists"] = bool(core_services.query_one("SELECT 1 FROM gl_balances gb JOIN gl_code_combinations gcc ON gcc.code_combination_id = gb.code_combination_id WHERE gb.ledger_id = :ledger_id AND gb.period_name = :period_name AND gb.actual_flag = :actual_flag AND gcc.segment3 = :account FETCH FIRST 1 ROW ONLY", {"ledger_id": params["ledger_id"], "period_name": params["period_name"], "actual_flag": params.get("actual_flag", "A"), "account": params["account_number"]}))
    return res

def db_journal_details(params: dict[str, Any]) -> dict[str, Any]:
    ledger_name = get_ledger_name(params.get("ledger_id", core_services.DEFAULT_LEDGER_ID))
    period_name = params.get("period_name")
    currency_code = params.get("currency_code", "USD")

    if not core_services.validate_ledger(ledger_name):
        return {"error": f"Invalid ledger name: {ledger_name}"}
    if period_name and not core_services.validate_period(period_name, ledger_name):
        return {"error": f"Invalid period '{period_name}' for ledger '{ledger_name}'"}
    if not core_services.validate_currency(currency_code):
        return {"error": f"Invalid currency code: {currency_code}"}

    account_str = params.get("account_number") or str(get_account_for_ccid(params.get("ccid")))
    hid = params.get("hierarchy_id")
    clob, msg = core_services.call_glc_drill(ledger_name=ledger_name, period_name=period_name, actual_flag=params.get("actual_flag", "A"), account_string=account_str, hierarchy_id=hid)
    return {"ledger_id": params.get("ledger_id"), "ledger_name": ledger_name, "period_name": period_name, "account_number": account_str, "raw_drill_clob": clob, "drill_status_msg": msg, "hierarchy_id": hid}

def dispatch_db_api(api_path: str, params: dict[str, Any]) -> dict[str, Any]:
    route_map = {
        "/api/db/balance/by-ccid": db_balance_by_ccid,
        "/api/db/balance/by-account": db_balance_by_account,
        "/api/db/balance/diff": db_balance_diff,
        "/api/db/balance/trend": db_balance_trend,
        "/api/db/balance/explain": db_balance_explain,
        "/api/db/balance/highlights": db_balance_highlights,
        "/api/db/balance/diagnostics": db_balance_diagnostics,
    }
    if api_path in route_map: return annotate_ledger_metadata(route_map[api_path](params))
    if api_path == "/api/db/none": return {"message": "This question does not require a database query."}
    if api_path == "/api/db/unsupported": return {"message": "This question maps to a database area that is not implemented yet."}
    raise KeyError(api_path)

def format_chat_reply(api_path: str, result: dict[str, Any]) -> str:
    lbl = result.get("ledger_name") or (get_ledger_name(result.get("ledger_id")) if "ledger_id" in result else None)
    cur = core_services.format_currency
    if api_path == "/api/db/balance/by-account": return f"Account {result.get('account_number')} in {lbl} for {result.get('period_name')} has YTD balance {cur(result.get('ytd_balance'))} and period activity {cur(result.get('period_activity'))}."
    if api_path == "/api/db/balance/by-ccid": return f"CCID {result.get('ccid')} in {lbl} for {result.get('period_name')} has YTD balance {cur(result.get('ytd_balance'))} and period activity {cur(result.get('period_activity'))}."
    if api_path == "/api/db/balance/diff":
        ident = f"account {result['account_number']}" if result.get("account_number") else f"CCID {result['ccid']}"
        return f"For {ident}, YTD changed by {cur(result['ytd_delta'])} between {result['period_from']} and {result['period_to']}. Period activity changed by {cur(result['period_activity_delta'])}."
    if api_path == "/api/db/balance/trend":
        parts = [f"{i['period_name']}: {cur(i['ytd_balance'])}" for i in result["periods"]]
        return "Trend: " + "; ".join(parts)
    if api_path == "/api/db/balance/explain": return f"YTD {cur(result['ytd_balance'])} = begin DR {cur(result['begin_balance_dr'])} - begin CR {cur(result['begin_balance_cr'])} + period DR {cur(result['period_net_dr'])} - period CR {cur(result['period_net_cr'])}."
    if api_path == "/api/db/balance/highlights":
        h = ", ".join(f"{i['account_number']} (YTD: {cur(i['ytd_balance'])}, Activity: {cur(i.get('period_activity', 0))})" for i in result.get("top_accounts", []))
        return f"Top accounts for {result['period_name']}: {h}"
    if api_path == "/api/db/balance/diagnostics": return json.dumps(result)
    return result.get("message", "No database result was needed.")
