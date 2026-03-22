import json
import os
import re
import time
from pathlib import Path
from typing import Any

import oracledb
import requests
import yaml
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
            cleaned = value.strip()
            if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {'"', "'"}:
                cleaned = cleaned[1:-1]
            os.environ.setdefault(key.strip(), cleaned)


load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_LEDGER_NAME = os.getenv("DEFAULT_LEDGER_NAME", "US Primary Ledger")
DEFAULT_LEDGER_ID = int(os.getenv("DEFAULT_LEDGER_ID", "300000046975971"))
DEFAULT_CURRENCY_SYMBOL = os.getenv("DEFAULT_CURRENCY_SYMBOL", "$")

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
RASA_URL = os.getenv("RASA_URL", "").rstrip("/")
QUESTION_INVENTORY_PATH = Path(os.getenv("QUESTION_INVENTORY_PATH", "robot/tests/glcai_questions.yaml"))

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
MONTH_MAP = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
    "ADJ": 13,
}
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
        "period_from": r"(?:between|from)\s+([A-Z]{3}-\d{2}|\d{2}-\d{2})\s+(?:and|to|vs\.?|versus)\s+([A-Z]{3}-\d{2}|\d{2}-\d{2})",
        "last_n": r"last\s+(\d+)\s+(?:periods|months)",
    }

    results: dict[str, Any] = {}
    upper_message = message.upper()
    period_range_match = re.search(patterns["period_from"], upper_message, re.IGNORECASE)
    if period_range_match:
        results["period_from"] = period_range_match.group(1).upper()
        results["period_to"] = period_range_match.group(2).upper()
    else:
        inline_periods = re.findall(r"\b(?:[A-Z]{3}-\d{2}|\d{2}-\d{2})\b", upper_message)
        if (" VS " in upper_message or " VERSUS " in upper_message) and len(inline_periods) >= 2:
            results["period_from"] = inline_periods[0].upper()
            results["period_to"] = inline_periods[1].upper()

    last_n_match = re.search(patterns["last_n"], message, re.IGNORECASE)
    if last_n_match:
        results["n"] = int(last_n_match.group(1))

    for key, pattern in patterns.items():
        if key in {"period_from", "last_n"}:
            continue
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

    if "account_number" not in results:
        seg_match = re.search(r"\b\d{2}[.\-]\d{3}[.\-](\d{4,6})\b", message)
        if seg_match:
            results["account_number"] = seg_match.group(1)
    if "account_number" not in results and "ccid" not in results:
        lower_message = message.lower()
        if any(token in lower_message for token in ("balance", "account", "period", "ytd", "activity")):
            bare_number_match = re.search(r"\b(\d{4,6})\b", message)
            if bare_number_match:
                results["account_number"] = bare_number_match.group(1)

    return results


def normalize_period(period_name: str | None) -> str | None:
    return period_name.upper() if period_name else None


def period_sort_key(period_name: str) -> tuple[int, int, str]:
    text = period_name.strip().upper()
    if re.fullmatch(r"\d{2}-\d{2}", text):
        month = int(text[:2])
        year = 2000 + int(text[-2:])
        return (year, month, text)

    match = re.fullmatch(r"([A-Z]{3})-(\d{2})", text)
    if match:
        month = MONTH_MAP.get(match.group(1), 99)
        year = 2000 + int(match.group(2))
        return (year, month, text)

    return (0, 0, text)


def query_all(sql: str, params: dict[str, Any] | None = None):
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, params or {})
            return cursor.fetchall()


def load_question_inventory() -> list[dict[str, Any]]:
    if not QUESTION_INVENTORY_PATH.exists():
        return []
    data = yaml.safe_load(QUESTION_INVENTORY_PATH.read_text(encoding="utf-8")) or {}
    return data.get("intents", [])


QUESTION_INVENTORY = load_question_inventory()


def tokenize(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) > 1}


