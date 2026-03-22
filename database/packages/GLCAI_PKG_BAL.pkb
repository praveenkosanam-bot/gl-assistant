CREATE OR REPLACE PACKAGE BODY GLCAI_PKG_BAL AS

  /******************************************************************
   * Internals
   ******************************************************************/
  FUNCTION ytd_expr(
    p_begin_dr NUMBER, p_begin_cr NUMBER,
    p_net_dr   NUMBER, p_net_cr   NUMBER
  ) RETURN NUMBER IS
  BEGIN
    RETURN NVL(p_begin_dr,0) - NVL(p_begin_cr,0)
         + NVL(p_net_dr,0)   - NVL(p_net_cr,0);
  END;

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
  BEGIN
    o_status_msg := NULL;

    SELECT ytd_expr(begin_balance_dr, begin_balance_cr, period_net_dr, period_net_cr)
      INTO o_ytd_balance
      FROM gl_balances gb
     WHERE gb.ledger_id            = p_ledger_id
       AND gb.period_name          = p_period_name
       AND gb.code_combination_id  = p_ccid
       AND gb.actual_flag          = NVL(p_actual_flag,'A');

  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      o_ytd_balance := NULL;
      o_status_msg  := 'No GL_BALANCES row found for inputs';
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
  BEGIN
    o_status_msg := NULL;

    SELECT NVL(period_net_dr,0), NVL(period_net_cr,0)
      INTO l_dr, l_cr
      FROM gl_balances gb
     WHERE gb.ledger_id            = p_ledger_id
       AND gb.period_name          = p_period_name
       AND gb.code_combination_id  = p_ccid
       AND gb.actual_flag          = NVL(p_actual_flag,'A');

    o_period_amt := l_dr - l_cr;

  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      o_period_amt := NULL;
      o_status_msg := 'No GL_BALANCES row found for inputs';
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
