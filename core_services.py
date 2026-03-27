from __future__ import annotations
import os
import re
import random
from pathlib import Path
from typing import Any
import oracledb

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

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

DEFAULT_LEDGER_NAME = os.getenv("DEFAULT_LEDGER_NAME", "US Primary Ledger")
DEFAULT_LEDGER_ID = int(os.getenv("DEFAULT_LEDGER_ID", "300000046975971"))
DEFAULT_CURRENCY_SYMBOL = os.getenv("DEFAULT_CURRENCY_SYMBOL", "$")
DEFAULT_BUDGET_NAME = os.getenv("DEFAULT_BUDGET_NAME", "Budget")

GLC_SOURCE_ID = int(os.getenv("GLC_SOURCE_ID", "0"))
GLC_USER_ID = int(os.getenv("GLC_USER_ID", "0"))
GLC_ROLE = os.getenv("GLC_ROLE", "")
GLC_ROLE_ID = int(os.getenv("GLC_ROLE_ID", "0"))
GLC_COA_ID = int(os.getenv("GLC_COA_ID", "0"))

MOCK_LLM = os.getenv("MOCK_LLM", "").lower() in {"1", "true", "yes"}
RASA_URL = os.getenv("RASA_URL", "").rstrip("/")
QUESTION_INVENTORY_PATH = Path(os.getenv("QUESTION_INVENTORY_PATH", "robot/tests/glcai_questions.yaml"))

ACCOUNT_ALIASES = {
    "cash": "11101",
    "receivables": "12101",
    "revenue": "41000",
    "sales": "41000",
    "payables": "22100",
    "inventory": "14100",
    "expenses": "51100"
}

MONTH_MAP = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12, "ADJ": 13,
}

DB_CONFIG = {
    "user": os.getenv("DB_USER", ""),
    "password": os.getenv("DB_PASSWORD", ""),
    "host": os.getenv("DB_HOST", ""),
    "port": int(os.getenv("DB_PORT", "1521")),
    "service_name": os.getenv("DB_SERVICE", ""),
}

DB_POOL_MIN = int(os.getenv("DB_POOL_MIN", "1"))
DB_POOL_MAX = int(os.getenv("DB_POOL_MAX", "4"))
DB_POOL_INCREMENT = int(os.getenv("DB_POOL_INCREMENT", "1"))

DB_POOL = oracledb.create_pool(
    min=DB_POOL_MIN,
    max=DB_POOL_MAX,
    increment=DB_POOL_INCREMENT,
    **DB_CONFIG,
)

def get_db_connection():
    return DB_POOL.acquire()

def get_coa_for_ledger(ledger_id: int) -> int | None:
    row = query_one(
        "SELECT chart_of_accounts_id FROM gl_ledgers WHERE ledger_id = :ledger_id",
        {"ledger_id": ledger_id}
    )
    return int(row[0]) if row else None

def get_hierarchy_table_for_account(coa_id: int | None = None, hierarchy_id: int | None = None, ledger_id: int | None = None) -> str:
    # If the caller already resolved a hierarchy (from user selection), use it directly.
    if hierarchy_id:
        return f"GLC_HIER_VALUES_{hierarchy_id}"

    # Prefer dynamically looked-up COA for the selected ledger
    if coa_id is None and ledger_id:
        coa_id = get_coa_for_ledger(ledger_id)

    effective_coa_id = coa_id if coa_id is not None else GLC_COA_ID

    # 1. Lookup FIELD_GROUP_ID for 'Account' from COA_FIELDS
    sql_fg = "SELECT FIELD_GROUP_ID FROM coa_fields WHERE coa_id = :coa_id AND field_name = 'Account'"
    fg_row = query_one(sql_fg, {"coa_id": effective_coa_id})
    if not fg_row:
        raise AmbiguousHierarchyError(
            f"No Account field group found for COA {effective_coa_id}.", []
        )
    fg_id = fg_row[0]

    # 2. Lookup ALL HIERARCHY_IDs for that FIELD_GROUP_ID — no defaults, no fallbacks.
    sql_h = "SELECT hierarchy_id, hierarchy_name FROM glc_hierarchies WHERE field_group_id = :fg_id ORDER BY hierarchy_name"
    h_rows = query_all(sql_h, {"fg_id": fg_id})
    print(f"[HIERARCHY] Found {len(h_rows)} options for fg_id {fg_id}")

    if not h_rows:
        raise AmbiguousHierarchyError(
            f"No hierarchies found for field group {fg_id}.", []
        )
    if len(h_rows) == 1:
        return f"GLC_HIER_VALUES_{h_rows[0][0]}"

    # Multiple hierarchies — always prompt the user to choose.
    options = [{"id": r[0], "name": r[1]} for r in h_rows]
    raise AmbiguousHierarchyError("Multiple hierarchies found. Please select one:", options)

