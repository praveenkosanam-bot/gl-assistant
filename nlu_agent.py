import json
import re
import requests
import yaml
from typing import Any
import core_services

SYSTEM_PROMPT = """You are GL Assistant, a concise finance support assistant for Oracle GL balances.

You answer two kinds of questions:
1. Live balance questions using the supplied database context.
2. API usage questions for this app and its balance endpoints.

Rules:
- Use live balance context when it is provided. Do not invent balances.
- If the balance context used inferred values from a seed row, say that clearly.
- If the user asks for a balance but key inputs are missing, state what is missing.
- When explaining API usage, be practical and reference these available server routes:
  - GET /api/health
  - POST /api/chat
- Balance data is sourced from Oracle package GLCAI_PKG_BAL.
- Account-based lookups use GL_CODE_COMBINATIONS.SEGMENT3 as the account number.
- Keep answers short, direct, and useful.
"""

ROUTING_INSTRUCTIONS = """
You must output ONLY valid JSON using the following structure. Do NOT output any markdown blocks or formatting.
{
  "api_path": "<route>",
  "params": { ... }
}

Allowed routes:
- /api/db/balance/by-ccid
- /api/db/balance/by-account
- /api/db/balance/diff
- /api/db/balance/trend
- /api/db/balance/explain
- /api/db/balance/highlights
- /api/db/balance/diagnostics
- /api/db/journal/details
- /api/db/none

Routing Rules:
- If the question is about balances for a CCID, route to by-ccid.
- If the question is about balances for an account number, route to by-account.
- If the question asks to compare two periods, use diff.
- If it asks for history or last N periods, use trend.
- If it asks to explain a calculation, use explain.
- If it asks why a result is null/zero or whether a CCID exists, use diagnostics.
- If it asks for high-level GL balance highlights or highest activity, use highlights. Include "sort_by": "activity" in params if activity is requested.
- If it is an API usage question, use /api/db/none.
- If it asks about journals, use /api/db/journal/details.
- Extract only params that are present or safely inferable.
- Default actual_flag to A when omitted.
"""

BALANCE_KEYWORDS = ("balance", "ccid", "account", "ledger", "period", "ytd", "activity")
SUPPORTED_API_PATHS = {
    "/api/db/balance/by-ccid",
    "/api/db/balance/by-account",
    "/api/db/balance/diff",
    "/api/db/balance/trend",
    "/api/db/balance/explain",
    "/api/db/balance/highlights",
    "/api/db/balance/diagnostics",
}
INTENT_API_MAP = {
    "balance.lookup.ccid.period": "/api/db/balance/by-ccid",
    "balance.lookup.ccid.ytd": "/api/db/balance/by-ccid",
    "balance.lookup.segments.period": "/api/db/balance/by-account",
    "balance.diff.two_periods": "/api/db/balance/diff",
    "balance.trend.last_n": "/api/db/balance/trend",
    "balance.type.override": "/api/db/balance/by-account",
    "balance.currency.override": "/api/db/balance/by-ccid",
    "balance.why_null_or_zero": "/api/db/balance/diagnostics",
    "balance.explain.calculation": "/api/db/balance/explain",
    "balance.high_level": "/api/db/balance/highlights",
    "journals.lookup.basic": "/api/db/unsupported",
    "journals.summary.by_source": "/api/db/unsupported",
}

def load_question_inventory() -> list[dict[str, Any]]:
    if not core_services.QUESTION_INVENTORY_PATH.exists():
        return []
    data = yaml.safe_load(core_services.QUESTION_INVENTORY_PATH.read_text(encoding="utf-8")) or {}
    return data.get("intents", [])

QUESTION_INVENTORY = load_question_inventory()

def tokenize(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) > 1}

def parse_question_local(question: str) -> dict[str, Any]:
    entities = core_services.extract_filters(question)
    question_tokens = tokenize(question)
    best_intent = None
    best_score = 0.0
    for intent in QUESTION_INVENTORY:
        score = 0.0
        description_tokens = tokenize(intent.get("description", ""))
        utterance_scores = []
        for utterance in intent.get("utterances", []):
            utterance_tokens = tokenize(utterance)
            if utterance_tokens:
                utterance_scores.append(len(question_tokens & utterance_tokens) / len(utterance_tokens))
        if utterance_scores: score += max(utterance_scores) * 0.75
        if description_tokens: score += (len(question_tokens & description_tokens) / len(description_tokens)) * 0.25
        entity_names = set(intent.get("entities", []))
        score += len(entity_names & set(entities.keys())) * 0.08
        if "ccid" in entity_names and entities.get("ccid") is not None: score += 0.2
        if "account" in entity_names and entities.get("account_number") is not None: score += 0.2
        if "period_from" in entity_names and entities.get("period_from") is not None: score += 0.2
        if intent["name"].startswith("journals.") and "journal" in question.lower(): score += 0.25
        if score > best_score:
            best_score = score
            best_intent = intent["name"]
    if not best_intent:
        best_intent = "balance.high_level" if any(token in question.lower() for token in BALANCE_KEYWORDS) else "balance.high_level"
    return {"intent": best_intent, "confidence": round(best_score, 4), "entities": entities, "source": "lightweight"}

