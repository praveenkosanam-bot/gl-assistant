"""
Test script for GL Assistant – one request per question in glcai_questions.yaml.
Tests the Flask /api/chat endpoint directly (no API key, so routing falls back to 
rule-based), then evaluates what type of response is returned.

Run with:  python -m .venv/Scripts/python.exe test_questions.py
"""
import sys, os, json, time, re, requests, yaml
sys.path.append(os.getcwd())

BASE_URL = "http://127.0.0.1:5000"
DEFAULT_HIERARCHY_HINT = os.getenv("TEST_HIERARCHY_HINT", "CORPORATE").strip().lower()

def load_questions():
    """Load all utterances from the YAML, tagged by intent."""
    with open("robot/tests/glcai_questions.yaml", "r") as f:
        data = yaml.safe_load(f)
    questions = []
    for intent in data.get("intents", []):
        for utt in intent.get("utterances", []):
            questions.append({"intent": intent["name"], "question": utt})
    return questions

def choose_hierarchy(options: list[dict]) -> dict | None:
    if not options:
        return None
    if DEFAULT_HIERARCHY_HINT:
        for option in options:
            if DEFAULT_HIERARCHY_HINT in (option.get("name", "").lower()):
                return option
    return options[0]

def ask(question: str) -> dict:
    """Send a question to /api/chat (no LLM key – rule-based routing)."""
    try:
        resp = requests.post(
            f"{BASE_URL}/api/chat",
            json={"message": question, "provider": "openai", "api_key": ""},
            timeout=30,
        )
        body = resp.json() if resp.ok else {"error": resp.text}
        if resp.ok and body.get("options"):
            choice = choose_hierarchy(body.get("options") or [])
            if choice:
                resp = requests.post(
                    f"{BASE_URL}/api/chat",
                    json={"message": question, "provider": "openai", "api_key": "", "hierarchy_id": choice.get("id")},
                    timeout=30,
                )
                body = resp.json() if resp.ok else {"error": resp.text}
        return {"status": resp.status_code, "body": body}
    except requests.RequestException as e:
        return {"status": "ERROR", "body": {"error": str(e)}}

def classify_result(body: dict) -> str:
    """Classify the quality of the response."""
    if "error" in body:
        return "ERROR"
    reply = body.get("reply", "") or ""
    routing = body.get("routing", {}) or {}
    api_path = routing.get("api_path", "")
    db_result = body.get("db_result")

    if api_path == "/api/db/unsupported":
        return "UNSUPPORTED"
    if api_path == "/api/db/none":
        return "NO_DB"
    if "error" in reply.lower() or "Error" in reply:
        return "DB_ERROR"
    if db_result is not None:
        # Each API path has a different result shape — check the right key
        if api_path == "/api/db/balance/diff":
            return "ANSWERED" if db_result.get("ytd_from") is not None or db_result.get("ytd_to") is not None else "ZERO_BALANCE"
        if api_path == "/api/db/balance/trend":
            periods = db_result.get("periods") or []
            return "ANSWERED" if periods else "ZERO_BALANCE"
        if api_path == "/api/db/balance/highlights":
            accounts = db_result.get("top_accounts") or []
            return "ANSWERED" if accounts else "ZERO_BALANCE"
        if api_path == "/api/db/balance/explain":
            return "ANSWERED" if db_result.get("ytd_balance") is not None else "ZERO_BALANCE"
        if api_path == "/api/db/balance/diagnostics":
            return "ANSWERED" if "balance_row_exists" in db_result else "ZERO_BALANCE"
        if api_path == "/api/db/journal/details":
            return "ANSWERED"
        # by-account / by-ccid — ytd_balance can legitimately be 0 for parent accounts
        ytd = db_result.get("ytd_balance")
        if ytd is None:
            return "ZERO_BALANCE"
        return "ANSWERED"
    if "completed" in reply.lower() or "drilldown" in reply.lower():
        return "ANSWERED"
    if reply and len(reply) > 10:
        return "ANSWERED"
    return "UNKNOWN"


def run():
    questions = load_questions()
    results = []
    print(f"Running {len(questions)} questions against {BASE_URL}...\n")

    for q in questions:
        t0 = time.time()
        outcome = ask(q["question"])
        elapsed = round((time.time() - t0) * 1000)
        body = outcome["body"]
        status = outcome["status"]
        classification = classify_result(body)
        routing = body.get("routing", {}) or {}
        api_path = routing.get("api_path", "N/A")
        reply = (body.get("reply") or "")[:100]

        results.append({
            "intent": q["intent"],
            "question": q["question"],
            "status": status,
            "api_path": api_path,
            "classification": classification,
            "reply_excerpt": reply,
            "elapsed_ms": elapsed,
        })
        icon = "PASS" if classification == "ANSWERED" else ("WARN" if classification in ("ZERO_BALANCE", "NO_DB") else "FAIL")
        print(f"[{icon}] [{elapsed:>5}ms] {classification:<15} {api_path:<35} {q['question'][:70]}")

    # ---- Summary ----
    total = len(results)
    counts = {}
    for r in results:
        counts[r["classification"]] = counts.get(r["classification"], 0) + 1

    answered = counts.get("ANSWERED", 0)
    zero = counts.get("ZERO_BALANCE", 0)
    unsupported = counts.get("UNSUPPORTED", 0)
    no_db = counts.get("NO_DB", 0)
    errors = counts.get("ERROR", 0) + counts.get("DB_ERROR", 0)

    print("\n" + "=" * 70)
    print(f"  TOTAL QUESTIONS  : {total}")
    print(f"  PASS ANSWERED       : {answered} ({answered*100//total}%)")
    print(f"  WARN ZERO BALANCE   : {zero}  ({zero*100//total}%)")
    print(f"  WARN NO DB (general) : {no_db} ({no_db*100//total}%)")
    print(f"  FAIL UNSUPPORTED    : {unsupported} ({unsupported*100//total}%)")
    print(f"  FAIL ERRORS         : {errors}  ({errors*100//total}%)")
    print("=" * 70)
    
    # Write JSON report
    with open("test_report_full.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\nFull JSON report saved to test_report_full.json")

if __name__ == "__main__":
    run()
