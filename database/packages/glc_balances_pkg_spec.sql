PACKAGE glc_balances_pkg AUTHID CURRENT_USER
IS

  -- Purpose: This package contains utility functions and procedures for  GL Connect tool.
  -- MODIFICATION HISTORY
  -- Person     Version   Date         Comments
  -- ---------  ------    -----------  -------------------------------------------
  -- SPUNNA      1.0      10-May-2020  Created the package
  -- SPUNNA      5.2.0    07-Jun-2021  Handle Logic(SGL-420 Fix) for Multiple GL Account Strings through Get Balance

   g_concat_string 		VARCHAR2(4000);
   g_procedure_name 	VARCHAR2(50) := 'GET_BALANCE';
   g_log_session_id 	NUMBER := 1;
   g_debug_flag 		VARCHAR2(1) := 'Y';
   g_debug_mode 		VARCHAR2(10) := 'TAB';
   g_ledger_name 		VARCHAR2(32000);
   g_prev_period_name 	VARCHAR2(4000);
   g_prev_curr_code 	VARCHAR2(4000);
   g_segment_str1 		VARCHAR2(32000);
   g_curr_code_tbl glc_utility.t_array;

  --Added for GL Security
   g_field_security_str 	CLOB;
   g_field_security_str1 	CLOB;
   g_session_id 			VARCHAR2(4000);
   g_security_field_code1 	VARCHAR2(20);
   g_mgt_field_column 		VARCHAR2(1000);

  --Added for GL Security
   PROCEDURE get_balance
   (
	   p_ledger_name         IN    VARCHAR2, -- 1 for vis need to pass relevant
	   p_period_name         IN    VARCHAR2, -- Jan-03
	   p_actual_flag         IN    VARCHAR2, -- A,B,E--constant
	   p_currency_code       IN    VARCHAR2, -- USD,AED,GBP..
	   p_period_type         IN    VARCHAR2, -- YTD,PTD--constant
	   p_get_bal_frm         IN    VARCHAR2 DEFAULT 'R',
	   p_trailing_months     IN    NUMBER,
	   p_debit_credit_flag   IN    VARCHAR2,
	   p_entered_flag        IN    VARCHAR2,
	   p_period_offset       IN    NUMBER DEFAULT NULL,
	   p_encumbrance_name    IN    VARCHAR2 DEFAULT NULL,
	   p_budget_name         IN    VARCHAR2 DEFAULT NULL,
	   p_gl_account_string   IN    VARCHAR2 DEFAULT NULL,
	   p_fields_tbl          IN    glc_utility.varchar2_tab,
	   p_field_hier_tbl      IN    glc_utility.varchar2_tab,
	   p_security_str        IN    VARCHAR2 DEFAULT NULL,
	   p_session_id          IN    VARCHAR2 DEFAULT NULL,
	   p_glc_process_id      IN    NUMBER,
	   p_balance             OUT   NUMBER,
	   p_message             OUT   VARCHAR2
	);

END glc_balances_pkg;