def parse_question_local(question: str) -> dict[str, Any]:
    entities = extract_filters(question)
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
        if utterance_scores:
            score += max(utterance_scores) * 0.75
        if description_tokens:
            score += (len(question_tokens & description_tokens) / len(description_tokens)) * 0.25

        entity_names = set(intent.get("entities", []))
        entity_bonus = len(entity_names & set(entities.keys())) * 0.08
        score += entity_bonus

        if "ccid" in entity_names and entities.get("ccid") is not None:
            score += 0.2
        if "account" in entity_names and entities.get("account_number") is not None:
            score += 0.2
        if "period_from" in entity_names and entities.get("period_from") is not None:
            score += 0.2
        if intent["name"].startswith("journals.") and "journal" in question.lower():
            score += 0.25

        if score > best_score:
            best_score = score
            best_intent = intent["name"]

    if not best_intent:
        best_intent = "balance.high_level" if any(token in question.lower() for token in BALANCE_KEYWORDS) else "balance.high_level"

    return {
        "intent": best_intent,
        "confidence": round(best_score, 4),
        "entities": entities,
        "source": "lightweight",
    }


def parse_question_with_rasa(question: str) -> dict[str, Any] | None:
    if not RASA_URL:
        return None
    session = requests.Session()
    session.trust_env = False
    response = session.post(f"{RASA_URL}/model/parse", json={"text": question}, timeout=10)
    response.raise_for_status()
    payload = response.json()
    entities = extract_filters(question)
    for entity in payload.get("entities", []):
        name = entity.get("entity")
        value = entity.get("value")
        if name in {"ledger_id", "ccid", "n"} and value is not None:
            try:
                entities[name] = int(value)
            except (TypeError, ValueError):
                entities[name] = value
        elif name == "account":
            entities["account_number"] = str(value)
        elif name == "period":
            entities["period_name"] = str(value).upper()
        elif name == "period_from":
            entities["period_from"] = str(value).upper()
        elif name == "period_to":
            entities["period_to"] = str(value).upper()
        elif name and value is not None:
            entities[name] = value

    return {
        "intent": (payload.get("intent") or {}).get("name"),
        "confidence": (payload.get("intent") or {}).get("confidence", 0.0),
        "entities": entities,
        "source": "rasa",
    }


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


def complete_lookup_params(question: str, params: dict[str, Any]) -> dict[str, Any]:
    completed = extract_filters(question) if question else {}
    completed.update(params)
    completed.setdefault("actual_flag", "A")
    completed.setdefault("ledger_id", DEFAULT_LEDGER_ID)
    if completed.get("period_name"):
        completed["period_name"] = normalize_period(completed["period_name"])
    if completed.get("period_from"):
        completed["period_from"] = normalize_period(completed["period_from"])
    if completed.get("period_to"):
        completed["period_to"] = normalize_period(completed["period_to"])

    requires_seed = any(
        completed.get(key) is not None for key in ("ccid", "account_number")
    ) and any(
        completed.get(key) is None for key in ("ledger_id", "period_name")
    )
    if requires_seed:
        seed = seed_lookup(
            account_number=completed.get("account_number"),
            ccid=completed.get("ccid"),
            ledger_id=completed.get("ledger_id"),
            period_name=completed.get("period_name"),
            actual_flag=completed.get("actual_flag"),
        )
        if seed:
            for key, value in seed.items():
                completed.setdefault(key, value)
            completed["resolved_from_seed"] = True
    else:
        completed["resolved_from_seed"] = False

    return completed


def validate_route_params(api_path: str, params: dict[str, Any]) -> str | None:
    required_fields: dict[str, tuple[str, ...]] = {
        "/api/db/balance/by-ccid": ("ledger_id", "period_name", "ccid"),
        "/api/db/balance/by-account": ("ledger_id", "period_name", "account_number"),
        "/api/db/balance/diff": ("ledger_id", "period_from", "period_to"),
        "/api/db/balance/trend": ("ledger_id",),
        "/api/db/balance/explain": ("ledger_id", "period_name"),
        "/api/db/balance/highlights": ("ledger_id", "period_name"),
        "/api/db/balance/diagnostics": (),
    }

    required = required_fields.get(api_path)
    if required is None:
        return None

    missing = [field for field in required if params.get(field) is None]
    if api_path in {"/api/db/balance/diff", "/api/db/balance/explain"}:
        if params.get("ccid") is None and params.get("account_number") is None:
            missing.append("ccid or account_number")
    if api_path == "/api/db/balance/diagnostics":
        if params.get("ledger_id") is None:
            missing.append("ledger_id")
        if params.get("period_name") is None:
            missing.append("period_name")
        if params.get("ccid") is None and params.get("account_number") is None:
            missing.append("ccid or account_number")

    if not missing:
        return None
    return "Missing required query inputs: " + ", ".join(missing)


