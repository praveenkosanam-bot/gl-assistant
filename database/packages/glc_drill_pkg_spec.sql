PACKAGE glc_drill_pkg AUTHID CURRENT_USER
IS
	-- Purpose: This package contains procedures to drilldrown the balances,journals and subledgers
	-- MODIFICATION HISTORY
	-- Person     Version   Date         Comments
	-- ---------  ------    -----------  -------------------------------------------
	-- ANILM      1.0       14-JUL-2020  Created the package
    -- ANJIY      5.7       09-Nov-2023  Added code to Fetch XCC Budget Balances Details

   g_procedure_name 	VARCHAR2(50):='GET_BALANCE';
   g_log_session_id 	NUMBER:= 1;
   g_debug_flag 		VARCHAR2(1):= 'Y';
   g_debug_mode 		VARCHAR2(10):='TAB';
   g_ledger_name 		VARCHAR2(32000);
   g_prev_curr_code 	VARCHAR2(4000);
   g_segment_str1 		VARCHAR2(32000);
   g_curr_code_tbl glc_utility.t_array;
   g_currency_code      VARCHAR2(100);

 PROCEDURE get_balance_dtl
  (
   p_ledger_name            IN VARCHAR2, -- 1 for vis need to pass relevant
   p_period_name            IN VARCHAR2, -- Jan-03
   p_actual_flag            IN VARCHAR2, -- A,B,E--constant
   p_currency_code          IN VARCHAR2, -- USD,AED,GBP..
   p_period_type            IN VARCHAR2, -- YTD,PTD--constant
   p_trailing_months        IN NUMBER,
   p_debit_credit_flag      IN VARCHAR2,
   p_entered_flag           IN VARCHAR2,
   p_period_offset          in number default null,
   p_encumbrance_name       IN VARCHAR2 DEFAULT NULL,
   p_budget_name            IN VARCHAR2 DEFAULT NULL,
   p_gl_account_strinG      IN VARCHAR2 DEFAULT NULL,
   p_fields_tbl             IN glc_utility.varchar2_tab,
   p_field_hier_tbl         IN glc_utility.varchar2_tab,
   p_drill_type             IN VARCHAR2 DEFAULT NULL,
   p_security_str           IN VARCHAR2 DEFAULT NULL,
   p_hide_zero              IN VARCHAR2 DEFAULT 'YES',
   p_session_id             IN VARCHAR2 DEFAULT  NULL,
   p_debug_flag             IN VARCHAR2 DEFAULT NULL,
   p_fsg_process_output_id  IN NUMBER DEFAULT 0,
   p_col_assign_template_id IN NUMBER DEFAULT 0,
   p_process_id             IN number,
   p_glc_process_id         IN NUMBER,
   p_template_id            IN NUMBER,
   p_drill_count            IN NUMBER,
   p_message                OUT VARCHAR2
  );

PROCEDURE get_journal_dtl (
    p_ledger_name              IN    VARCHAR2,
    p_period_name              IN    VARCHAR2,
    p_actual_flag              IN    VARCHAR2,
    p_currency_code            IN    VARCHAR2,
    p_period_type              IN    VARCHAR2,
    p_trailing_months          IN    NUMBER,
    p_debit_credit_flag        IN    VARCHAR2,
    p_entered_flag             IN    VARCHAR2,
    p_period_offset            IN    NUMBER DEFAULT NULL,
    p_fcid                     IN    VARCHAR2 DEFAULT NULL,
    p_encumbrance_name         IN    VARCHAR2 DEFAULT NULL,
    p_budget_name              IN    VARCHAR2 DEFAULT NULL,
    p_gl_account_string        IN    VARCHAR2 DEFAULT NULL,
    p_fields_tbl               IN    glc_utility.varchar2_tab,
    p_field_hier_tbl           IN    glc_utility.varchar2_tab,
    p_filter_tbl               IN    glc_utility.varchar2_tab,
    p_security_str             IN    VARCHAR2 DEFAULT NULL,
    p_session_id               IN    VARCHAR2 DEFAULT NULL,
    p_debug_flag               IN    VARCHAR2 DEFAULT NULL,
    p_fsg_process_output_id    IN    NUMBER DEFAULT 0,
    p_col_assign_template_id   IN    NUMBER DEFAULT 0,
    p_process_id               IN    NUMBER,
    p_glc_process_id           IN    NUMBER,
    p_template_id              IN    NUMBER,
	p_drill_count       	   IN 	 NUMBER,
    p_message                  OUT   VARCHAR2
);

