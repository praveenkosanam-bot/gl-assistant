import json
import os
import re
import time
from typing import Any

import oracledb
import requests
from flask import Flask, jsonify, render_template, request


app = Flask(__name__)


def load_dotenv(path: str = ".env") -> None:
    if not os.path.exists(path):
        return

    with open(path, encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"

DB_CONFIG = {
    "user": os.getenv("DB_USER", "XXSBID_605"),
    "password": os.getenv("DB_PASSWORD", "XXSBID_605"),
    "host": os.getenv("DB_HOST", "192.168.8.127"),
    "port": int(os.getenv("DB_PORT", "1521")),
    "service_name": os.getenv("DB_SERVICE", "splashgl001"),
}

DB_POOL_MIN = int(os.getenv("DB_POOL_MIN", "1"))
DB_POOL_MAX = int(os.getenv("DB_POOL_MAX", "4"))
DB_POOL_INCREMENT = int(os.getenv("DB_POOL_INCREMENT", "1"))
MOCK_OPENAI = os.getenv("MOCK_OPENAI", "").lower() in {"1", "true", "yes"}

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

BALANCE_KEYWORDS = ("balance", "ccid", "account", "ledger", "period", "ytd", "activity")


DB_POOL = oracledb.create_pool(
    min=DB_POOL_MIN,
    max=DB_POOL_MAX,
    increment=DB_POOL_INCREMENT,
    **DB_CONFIG,
)


def get_db_connection():
    return DB_POOL.acquire()


def query_one(sql: str, params: dict[str, Any] | None = None):
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, params or {})
            return cursor.fetchone()


def call_balance_procedure(proc_name: str, args: list[Any]) -> tuple[Any, Any]:
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            out_number = cursor.var(oracledb.DB_TYPE_NUMBER)
            out_message = cursor.var(str)
            cursor.callproc(proc_name, [*args, out_number, out_message])
            return out_number.getvalue(), out_message.getvalue()


def extract_filters(message: str) -> dict[str, Any]:
    patterns = {
        "ledger_id": r"ledger(?:\s+id)?\s*(?:=|:)?\s*(\d+)",
        "period_name": r"\b([A-Z]{3}-\d{2}|\d{2}-\d{2})\b",
        "ccid": r"(?:ccid|code combination(?:\s+id)?)\s*(?:=|:)?\s*(\d+)",
        "account_number": r"(?:account(?:\s+number)?|acct)\s*(?:=|:)?\s*([A-Za-z0-9_-]+)",
        "actual_flag": r"actual\s+flag\s*(?:=|:)?\s*([ABE])\b",
    }

    results: dict[str, Any] = {}
    upper_message = message.upper()
    for key, pattern in patterns.items():
        match = re.search(pattern, upper_message if key in {"period_name", "actual_flag"} else message, re.IGNORECASE)
        if not match:
            continue
        value = match.group(1)
        if key in {"ledger_id", "ccid"}:
            results[key] = int(value)
        elif key in {"period_name", "actual_flag"}:
            results[key] = value.upper()
        else:
            results[key] = value

    return results


def seed_lookup(
    account_number: str | None = None,
    ccid: int | None = None,
    ledger_id: int | None = None,
    period_name: str | None = None,
    actual_flag: str | None = None,
):
    sql = """
        SELECT gb.ledger_id,
               gb.period_name,
               gb.code_combination_id,
               gb.actual_flag,
               gcc.segment3
          FROM gl_balances gb
          JOIN gl_code_combinations gcc
            ON gcc.code_combination_id = gb.code_combination_id
         WHERE gb.code_combination_id IS NOT NULL
           AND gcc.segment3 IS NOT NULL
           AND (:ledger_id IS NULL OR gb.ledger_id = :ledger_id)
           AND (:period_name IS NULL OR gb.period_name = :period_name)
           AND (:actual_flag IS NULL OR gb.actual_flag = :actual_flag)
           AND (:account_number IS NULL OR gcc.segment3 = :account_number)
           AND (:ccid IS NULL OR gb.code_combination_id = :ccid)
         FETCH FIRST 1 ROW ONLY
    """
    row = query_one(
        sql,
        {
            "account_number": account_number,
            "ccid": ccid,
            "ledger_id": ledger_id,
            "period_name": period_name,
            "actual_flag": actual_flag,
        },
    )
    if not row:
        return None
    return {
        "ledger_id": row[0],
        "period_name": row[1],
        "ccid": row[2],
        "actual_flag": row[3],
        "account_number": row[4],
    }


