-- Cleanup script (use carefully). Drop package and revoke grants where appropriate.
BEGIN
    EXECUTE IMMEDIATE 'DROP PACKAGE GLCAI_PKG_BAL';
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE != -4043 THEN
            RAISE;
        END IF;
END;
/

-- Optional: revoke grants
-- REVOKE EXECUTE ON GLCAI_PKG_BAL FROM RUNTIME_USER;