def get_account_for_ccid(ccid: int) -> str | None:
    row = query_one(
        """
        SELECT gcc.segment3
          FROM gl_code_combinations gcc
         WHERE gcc.code_combination_id = :ccid
        """,
        {"ccid": ccid},
    )
    return row[0] if row else None


def get_ledger_name(ledger_id: int | None) -> str | None:
    if ledger_id is None:
        return None
    if ledger_id == DEFAULT_LEDGER_ID:
        return DEFAULT_LEDGER_NAME
    row = query_one(
        """
        SELECT name
          FROM gl_ledgers
         WHERE ledger_id = :ledger_id
        """,
        {"ledger_id": ledger_id},
    )
    return row[0] if row else str(ledger_id)


def format_currency(amount: Any, currency_symbol: str = DEFAULT_CURRENCY_SYMBOL) -> str:
    if amount is None:
        return "N/A"
    value = float(amount)
    formatted = f"{abs(value):,.2f}"
    if value < 0:
        return f"-{currency_symbol}{formatted}"
    return f"{currency_symbol}{formatted}"


def annotate_ledger_metadata(result: dict[str, Any]) -> dict[str, Any]:
    ledger_id = result.get("ledger_id")
    if ledger_id is None:
        return result
    enriched = dict(result)
    enriched["ledger_name"] = get_ledger_name(ledger_id)
    return enriched


def db_balance_by_ccid(params: dict[str, Any]) -> dict[str, Any]:
    ytd, ytd_msg = call_balance_procedure(
        "GLCAI_PKG_BAL.get_ytd_balance_by_ccid",
        [params["ledger_id"], params["period_name"], params["ccid"], params.get("actual_flag", "A")],
    )
    period_activity, activity_msg = call_balance_procedure(
        "GLCAI_PKG_BAL.get_period_activity_by_ccid",
        [params["ledger_id"], params["period_name"], params["ccid"], params.get("actual_flag", "A")],
    )
    return {
        "lookup_type": "ccid",
        "ledger_id": params["ledger_id"],
        "period_name": params["period_name"],
        "ccid": params["ccid"],
        "account_number": get_account_for_ccid(params["ccid"]),
        "actual_flag": params.get("actual_flag", "A"),
        "ytd_balance": float(ytd) if ytd is not None else None,
        "period_activity": float(period_activity) if period_activity is not None else None,
        "status_msg": ytd_msg or activity_msg,
        "resolved_from_seed": params.get("resolved_from_seed", False),
    }


def db_balance_by_account(params: dict[str, Any]) -> dict[str, Any]:
    ytd, ytd_msg = call_balance_procedure(
        "GLCAI_PKG_BAL.get_ytd_balance_by_account",
        [params["ledger_id"], params["period_name"], params["account_number"], params.get("actual_flag", "A")],
    )
    period_activity, activity_msg = call_balance_procedure(
        "GLCAI_PKG_BAL.get_period_activity_by_account",
        [params["ledger_id"], params["period_name"], params["account_number"], params.get("actual_flag", "A")],
    )
    seed = seed_lookup(
        account_number=params["account_number"],
        ledger_id=params["ledger_id"],
        period_name=params["period_name"],
        actual_flag=params.get("actual_flag", "A"),
    )
    return {
        "lookup_type": "account_number",
        "ledger_id": params["ledger_id"],
        "period_name": params["period_name"],
        "account_number": params["account_number"],
        "ccid": seed["ccid"] if seed else None,
        "actual_flag": params.get("actual_flag", "A"),
        "ytd_balance": float(ytd) if ytd is not None else None,
        "period_activity": float(period_activity) if period_activity is not None else None,
        "status_msg": ytd_msg or activity_msg,
        "resolved_from_seed": params.get("resolved_from_seed", False),
    }