def build_balance_context(message: str) -> dict[str, Any] | None:
    if not any(keyword in message.lower() for keyword in BALANCE_KEYWORDS):
        return None

    original_filters = extract_filters(message)
    parsed = dict(original_filters)
    parsed.setdefault("actual_flag", "A")
    seed = None

    parsed["resolved_from_seed"] = bool(seed) and (
        ("ledger_id" not in original_filters)
        or ("period_name" not in original_filters)
        or ("actual_flag" not in original_filters and seed is not None)
    )

    required_fields = ("ledger_id", "period_name", "actual_flag")
    has_account = bool(parsed.get("account_number"))
    has_ccid = bool(parsed.get("ccid"))

    if has_ccid and any(field not in parsed for field in required_fields):
        seed = seed_lookup(
            ccid=parsed["ccid"],
            ledger_id=parsed.get("ledger_id"),
            period_name=parsed.get("period_name"),
            actual_flag=parsed.get("actual_flag"),
        )
        if seed:
            for key, value in seed.items():
                parsed.setdefault(key, value)
        parsed["resolved_from_seed"] = bool(seed) and (
            ("ledger_id" not in original_filters)
            or ("period_name" not in original_filters)
            or ("actual_flag" not in original_filters and seed is not None)
        )

    if has_account and any(field not in parsed for field in required_fields):
        seed = seed_lookup(
            account_number=parsed["account_number"],
            ledger_id=parsed.get("ledger_id"),
            period_name=parsed.get("period_name"),
            actual_flag=parsed.get("actual_flag"),
        )
        if seed:
            for key, value in seed.items():
                parsed.setdefault(key, value)
        parsed["resolved_from_seed"] = bool(seed) and (
            ("ledger_id" not in original_filters)
            or ("period_name" not in original_filters)
            or ("actual_flag" not in original_filters and seed is not None)
        )

    if has_ccid and any(field not in parsed for field in required_fields):
        parsed["lookup_type"] = "ccid"
        parsed["status_msg"] = "Missing ledger, period, or actual flag for the CCID lookup."
        return parsed

    if has_account and any(field not in parsed for field in required_fields):
        parsed["lookup_type"] = "account_number"
        parsed["status_msg"] = "Missing ledger, period, or actual flag for the account lookup."
        return parsed

    if has_ccid:
        ytd, ytd_msg = call_balance_procedure(
            "GLCAI_PKG_BAL.get_ytd_balance_by_ccid",
            [parsed["ledger_id"], parsed["period_name"], parsed["ccid"], parsed.get("actual_flag", "A")],
        )
        period_activity, activity_msg = call_balance_procedure(
            "GLCAI_PKG_BAL.get_period_activity_by_ccid",
            [parsed["ledger_id"], parsed["period_name"], parsed["ccid"], parsed.get("actual_flag", "A")],
        )
        parsed.update(
            {
                "lookup_type": "ccid",
                "ytd_balance": float(ytd) if ytd is not None else None,
                "period_activity": float(period_activity) if period_activity is not None else None,
                "status_msg": ytd_msg or activity_msg,
            }
        )
        return parsed

    if has_account:
        ytd, ytd_msg = call_balance_procedure(
            "GLCAI_PKG_BAL.get_ytd_balance_by_account",
            [parsed["ledger_id"], parsed["period_name"], parsed["account_number"], parsed.get("actual_flag", "A")],
        )
        period_activity, activity_msg = call_balance_procedure(
            "GLCAI_PKG_BAL.get_period_activity_by_account",
            [parsed["ledger_id"], parsed["period_name"], parsed["account_number"], parsed.get("actual_flag", "A")],
        )
        parsed.update(
            {
                "lookup_type": "account_number",
                "ytd_balance": float(ytd) if ytd is not None else None,
                "period_activity": float(period_activity) if period_activity is not None else None,
                "status_msg": ytd_msg or activity_msg,
            }
        )
        return parsed

    seed = seed_lookup(
        ledger_id=parsed.get("ledger_id"),
        period_name=parsed.get("period_name"),
        actual_flag=parsed.get("actual_flag"),
    )
    if seed:
        seed["lookup_type"] = "seed_only"
        seed["resolved_from_seed"] = True
        seed["status_msg"] = "Seeded a live row from the database. Ask with ledger, period, and account or CCID for a precise balance lookup."
        return seed

    return {"lookup_type": "none", "status_msg": "No matching live balance row was found."}


