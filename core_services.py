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

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_LEDGER_NAME = os.getenv("DEFAULT_LEDGER_NAME", "US Primary Ledger")
DEFAULT_LEDGER_ID = int(os.getenv("DEFAULT_LEDGER_ID", "300000046975971"))
DEFAULT_CURRENCY_SYMBOL = os.getenv("DEFAULT_CURRENCY_SYMBOL", "$")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

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

DB_POOL = oracledb.create_pool(
    min=DB_POOL_MIN,
    max=DB_POOL_MAX,
    increment=DB_POOL_INCREMENT,
    **DB_CONFIG,
)

def get_db_connection():
    return DB_POOL.acquire()

def get_hierarchy_table_for_account(coa_id: int = 21, hierarchy_id: int | None = None) -> str:
    if hierarchy_id:
        return f"GLC_HIER_{hierarchy_id}"
        
    # 1. Lookup FIELD_GROUP_ID for 'Account' from COA_FIELDS
    sql_fg = "SELECT FIELD_GROUP_ID FROM coa_fields WHERE coa_id = :coa_id AND field_name = 'Account'"
    fg_row = query_one(sql_fg, {"coa_id": coa_id})
    if not fg_row:
        return "GLC_HIER_1169" # Fallback
    fg_id = fg_row[0]
    
    # 2. Lookup ALL HIERARCHY_IDs from GLC_HIERARCHIES for that FIELD_GROUP_ID
    sql_h = "SELECT hierarchy_id, hierarchy_name FROM glc_hierarchies WHERE field_group_id = :fg_id"
    h_rows = query_all(sql_h, {"fg_id": fg_id})
    print(f"[HIERARHY] Found {len(h_rows)} options for fg_id {fg_id}")
    
    if not h_rows:
        return "GLC_HIER_1169"
    if len(h_rows) == 1:
        return f"GLC_HIER_{h_rows[0][0]}"
        
    # Multiple hierarchies - Raise a custom error with options
    options = [{"id": r[0], "name": r[1]} for r in h_rows]
    raise AmbiguousHierarchyError("Multiple hierarchies found for this field group.", options)

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
        elif len(inline_periods) >= 2:
            diff_triggers = re.search(r"\b(change|changed|vs\.?|compare|between|delta|month.on.month)\b", message, re.IGNORECASE)
            if diff_triggers:
                results["period_from"] = inline_periods[0].upper()
                results["period_to"] = inline_periods[1].upper()

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
        if any(token in lower_message for token in ("balance", "account", "period", "ytd", "activity", "actuals", "budget", "encumbrance", "trend", "journal")):
            bare_number_match = re.search(r"(?<!\d)(\d{4,6})(?!\d)", message)
            if bare_number_match:
                results["account_number"] = bare_number_match.group(1)

    lower_message = message.lower()
    if "actual_flag" not in results:
        if re.search(r"\bactuals?\b", lower_message): results["actual_flag"] = "A"
        elif re.search(r"\bbudget\b", lower_message): results["actual_flag"] = "B"
        elif re.search(r"\bencumbrance\b", lower_message): results["actual_flag"] = "E"

    if "period_name" not in results and "period_from" not in results:
        try:
            row = query_one(
                "SELECT MAX(period_name) FROM gl_balances WHERE ledger_id = :lid",
                {"lid": DEFAULT_LEDGER_ID},
            )
            if row and row[0]:
                latest = str(row[0])
                if re.search(r"\b(this month|this period|current period|current month)\b", lower_message):
                    results["period_name"] = latest
                elif re.search(r"\b(recently|last period|recent)\b", lower_message):
                    results["period_name"] = latest
                    results.setdefault("n", 4)
        except Exception: pass

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
    hierarchy_id: int | None = None
) -> tuple[float | None, str | None]:
    session_id = str(random.randint(1000000, 9999999))
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
            p_source_id => 5,
            p_user_id => 1,
            p_role => 'ADMIN',
            p_role_id => 30000219190448,
            p_session_params => NULL
        );
        glc_utility.set_field_groups(p_coa_id => 21);
        l_fields(1) := '';
        l_fields(2) := '';
        l_fields(3) := :account_string; 
        l_hier(1)   := '';
        l_hier(2)   := '';
        l_hier(3)   := :hierarchy_table;
        glc_balances_pkg.get_balance(
            p_ledger_name => NVL(:ledger_name, 'US Primary Ledger'),
            p_period_name => :period_name,
            p_actual_flag => :actual_flag,
            p_currency_code => :currency_code,
            p_period_type => :period_type,
            p_get_bal_frm => 'R',
            p_trailing_months => 0,
            p_debit_credit_flag => NULL,
            p_entered_flag => 'B',
            p_period_offset => NULL,
            p_encumbrance_name => NULL,
            p_budget_name => NULL,
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
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            out_bal = cursor.var(oracledb.DB_TYPE_NUMBER)
            out_msg = cursor.var(str)
            try:
                import time
                start = time.perf_counter()
                cursor.execute(sql, {
                    "session_id": session_id,
                    "ledger_name": ledger_name,
                    "period_name": period_name,
                    "actual_flag": actual_flag,
                    "currency_code": currency_code,
                    "period_type": period_type,
                    "account_string": account_string,
                    "hierarchy_table": get_hierarchy_table_for_account(hierarchy_id=hierarchy_id),
                    "out_bal": out_bal,
                    "out_msg": out_msg,
                })
                duration = (time.perf_counter() - start) * 1000
                print(f"[GLC] PL/SQL get_balance ({period_type}) took {duration:.1f}ms for account {account_string}")
                val = out_bal.getvalue()
                if val is not None:
                    return float(val), out_msg.getvalue()
                return None, out_msg.getvalue()
            except Exception as e:
                return None, "Error executing GLC balances: " + str(e)

def call_glc_drill(
    ledger_name: str | None,
    period_name: str | None,
    actual_flag: str | None,
    account_string: str | None,
    drill_type: str = "journal",
    hierarchy_id: int | None = None
) -> tuple[str | None, str | None]:
    process_id = random.randint(1000000, 9999999)
    session_id = str(process_id)
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
            p_source_id => 5,
            p_user_id => 1,
            p_role => 'ADMIN',
            p_role_id => 30000219190448,
            p_session_params => NULL
        );
        glc_utility.set_field_groups(p_coa_id => 21);
        l_fields(1) := '';
        l_fields(2) := '';
        l_fields(3) := :account_string;
        l_hier(1)   := '';
        l_hier(2)   := '';
        l_hier(3)   := :hierarchy_table;
        glc_drill_pkg.get_journal_dtl(
            p_ledger_name => NVL(:ledger_name, 'US Primary Ledger'),
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
                except: pass
                cursor.execute(sql, {
                    "session_id": session_id,
                    "ledger_name": ledger_name,
                    "period_name": period_name,
                    "actual_flag": actual_flag,
                    "account_string": account_string,
                    "process_id": process_id,
                    "hierarchy_table": get_hierarchy_table_for_account(hierarchy_id=hierarchy_id),
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