def db_balance_explain(params: dict[str, Any]) -> dict[str, Any]:
    where_filter = [
        "gb.ledger_id = :ledger_id",
        "gb.period_name = :period_name",
        "gb.actual_flag = :actual_flag",
    ]
    bind = {
        "ledger_id": params["ledger_id"],
        "period_name": params["period_name"],
        "actual_flag": params.get("actual_flag", "A"),
    }
    if params.get("ccid") is not None:
        where_filter.append("gb.code_combination_id = :ccid")
        bind["ccid"] = params["ccid"]
    else:
        where_filter.append("gcc.segment3 = :account_number")
        bind["account_number"] = params["account_number"]

    row = query_one(
        f"""
        SELECT SUM(NVL(gb.begin_balance_dr,0)),
               SUM(NVL(gb.begin_balance_cr,0)),
               SUM(NVL(gb.period_net_dr,0)),
               SUM(NVL(gb.period_net_cr,0))
          FROM gl_balances gb
          JOIN gl_code_combinations gcc
            ON gcc.code_combination_id = gb.code_combination_id
         WHERE {' AND '.join(where_filter)}
        """,
        bind,
    )
    begin_dr, begin_cr, net_dr, net_cr = row
    ytd = (begin_dr or 0) - (begin_cr or 0) + (net_dr or 0) - (net_cr or 0)
    return {
        "ledger_id": params["ledger_id"],
        "period_name": params["period_name"],
        "actual_flag": params.get("actual_flag", "A"),
        "ccid": params.get("ccid"),
        "account_number": params.get("account_number"),
        "begin_balance_dr": float(begin_dr or 0),
        "begin_balance_cr": float(begin_cr or 0),
        "period_net_dr": float(net_dr or 0),
        "period_net_cr": float(net_cr or 0),
        "ytd_balance": float(ytd),
        "resolved_from_seed": params.get("resolved_from_seed", False),
    }


def db_balance_diff(params: dict[str, Any]) -> dict[str, Any]:
    base_params = {
        "ledger_id": params["ledger_id"],
        "actual_flag": params.get("actual_flag", "A"),
        "resolved_from_seed": params.get("resolved_from_seed", False),
    }
    if params.get("ccid") is not None:
        before = db_balance_by_ccid({**base_params, "period_name": params["period_from"], "ccid": params["ccid"]})
        after = db_balance_by_ccid({**base_params, "period_name": params["period_to"], "ccid": params["ccid"]})
        identifier = {"ccid": params["ccid"], "account_number": before.get("account_number")}
    else:
        before = db_balance_by_account(
            {**base_params, "period_name": params["period_from"], "account_number": params["account_number"]}
        )
        after = db_balance_by_account(
            {**base_params, "period_name": params["period_to"], "account_number": params["account_number"]}
        )
        identifier = {"account_number": params["account_number"], "ccid": after.get("ccid")}

    return {
        **identifier,
        "ledger_id": params["ledger_id"],
        "actual_flag": params.get("actual_flag", "A"),
        "period_from": params["period_from"],
        "period_to": params["period_to"],
        "ytd_from": before.get("ytd_balance"),
        "ytd_to": after.get("ytd_balance"),
        "period_activity_from": before.get("period_activity"),
        "period_activity_to": after.get("period_activity"),
        "ytd_delta": (after.get("ytd_balance") or 0) - (before.get("ytd_balance") or 0),
        "period_activity_delta": (after.get("period_activity") or 0) - (before.get("period_activity") or 0),
        "resolved_from_seed": params.get("resolved_from_seed", False),
    }


def db_balance_trend(params: dict[str, Any]) -> dict[str, Any]:
    bind = {"ledger_id": params["ledger_id"], "actual_flag": params.get("actual_flag", "A")}
    if params.get("ccid") is not None:
        rows = query_all(
            """
            SELECT gb.period_name,
                   SUM(NVL(gb.begin_balance_dr,0) - NVL(gb.begin_balance_cr,0)
                     + NVL(gb.period_net_dr,0) - NVL(gb.period_net_cr,0)) AS ytd_balance,
                   SUM(NVL(gb.period_net_dr,0) - NVL(gb.period_net_cr,0)) AS period_activity
              FROM gl_balances gb
             WHERE gb.ledger_id = :ledger_id
               AND gb.actual_flag = :actual_flag
               AND gb.code_combination_id = :ccid
             GROUP BY gb.period_name
            """,
            {**bind, "ccid": params["ccid"]},
        )
    else:
        rows = query_all(
            """
            WITH target_ccids AS (
                SELECT code_combination_id
                  FROM gl_code_combinations
                 WHERE segment3 = :account_number
            )
            SELECT gb.period_name,
                   SUM(NVL(gb.begin_balance_dr,0) - NVL(gb.begin_balance_cr,0)
                     + NVL(gb.period_net_dr,0) - NVL(gb.period_net_cr,0)) AS ytd_balance,
                   SUM(NVL(gb.period_net_dr,0) - NVL(gb.period_net_cr,0)) AS period_activity
              FROM gl_balances gb
              JOIN target_ccids tc
                ON tc.code_combination_id = gb.code_combination_id
             WHERE gb.ledger_id = :ledger_id
               AND gb.actual_flag = :actual_flag
             GROUP BY gb.period_name
            """,
            {**bind, "account_number": params["account_number"]},
        )
    sorted_rows = sorted(rows, key=lambda item: period_sort_key(item[0]))
    if params.get("period_name"):
        cutoff = normalize_period(params["period_name"])
        sorted_rows = [row for row in sorted_rows if period_sort_key(row[0]) <= period_sort_key(cutoff)]
    n = int(params.get("n") or 5)
    selected = sorted_rows[-n:]
    return {
        "ledger_id": params["ledger_id"],
        "ccid": params.get("ccid"),
        "account_number": params.get("account_number"),
        "actual_flag": params.get("actual_flag", "A"),
        "periods": [
            {
                "period_name": row[0],
                "ytd_balance": float(row[1] or 0),
                "period_activity": float(row[2] or 0),
            }
            for row in selected
        ],
        "resolved_from_seed": params.get("resolved_from_seed", False),
    }


