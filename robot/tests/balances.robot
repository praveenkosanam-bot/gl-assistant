*** Settings ***
Library    DatabaseLibrary
Resource   ../resources/db_connection.resource

*** Variables ***
${CONN_STRING}    ${DB USER}:${DB PASSWORD}@${DB HOST}:${DB PORT}/${DB SERVICE}

*** Test Cases ***
Balance package smoke test
    [Documentation]    Verify GLCAI balance package is accessible and works.
    Connect To Database    cx_Oracle    ${CONN_STRING}
    ${account_id}=    Set Variable    1001
    ${initial}=    Execute Sql String    SELECT GLCAI_PKG_BAL.GET_BALANCE(${account_id}) FROM DUAL
    Should Be Equal As Numbers    ${initial}[0][0]    0
    Execute Sql String    BEGIN GLCAI_PKG_BAL.SET_BALANCE(${account_id}, 12345); END;
    ${after}=    Execute Sql String    SELECT GLCAI_PKG_BAL.GET_BALANCE(${account_id}) FROM DUAL
    Should Be Equal As Numbers    ${after}[0][0]    12345
    Disconnect From Database
