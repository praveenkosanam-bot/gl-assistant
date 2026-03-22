*** Settings ***
Resource    ../resources/db_connection.resource
Suite Setup    Initialize Balance Test Context
Suite Teardown    Disconnect From Database

*** Variables ***
${ACTUAL_FLAG_FILTER}    A

*** Test Cases ***
YTD Balance Should Be Numeric
    ${sql}=    Set Variable    SELECT GLCAI_PKG_BAL.get_ytd_balance_f(${LEDGER_ID}, '${PERIOD_NAME}', ${CCID}, '${ACTUAL_FLAG}') AS ytd FROM dual
    ${rows}=    Query    ${sql}
    Log    Testing ledger=${LEDGER_ID}, period=${PERIOD_NAME}, ccid=${CCID}, flag=${ACTUAL_FLAG}
    Log    ${rows}
    Should Not Be Empty    ${rows}
    ${ytd}=    Set Variable    ${rows[0][0]}
    Should Not Be Equal    ${ytd}    ${None}

*** Keywords ***
Initialize Balance Test Context
    Connect To Oracle
    ${seed_sql}=    Set Variable    SELECT ledger_id, period_name, code_combination_id, actual_flag FROM gl_balances WHERE actual_flag = '${ACTUAL_FLAG_FILTER}' AND code_combination_id IS NOT NULL ORDER BY period_name DESC, code_combination_id FETCH FIRST 1 ROWS ONLY
    ${seed_rows}=    Query    ${seed_sql}
    Should Not Be Empty    ${seed_rows}
    ${seed}=    Set Variable    ${seed_rows[0]}
    Set Suite Variable    ${LEDGER_ID}      ${seed[0]}
    Set Suite Variable    ${PERIOD_NAME}    ${seed[1]}
    Set Suite Variable    ${CCID}           ${seed[2]}
    Set Suite Variable    ${ACTUAL_FLAG}    ${seed[3]}
    Log    Using DB seed ledger=${LEDGER_ID}, period=${PERIOD_NAME}, ccid=${CCID}, flag=${ACTUAL_FLAG}
