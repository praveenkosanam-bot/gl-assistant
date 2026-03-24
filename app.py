import os
import time
from flask import Flask, jsonify, render_template, request
import requests

import core_services
import nlu_agent
import finance_agent

from core_services import AmbiguousHierarchyError
app = Flask(__name__)

@app.get("/")
def index():
    return render_template("index.html", model=core_services.OPENAI_MODEL)

@app.get("/api/health")
def health():
    db_ok = False; db_error = None
    try:
        row = core_services.query_one("SELECT 1 FROM dual")
        db_ok = bool(row)
    except Exception as exc: db_error = str(exc)
    return jsonify({
        "providers_supported": ["openai", "anthropic", "gemini"],
        "openai_model": core_services.OPENAI_MODEL,
        "db_connected": db_ok,
        "db_error": db_error,
        "mock_openai": core_services.MOCK_OPENAI,
        "rasa_configured": bool(core_services.RASA_URL),
        "question_inventory_loaded": bool(nlu_agent.QUESTION_INVENTORY),
        "openai_key_set": bool(core_services.OPENAI_API_KEY),
        "anthropic_key_set": bool(core_services.ANTHROPIC_API_KEY),
        "gemini_key_set": bool(core_services.GEMINI_API_KEY),
    })

@app.post("/api/nlu/parse")
def api_nlu_parse():
    payload = request.get_json(silent=True) or {}
    message = (payload.get("message") or "").strip()
    if not message: return jsonify({"error": "Message is required."}), 400
    rasa_result = None
    if core_services.RASA_URL:
        try: rasa_result = nlu_agent.parse_question_with_rasa(message)
        except requests.RequestException as exc: rasa_result = {"error": str(exc), "source": "rasa"}
    history = payload.get("history") or []
    return jsonify({
        "rasa": rasa_result,
        "lightweight": nlu_agent.parse_question_local(message),
        "routing": nlu_agent.resolve_question_rule_based(message, history)
    })

@app.post("/api/chat")
def chat():
    payload = request.get_json(silent=True) or {}
    message = (payload.get("message") or "").strip()
    history = payload.get("history") or []
    api_key = (payload.get("api_key") or "").strip()
    provider = (payload.get("provider") or "openai").lower()
    if not message: return jsonify({"error": "Message is required."}), 400
    full_history = [*history, {"role": "user", "content": message}]
    timings: dict[str, float] = {}
    try:
        started = time.perf_counter()
        routed = nlu_agent.resolve_question_with_llm(full_history, message, provider, api_key)
        route_duration = (time.perf_counter() - started) * 1000
        timings["route_ms"] = round(route_duration, 1)
        print(f"[API] Routing (LLM) took {route_duration:.1f}ms")
    except Exception as exc: return jsonify({"error": str(exc)}), 500
    path = routed["api_path"]; pms = routed.get("params") or {}
    if "hierarchy_id" in payload:
        pms["hierarchy_id"] = payload["hierarchy_id"]
    if path == "/api/db/none":
        res = finance_agent.dispatch_db_api(path, pms)
        return jsonify({"reply": finance_agent.format_chat_reply(path, res), "routing": routed, "db_result": None, "timings": timings})
    if path == "/api/db/unsupported":
        db_res = {"reason": routed.get("reason", "Endpoint unsupported.")}
        return jsonify({"reply": finance_agent.format_chat_reply(path, db_res), "routing": routed, "db_result": None, "timings": timings})
    if path == "/api/db/journal/details":
        db_res = finance_agent.db_journal_details(pms)
        m = db_res.get("drill_status_msg", ""); c = db_res.get("raw_drill_clob", "")
        if not c and "error" in (m or "").lower(): r = f"Error drilling into journals for {db_res.get('account_number')}: {m}"
        else: r = f"Journal Drilldown completed. Detailed payload generated internally (length: {(len(c) if c else 0)} chars)."
        return jsonify({"reply": r, "routing": routed, "db_result": db_res, "timings": timings})
    err = nlu_agent.validate_route_params(path, pms)
    if err: return jsonify({"error": err, "routing": routed}), 400
    try:
        started = time.perf_counter()
        res = finance_agent.dispatch_db_api(path, pms)
        db_duration = (time.perf_counter() - started) * 1000
        timings["db_api_ms"] = round(db_duration, 1)
        print(f"[API] DB API ({path}) took {db_duration:.1f}ms")
        r = finance_agent.format_chat_reply(path, res)
    except AmbiguousHierarchyError as exc:
        return jsonify({
            "reply": "I found multiple hierarchies for this field group. Please select one:",
            "options": exc.options,
            "routing": routed,
            "timings": timings
        })
    except Exception as exc:
        print(f"[API] DB API ({path}) failed: {exc}")
        return jsonify({"error": f"Database API failed: {exc}", "routing": routed}), 500
    return jsonify({"reply": r, "routing": routed, "db_result": res, "timings": timings})

# Wrapper endpoints for direct DB API access
@app.post("/api/db/balance/by-ccid")
def api_balance_by_ccid():
    pms = nlu_agent.complete_lookup_params("", request.get_json(silent=True) or {})
    return jsonify(finance_agent.db_balance_by_ccid(pms))

@app.post("/api/db/balance/by-account")
def api_balance_by_account():
    pms = nlu_agent.complete_lookup_params("", request.get_json(silent=True) or {})
    return jsonify(finance_agent.db_balance_by_account(pms))

@app.post("/api/db/balance/diff")
def api_balance_diff():
    pms = nlu_agent.complete_lookup_params("", request.get_json(silent=True) or {})
    return jsonify(finance_agent.db_balance_diff(pms))

@app.post("/api/db/balance/trend")
def api_balance_trend():
    pms = nlu_agent.complete_lookup_params("", request.get_json(silent=True) or {})
    return jsonify(finance_agent.db_balance_trend(pms))

@app.post("/api/db/balance/explain")
def api_balance_explain():
    pms = nlu_agent.complete_lookup_params("", request.get_json(silent=True) or {})
    return jsonify(finance_agent.db_balance_explain(pms))

@app.post("/api/db/balance/highlights")
def api_balance_highlights():
    pms = nlu_agent.complete_lookup_params("", request.get_json(silent=True) or {})
    return jsonify(finance_agent.db_balance_highlights(pms))

@app.post("/api/db/balance/diagnostics")
def api_balance_diagnostics():
    pms = nlu_agent.complete_lookup_params("", request.get_json(silent=True) or {})
    return jsonify(finance_agent.db_balance_diagnostics(pms))

if __name__ == "__main__":
    app.run(
        host=os.getenv("FLASK_HOST", "127.0.0.1"),
        port=int(os.getenv("FLASK_PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "").lower() in {"1", "true", "yes"},
    )
