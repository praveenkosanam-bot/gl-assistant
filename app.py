import os
import time
from flask import Flask, jsonify, render_template, request

import core_services
import nlu_agent
import finance_agent
import rag_engine

from core_services import AmbiguousHierarchyError
app = Flask(__name__)

@app.get("/")
def index():
    return render_template("index.html", model=core_services.GEMINI_MODEL)

@app.get("/api/health")
def health():
    db_ok = False; db_error = None
    try:
        row = core_services.query_one("SELECT 1 FROM dual")
        db_ok = bool(row)
    except Exception as exc: db_error = str(exc)
    vectorstore = rag_engine.load_vectorstore()
    rag_doc_count = len((vectorstore or {}).get("documents", []))
    return jsonify({
        "gemini_model": core_services.GEMINI_MODEL,
        "db_connected": db_ok,
        "db_error": db_error,
        "mock_llm": core_services.MOCK_LLM,
        "rasa_configured": bool(core_services.RASA_URL),
        "question_inventory_loaded": bool(nlu_agent.QUESTION_INVENTORY),
        "gemini_key_set": bool(core_services.GEMINI_API_KEY),
        "rag_enabled": True,
        "rag_vectorstore_present": bool(vectorstore),
        "rag_knowledge_dir": rag_engine.KNOWLEDGE_DIR,
        "rag_vectorstore_path": rag_engine.VECTORSTORE_PATH,
        "rag_documents_indexed": rag_doc_count,
    })

@app.post("/api/nlu/parse")
def api_nlu_parse():
    import requests as req_lib
    payload = request.get_json(silent=True) or {}
    message = (payload.get("message") or "").strip()
    if not message: return jsonify({"error": "Message is required."}), 400
    rasa_result = None
    if core_services.RASA_URL:
        try: rasa_result = nlu_agent.parse_question_with_rasa(message)
        except req_lib.RequestException as exc: rasa_result = {"error": str(exc), "source": "rasa"}
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
    if not message: return jsonify({"error": "Message is required."}), 400
    full_history = [*history, {"role": "user", "content": message}]
    timings: dict[str, float] = {}
    try:
        started = time.perf_counter()
        routed = nlu_agent.resolve_question_with_llm(full_history, message)
        route_duration = (time.perf_counter() - started) * 1000
        timings["route_ms"] = round(route_duration, 1)
        print(f"[API] Routing (LLM) took {route_duration:.1f}ms")
    except Exception as exc: return jsonify({"error": str(exc)}), 500
    path = routed["api_path"]; pms = routed.get("params") or {}
    if "hierarchy_id" in payload:
        pms["hierarchy_id"] = payload["hierarchy_id"]
    if path == "/api/db/none":
        res = finance_agent.dispatch_db_api(path, pms)
        reply = finance_agent.generate_rag_reply(message, path, res)
        return jsonify({"reply": reply, "routing": routed, "db_result": None, "timings": timings})
    if path == "/api/db/unsupported":
        db_res = {"reason": routed.get("reason", "Endpoint unsupported.")}
        reply = finance_agent.generate_rag_reply(message, path, db_res)
        return jsonify({"reply": reply, "routing": routed, "db_result": None, "timings": timings})
    if path == "/api/db/journal/details":
        try:
            db_res = finance_agent.db_journal_details(pms)
            m = db_res.get("drill_status_msg", ""); c = db_res.get("raw_drill_clob", "")
            if not c and "error" in (m or "").lower(): r = f"Error drilling into journals for {db_res.get('account_number')}: {m}"
            else: r = f"Journal Drilldown completed. Detailed payload generated internally (length: {(len(c) if c else 0)} chars)."
            return jsonify({"reply": r, "routing": routed, "db_result": db_res, "timings": timings})
        except AmbiguousHierarchyError as exc:
            return jsonify({
                "reply": "I found multiple hierarchies for this field group. Please select one:",
                "options": exc.options,
                "routing": routed,
                "timings": timings
            })
    err = nlu_agent.validate_route_params(path, pms)
    if err: return jsonify({"error": err, "routing": routed}), 400
    try:
        started = time.perf_counter()
        res = finance_agent.dispatch_db_api(path, pms)
        db_duration = (time.perf_counter() - started) * 1000
        timings["db_api_ms"] = round(db_duration, 1)
        print(f"[API] DB API ({path}) took {db_duration:.1f}ms")
        r = finance_agent.generate_rag_reply(message, path, res)
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

# ── Excel / External Agent Endpoint ──────────────────────────────────────────
# Call from Excel VBA:
#   Dim http As Object: Set http = CreateObject("MSXML2.XMLHTTP.6.0")
#   http.Open "POST", "http://<host>:5000/api/excel/query", False
#   http.setRequestHeader "Content-Type", "application/json"
#   http.Send "{""question"":""Balance for 11200 in 01-23""}"
#   MsgBox http.responseText
#
# Call from Power Query:
#   let src = Web.Contents("http://<host>:5000/api/excel/query",
#     [Headers=[#"Content-Type"="application/json"],
#      Content=Text.ToBinary("{""question"":""Balance for 11200 in 01-23""}")])
#   in Json.Document(src)
# ─────────────────────────────────────────────────────────────────────────────
@app.post("/api/excel/query")
def excel_query():
    # CORS — allow Excel/Office add-ins and Power Query to call this
    def _cors(response):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return response

    payload = request.get_json(silent=True) or {}
    question = (payload.get("question") or payload.get("message") or "").strip()
    history = payload.get("history") or []
    if not question:
        return _cors(jsonify({"error": "Provide a 'question' field."})), 400

    full_history = [*history, {"role": "user", "content": question}]
    try:
        routed = nlu_agent.resolve_question_with_llm(full_history, question)
    except Exception as exc:
        return _cors(jsonify({"error": str(exc)})), 500

    path = routed["api_path"]
    pms = routed.get("params") or {}

    if path in {"/api/db/none", "/api/db/unsupported"}:
        res = finance_agent.dispatch_db_api(path, pms)
        reply = finance_agent.generate_rag_reply(question, path, res)
        return _cors(jsonify({"reply": reply, "data": None, "route": path}))

    err = nlu_agent.validate_route_params(path, pms)
    if err:
        return _cors(jsonify({"error": err, "route": path})), 400

    try:
        db_res = finance_agent.dispatch_db_api(path, pms)
        reply = finance_agent.generate_rag_reply(question, path, db_res)
        return _cors(jsonify({"reply": reply, "data": db_res, "route": path}))
    except Exception as exc:
        return _cors(jsonify({"error": str(exc), "route": path})), 500

@app.route("/api/excel/query", methods=["OPTIONS"])
def excel_query_preflight():
    resp = jsonify({})
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp, 204


if __name__ == "__main__":
    app.run(
        host=os.getenv("FLASK_HOST", "127.0.0.1"),
        port=int(os.getenv("FLASK_PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "").lower() in {"1", "true", "yes"},
    )
