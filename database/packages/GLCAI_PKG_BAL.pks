CREATE OR REPLACE PACKAGE GLCAI_PKG_BAL AUTHID CURRENT_USER AS
  /******************************************************************
   * GLCAI_PKG_BAL (v0.1)
   * Balances helper for GL Assistant
   * - All logic stays in PL/SQL
   * - Minimal contract for phase-1 automation & tests
   ******************************************************************/

  /* Returns YTD balance for a given CCID/Ledger/Period.
     YTD formula per Oracle GL_BALANCES doc:
       BEGIN_BALANCE_DR - BEGIN_BALANCE_CR
     + PERIOD_NET_DR - PERIOD_NET_CR
  */
  PROCEDURE get_ytd_balance_by_ccid(
    p_ledger_id     IN  NUMBER,
    p_period_name   IN  VARCHAR2,
    p_ccid          IN  NUMBER,
    p_actual_flag   IN  VARCHAR2 DEFAULT 'A', -- A=Actual; B=Budget; E=Encumbrance
    o_ytd_balance   OUT NUMBER,
    o_status_msg    OUT VARCHAR2
  );

  /* Returns period activity (DR-CR) for the given period (not YTD). */
  PROCEDURE get_period_activity_by_ccid(
    p_ledger_id     IN  NUMBER,
    p_period_name   IN  VARCHAR2,
    p_ccid          IN  NUMBER,
    p_actual_flag   IN  VARCHAR2 DEFAULT 'A',
    o_period_amt    OUT NUMBER,
    o_status_msg    OUT VARCHAR2
  );

  /* Convenience scalar function (helps Robot/SQLcl quickly assert values). */
  FUNCTION get_ytd_balance_f(
    p_ledger_id     IN  NUMBER,
    p_period_name   IN  VARCHAR2,
    p_ccid          IN  NUMBER,
    p_actual_flag   IN  VARCHAR2 DEFAULT 'A'
  ) RETURN NUMBER;

END GLCAI_PKG_BAL;
/
