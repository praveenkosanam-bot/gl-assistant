import sys
import os
import random
sys.path.append(os.getcwd())
import app
import oracledb

process_id = random.randint(1000000, 9999999)
session_id = str(process_id)

sql = """
DECLARE
    l_fields glc_utility.varchar2_tab;
    l_hier  glc_utility.varchar2_tab;
    l_filter glc_utility.varchar2_tab;
    l_msg   VARCHAR2(4000);
BEGIN
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
    l_fields(3) := '11200';
    
    l_hier(1) := '';
    l_hier(2) := '';
    l_hier(3) := 'GLC_HIER_1169';

    DECLARE
       l_cnt NUMBER;
    BEGIN
       SELECT COUNT(*) INTO l_cnt FROM gl_balances WHERE ledger_id = 300000046975971 AND rownum <= 10;
       dbms_output.put_line('BAL_CNT: ' || l_cnt);
    EXCEPTION WHEN OTHERS THEN
       dbms_output.put_line('BAL_CNT ERROR: ' || SQLERRM);
    END;

    glc_drill_pkg.get_journal_dtl(
        p_ledger_name => 'US Primary Ledger',
        p_period_name => '01-23',
        p_actual_flag => 'A',
        p_currency_code => 'USD',
        p_period_type => 'PTD',
        p_trailing_months => 0,
        p_debit_credit_flag => NULL,
        p_entered_flag => 'B',
        p_gl_account_string => '11200',
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
END;
"""

try:
    with app.get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.callproc("dbms_output.enable", (None,))
            out_msg = cursor.var(str)
            # Pre-insert row to see if it updates it
            cursor.execute("INSERT INTO glc_drill_details (drill_process_id, sub_process_id, start_time) VALUES (:1, :2, sysdate)", [process_id, process_id])
            conn.commit()
            
            print(f"Executing drill for process_id: {process_id}")
            cursor.execute(sql, {"session_id": session_id, "process_id": process_id, "out_msg": out_msg})
            conn.commit()
            print("MSG:", out_msg.getvalue())
            
            # Read dbms_output
            line_var = cursor.var(str)
            status_var = cursor.var(int)
            while True:
                cursor.callproc("dbms_output.get_line", (line_var, status_var))
                if status_var.getvalue() == 0:
                    print("DBMS_OUTPUT:", line_var.getvalue())
                else:
                    break

            # Now check the table
            cursor.execute("SELECT length(drill_details), drill_details FROM glc_drill_details WHERE drill_process_id = :p", {"p": process_id})
            row = cursor.fetchone()
            if row:
                print(f"Found row. Length: {row[0]}")
                if row[1]:
                    print("First 100 chars of CLOB:", row[1].read(100))
                else:
                    print("CLOB is None/Empty")
            else:
                print("No row found in glc_drill_details")
except Exception as e:
    print("Execution Error:", e)