class AmbiguousHierarchyError(Exception):
    def __init__(self, message: str, options: list[dict[str, Any]]):
        super().__init__(message)
        self.options = options

def query_one(sql: str, params: dict[str, Any] | None = None):
    import time
    start = time.perf_counter()
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, params or {})
            res = cursor.fetchone()
            duration = (time.perf_counter() - start) * 1000
            print(f"[DB] query_one took {duration:.1f}ms: {sql[:100]}...")
            return res

def query_all(sql: str, params: dict[str, Any] | None = None):
    import time
    start = time.perf_counter()
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, params or {})
            res = cursor.fetchall()
            duration = (time.perf_counter() - start) * 1000
            print(f"[DB] query_all took {duration:.1f}ms: {sql[:100]}...")
            return res

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

def format_currency(amount: Any, currency_symbol: str = DEFAULT_CURRENCY_SYMBOL) -> str:
    if amount is None:
        return "N/A"
    value = float(amount)
    formatted = f"{abs(value):,.2f}"
    if value < 0:
        return f"-{currency_symbol}{formatted}"
    return f"{currency_symbol}{formatted}"

def normalize_period(period_name: str | None) -> str | None:
    return period_name.upper() if period_name else None

def expand_period_range(period_from: str, period_to: str) -> list[str]:
    """Expand a period range (inclusive) into an ordered list of period names."""
    REVERSE_MONTH_MAP = {v: k for k, v in MONTH_MAP.items()}

    def parse(p: str):
        p = p.strip().upper()
        if re.fullmatch(r"\d{2}-\d{2}", p):
            return 2000 + int(p[-2:]), int(p[:2]), "mm-yy"
        m = re.fullmatch(r"([A-Z]{3})-(\d{2})", p)
        if m:
            return 2000 + int(m.group(2)), MONTH_MAP.get(m.group(1), 0), "mmm-yy"
        return None, None, None

    from_year, from_month, fmt = parse(period_from)
    to_year, to_month, _ = parse(period_to)
    if not from_year or not to_year or from_month == 0 or to_month == 0:
        return [period_from, period_to]

    periods: list[str] = []
    y, mo = from_year, from_month
    for _ in range(60):  # safety cap: max 5 years
        if fmt == "mm-yy":
            periods.append(f"{mo:02d}-{y % 100:02d}")
        else:
            periods.append(f"{REVERSE_MONTH_MAP.get(mo, str(mo))}-{y % 100:02d}")
        if y == to_year and mo == to_month:
            break
        mo += 1
        if mo > 12:
            mo = 1
            y += 1
    return periods or [period_from, period_to]


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

