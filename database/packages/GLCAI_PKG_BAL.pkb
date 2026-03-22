CREATE OR REPLACE PACKAGE BODY GLCAI_PKG_BAL AS

  /******************************************************************
   * Public: YTD Balance for a given CCID/Ledger/Period
   ******************************************************************/
  PROCEDURE get_ytd_balance_by_ccid(
    p_ledger_id     IN  NUMBER,
    p_period_name   IN  VARCHAR2,
    p_ccid          IN  NUMBER,
    p_actual_flag   IN  VARCHAR2,
    o_ytd_balance   OUT NUMBER,
    o_status_msg    OUT VARCHAR2
  ) IS
    l_match_count NUMBER;
  BEGIN
    o_status_msg := NULL;

    SELECT COUNT(*),
           SUM(NVL(begin_balance_dr,0) - NVL(begin_balance_cr,0)
             + NVL(period_net_dr,0)   - NVL(period_net_cr,0))
      INTO l_match_count, o_ytd_balance
      FROM gl_balances gb
     WHERE gb.ledger_id            = p_ledger_id
       AND gb.period_name          = p_period_name
       AND gb.code_combination_id  = p_ccid
       AND gb.actual_flag          = NVL(p_actual_flag,'A');

    IF l_match_count = 0 THEN
      o_ytd_balance := NULL;
      o_status_msg  := 'No GL_BALANCES row found for inputs';
    END IF;

  EXCEPTION
    WHEN OTHERS THEN
      o_ytd_balance := NULL;
      o_status_msg  := 'ERR: '||SQLERRM;
  END get_ytd_balance_by_ccid;


  /******************************************************************
   * Public: Period Activity (DR-CR) for given period
   ******************************************************************/
  PROCEDURE get_period_activity_by_ccid(
    p_ledger_id     IN  NUMBER,
    p_period_name   IN  VARCHAR2,
    p_ccid          IN  NUMBER,
    p_actual_flag   IN  VARCHAR2,
    o_period_amt    OUT NUMBER,
    o_status_msg    OUT VARCHAR2
  ) IS
    l_dr NUMBER; l_cr NUMBER;
    l_match_count NUMBER;
  BEGIN
    o_status_msg := NULL;

    SELECT COUNT(*),
           SUM(NVL(period_net_dr,0)),
           SUM(NVL(period_net_cr,0))
      INTO l_match_count, l_dr, l_cr
      FROM gl_balances gb
     WHERE gb.ledger_id            = p_ledger_id
       AND gb.period_name          = p_period_name
       AND gb.code_combination_id  = p_ccid
       AND gb.actual_flag          = NVL(p_actual_flag,'A');

    IF l_match_count = 0 THEN
      o_period_amt := NULL;
      o_status_msg := 'No GL_BALANCES row found for inputs';
    ELSE
      o_period_amt := l_dr - l_cr;
    END IF;

  EXCEPTION
    WHEN OTHERS THEN
      o_period_amt := NULL;
      o_status_msg := 'ERR: '||SQLERRM;
  END get_period_activity_by_ccid;


  /******************************************************************
   * Convenience scalar function for quick assertions
   ******************************************************************/
  FUNCTION get_ytd_balance_f(
    p_ledger_id     IN  NUMBER,
    p_period_name   IN  VARCHAR2,
    p_ccid          IN  NUMBER,
    p_actual_flag   IN  VARCHAR2
  ) RETURN NUMBER IS
    l_val NUMBER;
    l_msg VARCHAR2(4000);
  BEGIN
    get_ytd_balance_by_ccid(
      p_ledger_id   => p_ledger_id,
      p_period_name => p_period_name,
      p_ccid        => p_ccid,
      p_actual_flag => p_actual_flag,
      o_ytd_balance => l_val,
      o_status_msg  => l_msg
    );
    RETURN l_val;
  END get_ytd_balance_f;

END GLCAI_PKG_BAL;
/
SHOW ERRORS
