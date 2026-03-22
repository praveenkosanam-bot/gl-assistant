CREATE OR REPLACE PACKAGE GLCAI_PKG_BAL IS
    -- Get the current balance for an account.
    FUNCTION GET_BALANCE(p_account_id IN NUMBER) RETURN NUMBER;

    -- Set or create the balance for an account.
    PROCEDURE SET_BALANCE(p_account_id IN NUMBER, p_amount IN NUMBER);
END GLCAI_PKG_BAL;
/