def extract_filters(message: str) -> dict[str, Any]:
    patterns = {
        "ledger_id": r"ledger(?:\s+id)?\s*(?:=|:)?\s*(\d+)",
        "period_name": r"\b([A-Z]{3}-\d{2}|\d{2}-\d{2})\b",
        "ccid": r"(?:ccid|code combination(?:\s+id)?)\s*(?:=|:)?\s*(\d+)",
        "account_number": r"(?:account(?:\s+number)?|acct)(?!\w)\s*(?:=|:)?\s*([A-Za-z0-9_-]+)",
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
        elif len(inline_periods) >= 2:
            diff_triggers = re.search(r"\b(change|changed|vs\.?|compare|between|delta|month.on.month)\b", message, re.IGNORECASE)
            if diff_triggers:
                results["period_from"] = inline_periods[0].upper()
                results["period_to"] = inline_periods[1].upper()

    # Comma/and-separated period list: "01-23, 02-23, 03-23" or "01-23, 02-23, and 03-23"
    if "period_from" not in results and "period_to" not in results:
        csv_period_match = re.search(
            r"\b([A-Z]{3}-\d{2}|\d{2}-\d{2})\b(?:\s*,\s*(?:and\s+)?\b(?:[A-Z]{3}-\d{2}|\d{2}-\d{2})\b)+",
            upper_message,
        )
        if csv_period_match:
            results["period_list"] = re.findall(r"\b(?:[A-Z]{3}-\d{2}|\d{2}-\d{2})\b", csv_period_match.group(0))

    # Partial month names without year: "from Jan to Apr", "between March and June"
    if "period_from" not in results and "period_to" not in results and "period_list" not in results:
        _MONTH_NAME_RE = (
            r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?"
            r"|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
        )
        partial_range = re.search(
            r"(?:from|between)\s+" + _MONTH_NAME_RE + r"\b.*?\b(?:to|and)\s+" + _MONTH_NAME_RE,
            message, re.IGNORECASE,
        )
        if partial_range:
            _MO_MAP = {
                "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
                "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
                "aug": 8, "august": 8, "sep": 9, "september": 9, "oct": 10, "october": 10,
                "nov": 11, "november": 11, "dec": 12, "december": 12,
            }
            from_mo = _MO_MAP.get(partial_range.group(1).lower())
            to_mo = _MO_MAP.get(partial_range.group(2).lower())
            if from_mo and to_mo:
                _p_year = None
                try:
                    _seed = seed_lookup(
                        account_number=results.get("account_number"),
                        ccid=results.get("ccid"),
                        ledger_id=results.get("ledger_id", DEFAULT_LEDGER_ID),
                    )
                    if _seed and _seed.get("period_name"):
                        _ym = re.search(r"\d{2}$", _seed["period_name"])
                        if _ym:
                            _p_year = int(_ym.group())
                except Exception:
                    pass
                if _p_year is None:
                    import datetime as _dt
                    _p_year = _dt.datetime.now().year % 100
                results["period_from"] = f"{from_mo:02d}-{_p_year:02d}"
                results["period_to"] = f"{to_mo:02d}-{_p_year:02d}"

    last_n_match = re.search(patterns["last_n"], message, re.IGNORECASE)
    if last_n_match:
        results["n"] = int(last_n_match.group(1))
    elif re.search(r"\b(\d+)[- ]period\b", message, re.IGNORECASE):
        m = re.search(r"\b(\d+)[- ]period\b", message, re.IGNORECASE)
        results["n"] = int(m.group(1))

    for key, pattern in patterns.items():
        if key in {"period_from", "last_n"}:
            continue
        match = re.search(pattern, upper_message if key in {"period_name", "actual_flag"} else message, re.IGNORECASE)
        if not match:
            continue
        value = match.group(1)
        if key == "account_number" and value.lower() in ("has", "is", "for", "in", "the", "change", "what", "which", "account"):
            continue
        if key in {"ledger_id", "ccid"}:
            results[key] = int(value)
        elif key in {"period_name", "actual_flag"}:
            results[key] = value.upper()
        else:
            results[key] = value

    if "account_number" not in results:
        seg_match = re.search(r"\b(\d{2,3})[.\-](\d{2,3})[.\-](\d{4,6})\b", message)
        if seg_match:
            results["account_number"] = seg_match.group(3)
            if "company" not in results: results["company"] = seg_match.group(1)
            if "department" not in results: results["department"] = seg_match.group(2)

    if "account_number" not in results and "ccid" not in results:
        lower_message = message.lower()
        if any(token in lower_message for token in ("balance", "account", "period", "ytd", "activity", "actuals", "budget", "encumbrance", "trend", "journal", "change", "changed", "compare", "break", "breakdown", "debit", "credit", "entered", "accounted", "amount", "functional")):
            bare_number_match = re.search(r"(?<!\d)(\d{4,6})(?!\d)", message)
            if bare_number_match:
                results["account_number"] = bare_number_match.group(1)

    lower_message = message.lower()
    if "actual_flag" not in results:
        if re.search(r"\bactuals?\b", lower_message):
            results["actual_flag"] = "A"
        elif re.search(r"\bvariance\s*%|\bvar\s*%|\bv%\b", lower_message):
            results["actual_flag"] = "V%"
            results.setdefault("budget_name", DEFAULT_BUDGET_NAME)
        elif re.search(r"\bvariance\b", lower_message):
            results["actual_flag"] = "V"
            results.setdefault("budget_name", DEFAULT_BUDGET_NAME)
        elif re.search(r"\bbudget\b", lower_message):
            results["actual_flag"] = "B"
            results.setdefault("budget_name", DEFAULT_BUDGET_NAME)
        elif re.search(r"\bencumbrance\b", lower_message):
            results["actual_flag"] = "E"

    if "entered_flag" not in results:
        if re.search(r"\bentered\b", lower_message):
            results["entered_flag"] = "E"
        elif re.search(r"\b(accounted|functional currency|base currency)\b", lower_message):
            results["entered_flag"] = "A"

    if "period_name" not in results and "period_from" not in results:
        try:
            if re.search(r"\b(this month|this period|current period|current month|recently|last period|recent)\b", lower_message):
                seed = seed_lookup(
                    account_number=results.get("account_number"),
                    ccid=results.get("ccid"),
                    ledger_id=results.get("ledger_id", DEFAULT_LEDGER_ID),
                    period_name=None,
                    actual_flag=results.get("actual_flag"),
                ) or seed_lookup(
                    account_number=results.get("account_number"),
                    ccid=results.get("ccid"),
                    ledger_id=results.get("ledger_id", DEFAULT_LEDGER_ID),
                    period_name=None,
                    actual_flag=None,
                )
                if seed and seed.get("period_name"):
                    results["period_name"] = str(seed["period_name"])
                    if re.search(r"\b(recently|last period|recent)\b", lower_message):
                        results.setdefault("n", 4)
        except Exception:
            pass

    # Quarter notation: Q1/Q2/Q3/Q4
    if "period_name" not in results and "period_from" not in results and "period_list" not in results:
        _qm = re.search(r"\bQ([1-4])\b", message, re.IGNORECASE)
        if _qm:
            _q = int(_qm.group(1))
            _first_mo = (_q - 1) * 3 + 1
            _last_mo = _q * 3
            _q_year = None
            try:
                _qseed = seed_lookup(
                    account_number=results.get("account_number"),
                    ccid=results.get("ccid"),
                    ledger_id=results.get("ledger_id", DEFAULT_LEDGER_ID),
                )
                if _qseed and _qseed.get("period_name"):
                    _qym = re.search(r"\d{2}$", _qseed["period_name"])
                    if _qym:
                        _q_year = int(_qym.group())
            except Exception:
                pass
            if _q_year is None:
                import datetime as _dt
                _q_year = _dt.datetime.now().year % 100
            results["period_from"] = f"{_first_mo:02d}-{_q_year:02d}"
            results["period_to"] = f"{_last_mo:02d}-{_q_year:02d}"
            results["period_list"] = [f"{_mo:02d}-{_q_year:02d}" for _mo in range(_first_mo, _last_mo + 1)]
            results["quarter"] = f"Q{_q}"

    if "activity" in lower_message: results["sort_by"] = "activity"
    if "account_number" not in results:
        for alias, acct in ACCOUNT_ALIASES.items():
            if re.search(rf"\b{alias}\b", lower_message):
                results["account_number"] = acct
                break
    return results

def validate_period(period_name: str, ledger_name: str) -> bool:
    sql = """
        SELECT per.period_id
          FROM periods per
          JOIN ledger_groups_assignments lga
            ON lga.period_type_id = per.period_type_id
           AND lga.period_group_id = per.period_group_id
         WHERE lga.ledger_name = :ledger_name
           AND per.period_name = :period_name
         FETCH FIRST 1 ROW ONLY
    """
    row = query_one(sql, {"period_name": period_name, "ledger_name": ledger_name})
    return bool(row)

def validate_ledger(ledger_name: str) -> bool:
    sql = "SELECT ledger_id FROM ledgers WHERE ledger_name = :ledger_name FETCH FIRST 1 ROW ONLY"
    row = query_one(sql, {"ledger_name": ledger_name})
    return bool(row)

def validate_currency(currency: str) -> bool:
    sql = "SELECT currency FROM currencies WHERE currency = :currency FETCH FIRST 1 ROW ONLY"
    row = query_one(sql, {"currency": currency})
    return bool(row)

def call_glc_balance(
    ledger_name: str | None,
    period_name: str | None,
    actual_flag: str | None,
    account_string: str | None,
    period_type: str = "YTD",
    currency_code: str = "USD",
    hierarchy_id: int | None = None,
    role_id: str | int | None = None,
    role_name: str | None = None,
    ledger_id: int | None = None,
    entered_flag: str = "A",
    budget_name: str | None = None,
) -> tuple[float | None, str | None]:
    session_id = str(random.randint(1000000, 9999999))
    effective_coa_id = (get_coa_for_ledger(ledger_id) if ledger_id else None) or GLC_COA_ID
    hierarchy_table = get_hierarchy_table_for_account(coa_id=effective_coa_id, hierarchy_id=hierarchy_id)
    effective_role_id = int(role_id) if role_id is not None else GLC_ROLE_ID
    effective_role_name = role_name if role_name is not None else GLC_ROLE
    sql = """
    DECLARE
        l_fields glc_utility.varchar2_tab;
        l_hier  glc_utility.varchar2_tab;
        l_bal   NUMBER;
        l_msg   VARCHAR2(4000);
    BEGIN
        glc_utility.g_debug_flag := 'Y';
        glc_utility.g_log_level := '5';
        glc_utility.init_session(
            p_session_id => :session_id,
            p_source_id => :glc_source_id,
            p_user_id => :glc_user_id,
            p_role => :glc_role,
            p_role_id => :glc_role_id,
            p_session_params => NULL
        );
        glc_utility.set_field_groups(p_coa_id => :glc_coa_id);
        l_fields(1) := '';
        l_fields(2) := '';
        l_fields(3) := :account_string;
        l_hier(1)   := '';
        l_hier(2)   := '';
        l_hier(3)   := :hierarchy_table;
        glc_balances_pkg.get_balance(
            p_ledger_name => NVL(:ledger_name, :default_ledger_name),
            p_period_name => :period_name,
            p_actual_flag => :actual_flag,
            p_currency_code => :currency_code,
            p_period_type => :period_type,
            p_get_bal_frm => 'R',
            p_trailing_months => 0,
            p_debit_credit_flag => NULL,
            p_entered_flag => :entered_flag,
            p_period_offset => NULL,
            p_encumbrance_name => NULL,
            p_budget_name => :budget_name,
            p_gl_account_string => NULL,
            p_fields_tbl => l_fields,
            p_field_hier_tbl => l_hier,
            p_security_str => NULL,
            p_session_id => :session_id,
            p_glc_process_id => 1,
            p_balance => l_bal,
            p_message => l_msg
        );
        :out_bal := l_bal;
        :out_msg := l_msg;
    EXCEPTION WHEN OTHERS THEN
        :out_bal := NULL;
        :out_msg := 'GLC_BALANCES_PKG Error: ' || SQLERRM;
    END;
    """
    GLC_CALL_TIMEOUT_MS = int(os.getenv("GLC_CALL_TIMEOUT_MS", "30000"))
    with get_db_connection() as conn:
        conn.call_timeout = GLC_CALL_TIMEOUT_MS
        with conn.cursor() as cursor:
            out_bal = cursor.var(oracledb.DB_TYPE_NUMBER)
            out_msg = cursor.var(str)
            try:
                import time
                start = time.perf_counter()
                cursor.execute(sql, {
                    "session_id": session_id,
                    "glc_source_id": GLC_SOURCE_ID,
                    "glc_user_id": GLC_USER_ID,
                    "glc_role": effective_role_name,
                    "glc_role_id": effective_role_id,
                    "glc_coa_id": effective_coa_id,
                    "ledger_name": ledger_name,
                    "default_ledger_name": DEFAULT_LEDGER_NAME,
                    "period_name": period_name,
                    "actual_flag": actual_flag,
                    "currency_code": currency_code,
                    "period_type": period_type,
                    "entered_flag": entered_flag,
                    "account_string": account_string,
                    "hierarchy_table": hierarchy_table,
                    "budget_name": budget_name,
                    "out_bal": out_bal,
                    "out_msg": out_msg,
                })
                duration = (time.perf_counter() - start) * 1000
                print(f"[GLC] PL/SQL get_balance ({period_type}) took {duration:.1f}ms for account {account_string}")
                val = out_bal.getvalue()
                if val is not None:
                    return float(val), out_msg.getvalue()
                return None, out_msg.getvalue()
            except oracledb.OperationalError as e:
                if "DPY-4011" in str(e) or "DPY-4024" in str(e) or "call timeout" in str(e).lower():
                    timeout_s = GLC_CALL_TIMEOUT_MS // 1000
                    print(f"[GLC] PL/SQL get_balance timed out after {timeout_s}s for account {account_string} — likely a large summary/parent account.")
                    return None, f"Balance query timed out after {timeout_s}s. Account {account_string} may be a parent/summary account with too many child accounts to roll up quickly."
                return None, "Error executing GLC balances: " + str(e)
            except Exception as e:
                return None, "Error executing GLC balances: " + str(e)

def call_get_ledgers() -> dict:
    """Call GET_LEDGERS stored procedure and return parsed responsibilities and ledgers."""
    import json as _json
    session_id = str(random.randint(1000000, 9999999))
    sql = """
    DECLARE
        P_XML_OUT CLOB;
    BEGIN
        GET_LEDGERS(
            P_SOURCE_ID  => :source_id,
            P_USER_ID    => :user_id,
            P_SESSION_ID => :session_id,
            P_XML_OUT    => P_XML_OUT
        );
        :json_out := P_XML_OUT;
    END;
    """
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            json_out = cursor.var(oracledb.DB_TYPE_CLOB)
            cursor.execute(sql, {
                "source_id":  GLC_SOURCE_ID,
                "user_id":    GLC_USER_ID,
                "session_id": session_id,
                "json_out":   json_out,
            })
            raw = json_out.getvalue()
            if raw is None:
                return {"responsibilities": []}
            json_str = raw.read() if hasattr(raw, "read") else str(raw)

    try:
        data = _json.loads(json_str)
        responsibilities = [
            {
                "id":   str(item.get("Id", "")),
                "name": item.get("Name", ""),
                "ledgers": [
                    {"id": str(l.get("Id", "")), "name": l.get("Name", "")}
                    for l in item.get("Ledgers", [])
                ],
            }
            for item in data
        ]
        return {"responsibilities": responsibilities}
    except (_json.JSONDecodeError, TypeError) as exc:
        return {"error": f"JSON parse error: {exc}", "raw": json_str[:500]}


def call_glc_drill(
    ledger_name: str | None,
    period_name: str | None,
    actual_flag: str | None,
    account_string: str | None,
    drill_type: str = "journal",
    hierarchy_id: int | None = None,
    role_id: str | int | None = None,
    role_name: str | None = None,
    ledger_id: int | None = None,
) -> tuple[str | None, str | None]:
    process_id = random.randint(1000000, 9999999)
    session_id = str(process_id)
    effective_coa_id = (get_coa_for_ledger(ledger_id) if ledger_id else None) or GLC_COA_ID
    hierarchy_table = get_hierarchy_table_for_account(coa_id=effective_coa_id, hierarchy_id=hierarchy_id)
    effective_role_id = int(role_id) if role_id is not None else GLC_ROLE_ID
    effective_role_name = role_name if role_name is not None else GLC_ROLE
    sql = """
    DECLARE
        l_fields glc_utility.varchar2_tab;
        l_hier  glc_utility.varchar2_tab;
        l_filter glc_utility.varchar2_tab;
        l_msg   VARCHAR2(4000);
    BEGIN
        glc_utility.g_debug_flag := 'Y';
        glc_utility.g_log_level := '5';
        glc_utility.init_session(
            p_session_id => :session_id,
            p_source_id => :glc_source_id,
            p_user_id => :glc_user_id,
            p_role => :glc_role,
            p_role_id => :glc_role_id,
            p_session_params => NULL
        );
        glc_utility.set_field_groups(p_coa_id => :glc_coa_id);
        l_fields(1) := '';
        l_fields(2) := '';
        l_fields(3) := :account_string;
        l_hier(1)   := '';
        l_hier(2)   := '';
        l_hier(3)   := :hierarchy_table;
        glc_drill_pkg.get_journal_dtl(
            p_ledger_name => NVL(:ledger_name, :default_ledger_name),
            p_period_name => :period_name,
            p_actual_flag => :actual_flag,
            p_currency_code => 'USD',
            p_period_type => 'PTD',
            p_trailing_months => 0,
            p_debit_credit_flag => NULL,
            p_entered_flag => 'B',
            p_gl_account_string => NULL,
            p_fields_tbl => l_fields,
            p_field_hier_tbl => l_hier,
            p_filter_tbl => l_filter,
            p_process_id => :process_id,
            p_glc_process_id => :process_id,
            p_template_id => 0,
            p_drill_count => 1,
            p_message => l_msg
        );
        :out_msg := l_msg;
    EXCEPTION WHEN OTHERS THEN
        :out_msg := 'GLC_DRILL_PKG Error: ' || SQLERRM;
    END;
    """
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            out_msg = cursor.var(str)
            try:
                try:
                    cursor.execute("INSERT INTO glc_drill_details (drill_process_id, sub_process_id, start_time) VALUES (:1, :2, sysdate)", [process_id, process_id])
                except Exception:
                    pass
                cursor.execute(sql, {
                    "session_id": session_id,
                    "glc_source_id": GLC_SOURCE_ID,
                    "glc_user_id": GLC_USER_ID,
                    "glc_role": effective_role_name,
                    "glc_role_id": effective_role_id,
                    "glc_coa_id": effective_coa_id,
                    "ledger_name": ledger_name,
                    "default_ledger_name": DEFAULT_LEDGER_NAME,
                    "period_name": period_name,
                    "actual_flag": actual_flag,
                    "account_string": account_string,
                    "process_id": process_id,
                    "hierarchy_table": hierarchy_table,
                    "out_msg": out_msg,
                })
                conn.commit()
                cursor.execute("SELECT drill_details FROM glc_drill_details WHERE drill_process_id = :p AND rownum = 1", {"p": process_id})
                row = cursor.fetchone()
                if row and row[0]:
                    return str(row[0].read()), out_msg.getvalue()
                return None, out_msg.getvalue()
            except Exception as e:
                return None, "Error executing GLC drill: " + str(e)