def db_balance_highlights(params: dict[str, Any]) -> dict[str, Any]:
    limit = int(params.get("limit") or 5)
    rows = query_all(
        """
        SELECT gcc.segment3 AS account_number,
               SUM(NVL(gb.begin_balance_dr,0) - NVL(gb.begin_balance_cr,0)
                 + NVL(gb.period_net_dr,0) - NVL(gb.period_net_cr,0)) AS ytd_balance
          FROM gl_balances gb
          JOIN gl_code_combinations gcc
            ON gcc.code_combination_id = gb.code_combination_id
         WHERE gb.ledger_id = :ledger_id
           AND gb.period_name = :period_name
           AND gb.actual_flag = :actual_flag
           AND gcc.segment3 IS NOT NULL
         GROUP BY gcc.segment3
         ORDER BY ABS(SUM(NVL(gb.begin_balance_dr,0) - NVL(gb.begin_balance_cr,0)
                        + NVL(gb.period_net_dr,0) - NVL(gb.period_net_cr,0))) DESC
         FETCH FIRST :limit ROWS ONLY
        """,
        {
            "ledger_id": params["ledger_id"],
            "period_name": params["period_name"],
            "actual_flag": params.get("actual_flag", "A"),
            "limit": limit,
        },
    )
    return {
        "ledger_id": params["ledger_id"],
        "period_name": params["period_name"],
        "actual_flag": params.get("actual_flag", "A"),
        "top_accounts": [{"account_number": row[0], "ytd_balance": float(row[1] or 0)} for row in rows],
    }


def db_balance_diagnostics(params: dict[str, Any]) -> dict[str, Any]:
    result = {
        "ledger_id": params.get("ledger_id"),
        "period_name": params.get("period_name"),
        "actual_flag": params.get("actual_flag", "A"),
        "ccid": params.get("ccid"),
        "account_number": params.get("account_number"),
    }
    if params.get("ccid") is not None:
        result["ccid_exists"] = bool(query_one("SELECT 1 FROM gl_code_combinations WHERE code_combination_id = :ccid", {"ccid": params["ccid"]}))
        result["balance_row_exists"] = bool(
            query_one(
                "SELECT 1 FROM gl_balances WHERE ledger_id = :ledger_id AND period_name = :period_name AND code_combination_id = :ccid AND actual_flag = :actual_flag FETCH FIRST 1 ROW ONLY",
                {
                    "ledger_id": params["ledger_id"],
                    "period_name": params["period_name"],
                    "ccid": params["ccid"],
                    "actual_flag": params.get("actual_flag", "A"),
                },
            )
        )
    elif params.get("account_number") is not None:
        result["account_exists"] = bool(
            query_one("SELECT 1 FROM gl_code_combinations WHERE segment3 = :account FETCH FIRST 1 ROW ONLY", {"account": params["account_number"]})
        )
        result["balance_row_exists"] = bool(
            query_one(
                """
                SELECT 1
                  FROM gl_balances gb
                  JOIN gl_code_combinations gcc
                    ON gcc.code_combination_id = gb.code_combination_id
                 WHERE gb.ledger_id = :ledger_id
                   AND gb.period_name = :period_name
                   AND gb.actual_flag = :actual_flag
                   AND gcc.segment3 = :account
                 FETCH FIRST 1 ROW ONLY
                """,
                {
                    "ledger_id": params["ledger_id"],
                    "period_name": params["period_name"],
                    "actual_flag": params.get("actual_flag", "A"),
                    "account": params["account_number"],
                },
            )
        )
    return result


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