def parse_question_with_rasa(question: str) -> dict[str, Any] | None:
    if not core_services.RASA_URL: return None
    session = requests.Session()
    session.trust_env = False
    response = session.post(f"{core_services.RASA_URL}/model/parse", json={"text": question}, timeout=10)
    response.raise_for_status()
    payload = response.json()
    entities = core_services.extract_filters(question)
    for entity in payload.get("entities", []):
        name = entity.get("entity"); value = entity.get("value")
        if name in {"ledger_id", "ccid", "n"} and value is not None:
            try: entities[name] = int(value)
            except Exception: entities[name] = value
        elif name == "account": entities["account_number"] = str(value)
        elif name == "period": entities["period_name"] = str(value).upper()
        elif name == "period_from": entities["period_from"] = str(value).upper()
        elif name == "period_to": entities["period_to"] = str(value).upper()
        elif name and value is not None: entities[name] = value
    return {"intent": (payload.get("intent") or {}).get("name"), "confidence": (payload.get("intent") or {}).get("confidence", 0.0), "entities": entities, "source": "rasa"}

def complete_lookup_params(question: str, params: dict[str, Any], history: list[dict[str, str]] | None = None) -> dict[str, Any]:
    completed = {}
    if history:
        for turn in history:
            if turn.get("role") == "user":
                completed.update(core_services.extract_filters(turn.get("content", "")))
    completed.update(core_services.extract_filters(question) if question else {})
    completed.update(params)
    completed.setdefault("actual_flag", "A")
    completed.setdefault("ledger_id", core_services.DEFAULT_LEDGER_ID)
    if completed.get("account_number"):
        acct_str = str(completed["account_number"]).lower()
        if not re.fullmatch(r"[\d\.\-]+", acct_str):
            for alias, acct_id in core_services.ACCOUNT_ALIASES.items():
                if alias in acct_str:
                    completed["account_number"] = acct_id
                    break
    if completed.get("period_name"): completed["period_name"] = core_services.normalize_period(completed["period_name"])
    if completed.get("period_from"): completed["period_from"] = core_services.normalize_period(completed["period_from"])
    if completed.get("period_to"): completed["period_to"] = core_services.normalize_period(completed["period_to"])
    if any(completed.get(k) is not None for k in ("ccid", "account_number")) and any(completed.get(k) is None for k in ("ledger_id", "period_name")):
        seed = core_services.seed_lookup(account_number=completed.get("account_number"), ccid=completed.get("ccid"), ledger_id=completed.get("ledger_id"), period_name=completed.get("period_name"), actual_flag=completed.get("actual_flag"))
        if not seed:
            seed = core_services.seed_lookup(account_number=completed.get("account_number"), ccid=completed.get("ccid"), ledger_id=completed.get("ledger_id"), period_name=completed.get("period_name"), actual_flag=None)
        if seed:
            for k, v in seed.items(): completed.setdefault(k, v)
            completed["resolved_from_seed"] = True
    else: completed["resolved_from_seed"] = False
    return completed

def validate_route_params(api_path: str, params: dict[str, Any]) -> str | None:
    req: dict[str, tuple[str, ...]] = {
        "/api/db/balance/by-ccid": ("ledger_id", "period_name", "ccid"),
        "/api/db/balance/by-account": ("ledger_id", "period_name", "account_number"),
        "/api/db/balance/diff": ("ledger_id", "period_from", "period_to"),
        "/api/db/balance/trend": ("ledger_id",),
        "/api/db/balance/explain": ("ledger_id", "period_name"),
        "/api/db/balance/highlights": ("ledger_id", "period_name"),
        "/api/db/balance/diagnostics": (),
    }
    required = req.get(api_path)
    if required is None: return None
    missing = [f for f in required if params.get(f) is None]
    if api_path in {"/api/db/balance/diff", "/api/db/balance/explain", "/api/db/journal/details"} and params.get("ccid") is None and params.get("account_number") is None:
        missing.append("ccid or account_number")
    if api_path == "/api/db/balance/diagnostics" and (params.get("ledger_id") is None or params.get("period_name") is None or (params.get("ccid") is None and params.get("account_number") is None)):
        missing.append("required fields")
    return "Missing required query inputs: " + ", ".join(missing) if missing else None

