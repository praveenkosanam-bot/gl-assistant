import sys
import os
sys.path.append(os.getcwd())
import app
import oracledb

sql = """
DECLARE
    l_fields glc_utility.varchar2_tab;
    l_hier  glc_utility.varchar2_tab;
    l_bal   NUMBER := -999;
    l_msg   VARCHAR2(4000) := 'default';
BEGIN
    l_fields(1) := 'SEGMENT3';
    glc_balances_pkg.get_balance(
        p_ledger_name => 'US Primary Ledger',
        p_period_name => '01-23',
        p_actual_flag => 'A',
        p_currency_code => 'USD',
        p_period_type => 'YTD',
        p_get_bal_frm => 'R',
        p_trailing_months => 0,
        p_debit_credit_flag => NULL,
        p_entered_flag => 'N',
        p_period_offset => NULL,
        p_encumbrance_name => NULL,
        p_budget_name => NULL,
        p_gl_account_string => '11101',
        p_fields_tbl => l_fields,
        p_field_hier_tbl => l_hier,
        p_security_str => NULL,
        p_session_id => NULL,
        p_glc_process_id => 1,
        p_balance => l_bal,
        p_message => l_msg
    );
    :out_bal := l_bal;
    :out_msg := l_msg;
EXCEPTION WHEN OTHERS THEN
    :out_msg := SQLERRM;
END;
"""

try:
    with app.get_db_connection() as conn:
        with conn.cursor() as cursor:
            out_bal = cursor.var(oracledb.DB_TYPE_NUMBER)
            out_msg = cursor.var(str)
            cursor.execute(sql, {"out_bal": out_bal, "out_msg": out_msg})
            print("BAL:", out_bal.getvalue())
            print("MSG:", out_msg.getvalue())
except Exception as e:
    print("Execution Error:", e)