def resolve_question_rule_based(question: str) -> dict[str, Any]:
    parsed = parse_question_local(question)
    params = complete_lookup_params(question, parsed["entities"])
    api_path = INTENT_API_MAP.get(parsed["intent"], "/api/db/balance/highlights")
    lower_question = question.lower()

    if "how do i call" in lower_question or "/api/" in lower_question or "javascript" in lower_question:
        api_path = "/api/db/none"
        params = {}

    if api_path == "/api/db/balance/by-account" and params.get("account_number") is None and params.get("ccid") is not None:
        api_path = "/api/db/balance/by-ccid"
    if api_path == "/api/db/balance/by-ccid" and params.get("ccid") is None and params.get("account_number") is not None:
        api_path = "/api/db/balance/by-account"
    if api_path == "/api/db/balance/highlights":
        params.setdefault("limit", 5)

    return {
        "api_path": api_path,
        "params": params,
        "intent": parsed["intent"],
        "intent_confidence": parsed["confidence"],
        "parser_source": parsed["source"],
    }

    params = complete_lookup_params(question, extract_filters(question))
    text = question.lower()

    if "source" in text or "journals" in text or "payables" in text or "posted journals" in text:
        return {
            "api_path": "/api/db/unsupported",
            "params": params,
            "reason": "Journal endpoints are not implemented yet.",
        }

    if "how do i call" in text or "/api/" in text or "javascript" in text or "api" in text:
        return {"api_path": "/api/db/none", "params": {}, "reason": "This is an API usage question, not a DB query."}

    if "trend" in text or "last " in text or "history" in text or "trended" in text:
        return {"api_path": "/api/db/balance/trend", "params": params}

    if "compare" in text or "changed between" in text or "month-on-month" in text or "Δ" in question or "delta" in text:
        return {"api_path": "/api/db/balance/diff", "params": params}

    if "explain" in text or "break down" in text or "breakdown" in text or "debit/credit" in text:
        return {"api_path": "/api/db/balance/explain", "params": params}

    if "why" in text or "zero" in text or "null" in text or "exist" in text or "open for this ledger" in text:
        return {"api_path": "/api/db/balance/diagnostics", "params": params}

    if "high balances" in text or "changed the most" in text or "unusual" in text or "what does our gl look like" in text:
        params.setdefault("limit", 5)
        return {"api_path": "/api/db/balance/highlights", "params": params}

    if params.get("ccid") is not None:
        return {"api_path": "/api/db/balance/by-ccid", "params": params}

    if params.get("account_number") is not None:
        return {"api_path": "/api/db/balance/by-account", "params": params}

    return {"api_path": "/api/db/balance/highlights", "params": params}


