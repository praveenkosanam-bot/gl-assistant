import sys
import os
import random
sys.path.append(os.getcwd())
import app
import oracledb

session_id = str(random.randint(1000000, 9999999))

sql = """
DECLARE
    l_fields glc_utility.varchar2_tab;
    l_hier  glc_utility.varchar2_tab;
    l_bal   NUMBER := -999;
    l_msg   VARCHAR2(4000);
BEGIN
    -- Enable Debugging
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
    l_fields(3) := '11200'; -- New target account
    
    l_hier(1) := '';
    l_hier(2) := '';
    l_hier(3) := 'GLC_HIER_1169';

    glc_balances_pkg.get_balance(
        p_ledger_name => 'US Primary Ledger',
        p_period_name => '01-23',
        p_actual_flag => 'A',
        p_currency_code => 'USD',
        p_period_type => 'YTD',
        p_get_bal_frm => 'R',
        p_trailing_months => 0,
        p_debit_credit_flag => NULL,
        p_entered_flag => 'B',
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
END;
"""

try:
    with app.get_db_connection() as conn:
        with conn.cursor() as cursor:
            out_bal = cursor.var(oracledb.DB_TYPE_NUMBER)
            out_msg = cursor.var(str)
            cursor.execute(sql, {"session_id": session_id, "out_bal": out_bal, "out_msg": out_msg})
            print("BAL(11200):", out_bal.getvalue())
            print("MSG:", out_msg.getvalue())
except Exception as e:
    print("Execution Error:", e)
