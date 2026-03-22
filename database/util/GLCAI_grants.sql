-- Grant required permissions to runtime/test user
-- Replace RUNTIME_USER with your runtime role or user name.

GRANT EXECUTE ON GLCAI_PKG_BAL TO RUNTIME_USER;

-- If there are tables, add grants like:
-- GRANT SELECT, INSERT, UPDATE, DELETE ON GLCAI_BALANCES TO RUNTIME_USER;