def resolve_question_with_llm(history: list[dict[str, str]], question: str) -> dict[str, Any]:
    if MOCK_OPENAI:
        return resolve_question_rule_based(question)

    if not OPENAI_API_KEY:
        return resolve_question_rule_based(question)

    try:
        rasa_result = parse_question_with_rasa(question)
    except requests.RequestException:
        rasa_result = None

    if rasa_result and rasa_result.get("intent") in INTENT_API_MAP:
        routed = {
            "api_path": INTENT_API_MAP[rasa_result["intent"]],
            "params": complete_lookup_params(question, rasa_result["entities"]),
            "intent": rasa_result["intent"],
            "intent_confidence": rasa_result["confidence"],
            "parser_source": rasa_result["source"],
            "routing_mode": "rasa",
        }
        if routed["api_path"] == "/api/db/balance/highlights":
            routed["params"].setdefault("limit", 5)
        return routed

    transcript = []
    for item in history[-8:]:
        role = item.get("role", "user")
        content = item.get("content", "").strip()
        if content:
            transcript.append(f"{role.title()}: {content}")

    prompt = "\n".join(transcript)
    prompt += f"\n\nLatest user question: {question}"
    prompt += """

Return only JSON with this shape:
{"api_path":"...","params":{...}}

Allowed api_path values:
- /api/db/balance/by-ccid
- /api/db/balance/by-account
- /api/db/balance/diff
- /api/db/balance/trend
- /api/db/balance/explain
- /api/db/balance/highlights
- /api/db/balance/diagnostics
- /api/db/none
- /api/db/unsupported

Rules:
- Use only the allowed api_path values.
- If the question is about balances for a CCID, route to by-ccid.
- If the question is about balances for an account number, route to by-account.
- If the question asks to compare two periods, use diff.
- If it asks for history or last N periods, use trend.
- If it asks to explain a calculation, use explain.
- If it asks why a result is null/zero or whether a CCID exists, use diagnostics.
- If it asks for high-level GL balance highlights, use highlights.
- If it is an API usage question, use /api/db/none.
- If it asks about journals, use /api/db/unsupported.
- Extract only params that are present or safely inferable.
- Default actual_flag to A when omitted.
"""

    session = requests.Session()
    session.trust_env = False
    try:
        response = session.post(
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
            raise RuntimeError("OpenAI response did not contain routing output.")
        try:
            routed = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if not match:
                raise RuntimeError(f"OpenAI route output was not valid JSON: {text}")
            routed = json.loads(match.group(0))

        if routed.get("api_path") not in SUPPORTED_API_PATHS | {"/api/db/none", "/api/db/unsupported"}:
            raise RuntimeError(f"OpenAI returned unsupported api path: {routed.get('api_path')}")

        routed["params"] = complete_lookup_params(question, routed.get("params") or {})
        routed["routing_mode"] = "openai"
        return routed
    except (requests.RequestException, RuntimeError, json.JSONDecodeError):
        routed = resolve_question_rule_based(question)
        routed["routing_mode"] = "rule_based_fallback"
        return routed


def dispatch_db_api(api_path: str, params: dict[str, Any]) -> dict[str, Any]:
    if api_path == "/api/db/balance/by-ccid":
        return annotate_ledger_metadata(db_balance_by_ccid(params))
    if api_path == "/api/db/balance/by-account":
        return annotate_ledger_metadata(db_balance_by_account(params))
    if api_path == "/api/db/balance/diff":
        return annotate_ledger_metadata(db_balance_diff(params))
    if api_path == "/api/db/balance/trend":
        return annotate_ledger_metadata(db_balance_trend(params))
    if api_path == "/api/db/balance/explain":
        return annotate_ledger_metadata(db_balance_explain(params))
    if api_path == "/api/db/balance/highlights":
        return annotate_ledger_metadata(db_balance_highlights(params))
    if api_path == "/api/db/balance/diagnostics":
        return annotate_ledger_metadata(db_balance_diagnostics(params))
    if api_path == "/api/db/none":
        return {"message": "This question does not require a database query."}
    if api_path == "/api/db/unsupported":
        return {"message": "This question maps to a database area that is not implemented yet."}
    raise KeyError(api_path)


def format_chat_reply(api_path: str, result: dict[str, Any]) -> str:
    ledger_label = result.get("ledger_name") or (get_ledger_name(result.get("ledger_id")) if "ledger_id" in result else None)
    if api_path == "/api/db/balance/by-account":
        return (
            f"Account {result['account_number']} in {ledger_label} for {result['period_name']} "
            f"has YTD balance {format_currency(result['ytd_balance'])} and period activity {format_currency(result['period_activity'])}."
        )
    if api_path == "/api/db/balance/by-ccid":
        return (
            f"CCID {result['ccid']} in {ledger_label} for {result['period_name']} "
            f"has YTD balance {format_currency(result['ytd_balance'])} and period activity {format_currency(result['period_activity'])}."
        )
    if api_path == "/api/db/balance/diff":
        identifier = f"account {result['account_number']}" if result.get("account_number") else f"CCID {result['ccid']}"
        return (
            f"For {identifier}, YTD changed by {format_currency(result['ytd_delta'])} between {result['period_from']} and {result['period_to']}. "
            f"Period activity changed by {format_currency(result['period_activity_delta'])}."
        )
    if api_path == "/api/db/balance/trend":
        parts = [f"{item['period_name']}: {format_currency(item['ytd_balance'])}" for item in result["periods"]]
        return "Trend: " + "; ".join(parts)
    if api_path == "/api/db/balance/explain":
        return (
            f"YTD {format_currency(result['ytd_balance'])} = begin DR {format_currency(result['begin_balance_dr'])} - begin CR {format_currency(result['begin_balance_cr'])} "
            f"+ period DR {format_currency(result['period_net_dr'])} - period CR {format_currency(result['period_net_cr'])}."
        )
    if api_path == "/api/db/balance/highlights":
        highlights = ", ".join(
            f"{item['account_number']} ({format_currency(item['ytd_balance'])})" for item in result.get("top_accounts", [])
        )
        return f"Top balance accounts for {result['period_name']}: {highlights}"
    if api_path == "/api/db/balance/diagnostics":
        return json.dumps(result)
    return result.get("message", "No database result was needed.")


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
            "mock_openai": MOCK_OPENAI,
            "rasa_configured": bool(RASA_URL),
            "question_inventory_loaded": bool(QUESTION_INVENTORY),
        }
    )


