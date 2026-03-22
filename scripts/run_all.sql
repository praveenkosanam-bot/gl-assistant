SET ECHO ON
WHENEVER SQLERROR EXIT SQL.SQLCODE

-- Compile package
@../database/packages/GLCAI_PKG_BAL.pks
@../database/packages/GLCAI_PKG_BAL.pkb

-- Grants for runtime/test user (adjust recipient)
@../database/util/GLCAI_grants.sql

PROMPT Done.
