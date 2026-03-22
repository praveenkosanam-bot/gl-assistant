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

YTD Balance By Account Should Be Numeric
    ${sql}=    Set Variable    SELECT GLCAI_PKG_BAL.get_ytd_balance_by_account_f(${LEDGER_ID}, '${PERIOD_NAME}', '${ACCOUNT_NUMBER}', '${ACTUAL_FLAG}') AS ytd FROM dual
    ${rows}=    Query    ${sql}
    Log    Testing ledger=${LEDGER_ID}, period=${PERIOD_NAME}, account=${ACCOUNT_NUMBER}, flag=${ACTUAL_FLAG}
    Log    ${rows}
    Should Not Be Empty    ${rows}
    ${ytd}=    Set Variable    ${rows[0][0]}
    Should Not Be Equal    ${ytd}    ${None}

*** Keywords ***
Initialize Balance Test Context
    Connect To Oracle
    ${seed_sql}=    Set Variable    SELECT gb.ledger_id, gb.period_name, gb.code_combination_id, gb.actual_flag, gcc.segment3 FROM gl_balances gb JOIN gl_code_combinations gcc ON gcc.code_combination_id = gb.code_combination_id WHERE gb.actual_flag = '${ACTUAL_FLAG_FILTER}' AND gb.code_combination_id IS NOT NULL AND gcc.segment3 IS NOT NULL ORDER BY gb.period_name DESC, gb.code_combination_id FETCH FIRST 1 ROWS ONLY
    ${seed_rows}=    Query    ${seed_sql}
    Should Not Be Empty    ${seed_rows}
    ${seed}=    Set Variable    ${seed_rows[0]}
    Set Suite Variable    ${LEDGER_ID}      ${seed[0]}
    Set Suite Variable    ${PERIOD_NAME}    ${seed[1]}
    Set Suite Variable    ${CCID}           ${seed[2]}
    Set Suite Variable    ${ACTUAL_FLAG}    ${seed[3]}
    Set Suite Variable    ${ACCOUNT_NUMBER}    ${seed[4]}
    Log    Using DB seed ledger=${LEDGER_ID}, period=${PERIOD_NAME}, ccid=${CCID}, account=${ACCOUNT_NUMBER}, flag=${ACTUAL_FLAG}