@app.post("/api/nlu/parse")
def api_nlu_parse():
    payload = request.get_json(silent=True) or {}
    message = (payload.get("message") or "").strip()
    if not message:
        return jsonify({"error": "Message is required."}), 400

    rasa_result = None
    if RASA_URL:
        try:
            rasa_result = parse_question_with_rasa(message)
        except requests.RequestException as exc:
            rasa_result = {"error": str(exc), "source": "rasa"}

    lightweight = parse_question_local(message)
    routed = resolve_question_rule_based(message)
    return jsonify({"rasa": rasa_result, "lightweight": lightweight, "routing": routed})


@app.post("/api/db/balance/by-ccid")
def api_balance_by_ccid():
    params = complete_lookup_params("", request.get_json(silent=True) or {})
    return jsonify(db_balance_by_ccid(params))


@app.post("/api/db/balance/by-account")
def api_balance_by_account():
    params = complete_lookup_params("", request.get_json(silent=True) or {})
    return jsonify(db_balance_by_account(params))


@app.post("/api/db/balance/diff")
def api_balance_diff():
    params = complete_lookup_params("", request.get_json(silent=True) or {})
    return jsonify(db_balance_diff(params))


@app.post("/api/db/balance/trend")
def api_balance_trend():
    params = complete_lookup_params("", request.get_json(silent=True) or {})
    return jsonify(db_balance_trend(params))


@app.post("/api/db/balance/explain")
def api_balance_explain():
    params = complete_lookup_params("", request.get_json(silent=True) or {})
    return jsonify(db_balance_explain(params))


@app.post("/api/db/balance/highlights")
def api_balance_highlights():
    params = complete_lookup_params("", request.get_json(silent=True) or {})
    return jsonify(db_balance_highlights(params))


@app.post("/api/db/balance/diagnostics")
def api_balance_diagnostics():
    params = complete_lookup_params("", request.get_json(silent=True) or {})
    return jsonify(db_balance_diagnostics(params))


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
        routed = resolve_question_with_llm(full_history, message)
        timings["route_ms"] = round((time.perf_counter() - started) * 1000, 1)
    except requests.HTTPError as exc:
        detail = exc.response.text if exc.response is not None else str(exc)
        return jsonify({"error": f"OpenAI request failed: {detail}"}), 502
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    api_path = routed["api_path"]
    if api_path in {"/api/db/none", "/api/db/unsupported"}:
        result = dispatch_db_api(api_path, routed.get("params") or {})
        reply = format_chat_reply(api_path, result)
        return jsonify({"reply": reply, "routing": routed, "db_result": None, "timings": timings})

    validation_error = validate_route_params(api_path, routed.get("params") or {})
    if validation_error:
        return jsonify({"error": validation_error, "routing": routed}), 400

    try:
        started = time.perf_counter()
        result = dispatch_db_api(api_path, routed.get("params") or {})
        timings["db_api_ms"] = round((time.perf_counter() - started) * 1000, 1)
        reply = format_chat_reply(api_path, result)
    except Exception as exc:
        return jsonify({"error": f"Database API failed: {exc}", "routing": routed}), 500

    return jsonify({"reply": reply, "routing": routed, "db_result": result, "timings": timings})


if __name__ == "__main__":
    app.run(
        host=os.getenv("FLASK_HOST", "127.0.0.1"),
        port=int(os.getenv("FLASK_PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "").lower() in {"1", "true", "yes"},
    )