def extract_output_text(payload: dict[str, Any]) -> str:
    direct_text = payload.get("output_text")
    if direct_text:
        return direct_text

    texts: list[str] = []
    for item in payload.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"}:
                if isinstance(content.get("text"), str):
                    texts.append(content["text"])
                elif isinstance(content.get("text"), dict):
                    text_value = content["text"].get("value")
                    if text_value:
                        texts.append(text_value)
    return "\n".join(part for part in texts if part).strip()


def call_openai(history: list[dict[str, str]], balance_context: dict[str, Any] | None) -> str:
    if MOCK_OPENAI:
        latest_user = next((item["content"] for item in reversed(history) if item.get("role") == "user"), "")
        return f"Mocked assistant reply for: {latest_user}"

    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set.")

    transcript = []
    for item in history[-8:]:
        role = item.get("role", "user")
        content = item.get("content", "").strip()
        if content:
            transcript.append(f"{role.title()}: {content}")

    prompt = "\n".join(transcript)
    if balance_context:
        prompt += "\n\nLive balance context:\n" + json.dumps(balance_context, indent=2)

    response = requests.post(
        OPENAI_RESPONSES_URL,
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": OPENAI_MODEL,
            "instructions": SYSTEM_PROMPT,
            "input": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": prompt,
                        }
                    ],
                }
            ],
        },
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    text = extract_output_text(payload)
    if not text:
        raise RuntimeError("OpenAI response did not contain text output.")
    return text


@app.get("/")
def index():
    return render_template("index.html", model=OPENAI_MODEL)


@app.get("/api/health")
def health():
    db_ok = False
    db_error = None
    try:
        row = query_one("SELECT 1 FROM dual")
        db_ok = bool(row)
    except Exception as exc:  # pragma: no cover - diagnostic path
        db_error = str(exc)

    return jsonify(
        {
            "openai_configured": bool(OPENAI_API_KEY),
            "openai_model": OPENAI_MODEL,
            "db_connected": db_ok,
            "db_error": db_error,
        }
    )


@app.post("/api/chat")
def chat():
    payload = request.get_json(silent=True) or {}
    message = (payload.get("message") or "").strip()
    history = payload.get("history") or []
    if not message:
        return jsonify({"error": "Message is required."}), 400

    full_history = [*history, {"role": "user", "content": message}]

    timings: dict[str, float] = {}

    try:
        started = time.perf_counter()
        balance_context = build_balance_context(message)
        timings["balance_lookup_ms"] = round((time.perf_counter() - started) * 1000, 1)
    except Exception as exc:
        return jsonify({"error": f"Balance lookup failed: {exc}"}), 500

    try:
        started = time.perf_counter()
        reply = call_openai(full_history, balance_context)
        timings["openai_ms"] = round((time.perf_counter() - started) * 1000, 1)
    except requests.HTTPError as exc:
        detail = exc.response.text if exc.response is not None else str(exc)
        return jsonify({"error": f"OpenAI request failed: {detail}"}), 502
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    return jsonify({"reply": reply, "balance_context": balance_context, "timings": timings})


if __name__ == "__main__":
    app.run(
        host=os.getenv("FLASK_HOST", "127.0.0.1"),
        port=int(os.getenv("FLASK_PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "").lower() in {"1", "true", "yes"},
    )