PROCEDURE get_sld_dtl (
    p_ledger_name              IN    VARCHAR2,
    p_period_name              IN    VARCHAR2,
    p_actual_flag              IN    VARCHAR2,
    p_currency_code            IN    VARCHAR2,
    p_je_source                IN    VARCHAR2 DEFAULT NULL,
    p_period_type              IN    VARCHAR2,
    p_trailing_months          IN    NUMBER,
    p_debit_credit_flag        IN    VARCHAR2,
    p_entered_flag             IN    VARCHAR2,
    p_period_offset            IN    NUMBER DEFAULT NULL,
    p_je_header_id             IN    NUMBER DEFAULT NULL,
    p_je_line_num              IN    NUMBER DEFAULT NULL,
    p_ccid                     IN    NUMBER DEFAULT NULL,
    p_encumbrance_name         IN    VARCHAR2 DEFAULT NULL,
    p_budget_name              IN    VARCHAR2 DEFAULT NULL,
    p_gl_account_string        IN    VARCHAR2 DEFAULT NULL,
    p_fields_tbl               IN    glc_utility.varchar2_tab,
    p_field_hier_tbl           IN    glc_utility.varchar2_tab,
    p_filter_tbl               IN    glc_utility.varchar2_tab,
    p_security_str             IN    VARCHAR2 DEFAULT NULL,
    p_session_id               IN    VARCHAR2 DEFAULT NULL,
    p_debug_flag               IN    VARCHAR2 DEFAULT NULL,
    p_fsg_process_output_id    IN    NUMBER DEFAULT 0,
    p_col_assign_template_id   IN    NUMBER DEFAULT 0,
    p_process_id               IN    NUMBER,
    p_glc_process_id           IN    NUMBER,
    p_template_id              IN    NUMBER,
	p_drill_count              IN    NUMBER,
    p_from                     IN    VARCHAR2,
    p_drill_filter_flag        IN    VARCHAR2,
    p_message                  OUT   VARCHAR2
);
--- XCC Budget Balances Details ---
 PROCEDURE get_xcc_balance_dtl
  (
   p_ledger_name            IN VARCHAR2, -- 1 for vis need to pass relevant
   p_period_name            IN VARCHAR2, -- Jan-03
   p_actual_flag            IN VARCHAR2, -- A,B,E--constant
   p_currency_code          IN VARCHAR2, -- USD,AED,GBP..
   p_period_type            IN VARCHAR2, -- YTD,PTD--constant
   p_trailing_months        IN NUMBER,
   p_debit_credit_flag      IN VARCHAR2,
   p_entered_flag           IN VARCHAR2,
   p_period_offset          in number default null,
   p_encumbrance_name       IN VARCHAR2 DEFAULT NULL,
   p_budget_name            IN VARCHAR2 DEFAULT NULL,
   p_gl_account_strinG      IN VARCHAR2 DEFAULT NULL,
   p_fields_tbl             IN glc_utility.varchar2_tab,
   p_field_hier_tbl         IN glc_utility.varchar2_tab,
   p_drill_type             IN VARCHAR2 DEFAULT NULL,
   p_security_str           IN VARCHAR2 DEFAULT NULL,
   p_hide_zero              IN VARCHAR2 DEFAULT 'YES',
   p_session_id             IN VARCHAR2 DEFAULT  NULL,
   p_debug_flag             IN VARCHAR2 DEFAULT NULL,
   p_fsg_process_output_id  IN NUMBER DEFAULT 0,
   p_col_assign_template_id IN NUMBER DEFAULT 0,
   p_process_id             IN number,
   p_glc_process_id         IN NUMBER,
   p_template_id            IN NUMBER,
   p_drill_count            IN NUMBER,
   p_message                OUT VARCHAR2
  );

END glc_drill_pkg;