def resolve_question_rule_based(question: str, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
    parsed = parse_question_local(question)
    params = complete_lookup_params(question, parsed["entities"], history)
    api_path = INTENT_API_MAP.get(parsed["intent"], "/api/db/balance/highlights")
    text = question.lower()
    if re.search(r"\b(journals?|payables|posted journals?|journal totals?|journal summary)\b", text):
        return {"api_path": "/api/db/journal/details", "params": params}
    if "how do i call" in text or "/api/" in text or "javascript" in text:
        return {"api_path": "/api/db/none", "params": {}, "reason": "API usage question."}
    if re.search(r"\b(compare|changed between|month.on.month|delta|what changed)\b", text) or "Δ" in question or "δ" in question:
        api_path = "/api/db/balance/diff"
    elif re.search(r"\b(trend|trended|last \d|history|\d+[- ]period|recently)\b", text): api_path = "/api/db/balance/trend"
    elif re.search(r"\b(explain|break.?down|breakdown|debit.?credit)\b", text): api_path = "/api/db/balance/explain"
    elif re.search(r"\b(why|zero|null|exist|open for this ledger)\b", text): api_path = "/api/db/balance/diagnostics"
    elif re.search(r"\b(high balances?|changed the most|unusual|what does our gl|highest activity|highest|look like|anything unusual|show accounts)\b", text):
        params.setdefault("limit", 5); api_path = "/api/db/balance/highlights"
    if api_path == "/api/db/balance/by-account" and params.get("account_number") is None and params.get("ccid") is not None: api_path = "/api/db/balance/by-ccid"
    if api_path == "/api/db/balance/by-ccid" and params.get("ccid") is None and params.get("account_number") is not None: api_path = "/api/db/balance/by-account"
    if api_path == "/api/db/balance/highlights": params.setdefault("limit", 5)
    if params.get("account_number") in ("has", "is", "for", "in", "the", "change", "what", "which"): params["account_number"] = None
    return {"api_path": api_path, "params": params, "intent": parsed["intent"], "intent_confidence": parsed["confidence"], "parser_source": parsed["source"]}

def resolve_question_with_llm(history: list[dict[str, str]], question: str) -> dict[str, Any]:
    if core_services.MOCK_LLM or not core_services.GEMINI_API_KEY:
        return resolve_question_rule_based(question, history)
    try:
        rasa_result = parse_question_with_rasa(question)
    except Exception:
        rasa_result = None
    if rasa_result and rasa_result.get("intent") in INTENT_API_MAP:
        routed = {"api_path": INTENT_API_MAP[rasa_result["intent"]], "params": complete_lookup_params(question, rasa_result["entities"], history), "intent": rasa_result["intent"], "intent_confidence": rasa_result["confidence"], "parser_source": rasa_result["source"], "routing_mode": "rasa"}
        if routed["api_path"] == "/api/db/balance/highlights": routed["params"].setdefault("limit", 5)
        return routed
    transcript = [f"{i.get('role','').title()}: {i.get('content','').strip()}" for i in history[-8:] if i.get("content","").strip()]
    prompt = "\n".join(transcript) + f"\n\nLatest user question: {question}"
    session = requests.Session(); session.trust_env = False
    try:
        import time
        start_llm = time.perf_counter()
        resp = session.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{core_services.GEMINI_MODEL}:generateContent",
            headers={"x-goog-api-key": core_services.GEMINI_API_KEY, "Content-Type": "application/json"},
            json={"systemInstruction": {"parts": [{"text": SYSTEM_PROMPT + "\n" + ROUTING_INSTRUCTIONS}]}, "contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.0}},
            timeout=60,
        )
        resp.raise_for_status()
        text = resp.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        llm_duration = (time.perf_counter() - start_llm) * 1000
        print(f"[LLM] Gemini request took {llm_duration:.1f}ms")
        if not text: raise RuntimeError("Gemini response did not contain routing output.")
        try: routed = json.loads(text)
        except Exception:
            m = re.search(r"\{.*\}", text, re.DOTALL)
            if not m: raise RuntimeError(f"Gemini route output was not valid JSON: {text}")
            routed = json.loads(m.group(0))
        if routed.get("api_path") not in SUPPORTED_API_PATHS | {"/api/db/none", "/api/db/unsupported", "/api/db/journal/details"}:
            raise RuntimeError(f"Gemini returned unsupported api path: {routed.get('api_path')}")
        routed["params"] = complete_lookup_params(question, routed.get("params") or {}, history)
        routed["routing_mode"] = "gemini"
        return routed
    except Exception as e:
        routed = resolve_question_rule_based(question, history); routed["routing_mode"] = f"gemini_fallback_due_to_{type(e).__name__}"
        return routed
