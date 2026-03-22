CREATE OR REPLACE PACKAGE BODY GLCAI_PKG_BAL IS
    TYPE t_balance_map IS TABLE OF NUMBER INDEX BY PLS_INTEGER;
    g_balances t_balance_map;

    FUNCTION GET_BALANCE(p_account_id IN NUMBER) RETURN NUMBER IS
    BEGIN
        IF g_balances.EXISTS(p_account_id) THEN
            RETURN g_balances(p_account_id);
        ELSE
            RETURN 0;
        END IF;
    END GET_BALANCE;

    PROCEDURE SET_BALANCE(p_account_id IN NUMBER, p_amount IN NUMBER) IS
    BEGIN
        g_balances(p_account_id) := p_amount;
    END SET_BALANCE;
END GLCAI_PKG_BAL;
/
