*** Settings ***
Library    Process
Library    Collections
Library    DatabaseLibrary
Resource   ../resources/db_connection.resource
Suite Setup    Initialize Assistant Suite
Suite Teardown    Cleanup Assistant Suite

*** Variables ***
${APP_URL}                 http://127.0.0.1:5123
${APP_PORT}                5123
${LEDGER_NAME}             US Primary Ledger
${PERIOD_NAME}             01-23
${COMPARE_PERIOD}          02-23
${ACTUAL_FLAG}             A
${ACCOUNT_NUMBER}          11200
${TREND_LENGTH}            4

*** Test Cases ***
Question Inventory Segments Period Routes To Account API
    ${payload}=    Create Dictionary    message=What is the balance for 01.200.${ACCOUNT_NUMBER}, ${PERIOD_NAME}, ${LEDGER_NAME}?    history=${EMPTY_HISTORY}
    ${response}=    Call Assistant API    ${payload}
    Should Be Equal    ${response}[body][routing][api_path]    /api/db/balance/by-account
    Should Be Equal    ${response}[body][db_result][account_number]    ${ACCOUNT_NUMBER}
    Should Not Be Equal    ${response}[body][db_result][period_activity]    ${None}

Question Inventory Diff Routes To Diff API
    ${payload}=    Create Dictionary    message=Compare ${PERIOD_NAME} vs ${COMPARE_PERIOD} for account ${ACCOUNT_NUMBER} on ${LEDGER_NAME}.    history=${EMPTY_HISTORY}
    ${response}=    Call Assistant API    ${payload}
    Should Be Equal    ${response}[body][routing][api_path]    /api/db/balance/diff
    Dictionary Should Contain Key    ${response}[body][db_result]    ytd_delta
    Dictionary Should Contain Key    ${response}[body][db_result]    period_activity_delta

Question Inventory Trend Routes To Trend API
    ${payload}=    Create Dictionary    message=Show last ${TREND_LENGTH} periods for account ${ACCOUNT_NUMBER} on ${LEDGER_NAME}.    history=${EMPTY_HISTORY}
    ${response}=    Call Assistant API    ${payload}
    Should Be Equal    ${response}[body][routing][api_path]    /api/db/balance/trend
    ${periods}=    Get From Dictionary    ${response}[body][db_result]    periods
    Length Should Be    ${periods}    ${TREND_LENGTH}

Question Inventory Explain Routes To Explain API
    ${payload}=    Create Dictionary    message=Explain how the balance for Account ${ACCOUNT_NUMBER} in ${PERIOD_NAME} was calculated for ${LEDGER_NAME}.    history=${EMPTY_HISTORY}
    ${response}=    Call Assistant API    ${payload}
    Should Be Equal    ${response}[body][routing][api_path]    /api/db/balance/explain
    Dictionary Should Contain Key    ${response}[body][db_result]    begin_balance_dr
    Dictionary Should Contain Key    ${response}[body][db_result]    period_net_cr

Question Inventory High Level Routes To Highlights API
    ${payload}=    Create Dictionary    message=Show accounts with high balances in ${PERIOD_NAME} for ${LEDGER_NAME}.    history=${EMPTY_HISTORY}
    ${response}=    Call Assistant API    ${payload}
    Should Be Equal    ${response}[body][routing][api_path]    /api/db/balance/highlights
    ${top_accounts}=    Get From Dictionary    ${response}[body][db_result]    top_accounts
    Should Not Be Empty    ${top_accounts}

Journal Question Is Marked Unsupported
    ${payload}=    Create Dictionary    message=Show journals for Account ${ACCOUNT_NUMBER} in ${PERIOD_NAME}.    history=${EMPTY_HISTORY}
    ${response}=    Call Assistant API    ${payload}
    Should Be Equal    ${response}[body][routing][api_path]    /api/db/unsupported
    Should Contain    ${response}[body][reply]    not implemented yet

Lightweight NLP Parse Returns Intent And Route
    ${payload}=    Create Dictionary    message=Compare ${PERIOD_NAME} vs ${COMPARE_PERIOD} for account ${ACCOUNT_NUMBER} on ${LEDGER_NAME}.
    ${response}=    Call JSON API    POST    ${APP_URL}/api/nlu/parse    ${payload}
    Should Be Equal As Integers    ${response}[status]    200
    Should Be Equal    ${response}[body][lightweight][intent]    balance.diff.two_periods
    Should Be Equal    ${response}[body][routing][api_path]    /api/db/balance/diff

Direct Account DB API Returns Balance
    ${payload}=    Create Dictionary    period_name=${PERIOD_NAME}    account_number=${ACCOUNT_NUMBER}    actual_flag=${ACTUAL_FLAG}
    ${response}=    Call JSON API    POST    ${APP_URL}/api/db/balance/by-account    ${payload}
    Should Be Equal As Integers    ${response}[status]    200
    Should Be Equal    ${response}[body][account_number]    ${ACCOUNT_NUMBER}
    Should Not Be Equal    ${response}[body][ytd_balance]    ${None}

Direct Trend DB API Returns Requested Count
    ${payload}=    Create Dictionary    account_number=${ACCOUNT_NUMBER}    actual_flag=${ACTUAL_FLAG}    n=${TREND_LENGTH}    period_name=${COMPARE_PERIOD}
    ${response}=    Call JSON API    POST    ${APP_URL}/api/db/balance/trend    ${payload}
    Should Be Equal As Integers    ${response}[status]    200
    ${periods}=    Get From Dictionary    ${response}[body]    periods
    Length Should Be    ${periods}    ${TREND_LENGTH}

*** Keywords ***
Initialize Assistant Suite
    Connect To Oracle
    ${rows}=    Query    SELECT gb.code_combination_id FROM gl_balances gb JOIN gl_code_combinations gcc ON gcc.code_combination_id = gb.code_combination_id WHERE gb.period_name = '${PERIOD_NAME}' AND gb.actual_flag = '${ACTUAL_FLAG}' AND gcc.segment3 = '${ACCOUNT_NUMBER}' FETCH FIRST 1 ROWS ONLY
    Should Not Be Empty    ${rows}
    ${compare_rows}=    Query    SELECT 1 FROM gl_balances gb JOIN gl_code_combinations gcc ON gcc.code_combination_id = gb.code_combination_id WHERE gb.period_name = '${COMPARE_PERIOD}' AND gb.actual_flag = '${ACTUAL_FLAG}' AND gcc.segment3 = '${ACCOUNT_NUMBER}' FETCH FIRST 1 ROWS ONLY
    Should Not Be Empty    ${compare_rows}
    ${empty_history}=    Create List
    Set Suite Variable    ${EMPTY_HISTORY}    ${empty_history}
    Start Assistant Server
    Wait For Assistant Health

Cleanup Assistant Suite
    Terminate Process    ${SERVER_HANDLE}    kill=True
    Disconnect From Database

Start Assistant Server
    ${root}=    Set Variable    ${CURDIR}${/}..${/}..
    ${stdout}=    Set Variable    ${root}${/}results${/}assistant_server.out
    ${stderr}=    Set Variable    ${root}${/}results${/}assistant_server.err
    ${handle}=    Start Process    python    app.py    shell=False    cwd=${root}    stdout=${stdout}    stderr=${stderr}    alias=assistant_server
    ...    env:MOCK_OPENAI=1
    ...    env:FLASK_PORT=${APP_PORT}
    ...    env:FLASK_HOST=127.0.0.1
    ...    env:FLASK_DEBUG=0
    ...    env:DB_USER=${DB_USER}
    ...    env:DB_PASSWORD=${DB_PASSWORD}
    ...    env:DB_HOST=${DB_HOST}
    ...    env:DB_PORT=${DB_PORT}
    ...    env:DB_SERVICE=${DB_NAME}
    Set Suite Variable    ${SERVER_HANDLE}    ${handle}

Wait For Assistant Health
    Wait Until Keyword Succeeds    30s    2s    Assistant Health Should Be OK

Assistant Health Should Be OK
    ${response}=    Call JSON API    GET    ${APP_URL}/api/health
    Should Be Equal As Integers    ${response}[status]    200
    Should Be Equal    ${response}[body][db_connected]    ${True}

Call Assistant API
    [Arguments]    ${payload}
    ${response}=    Call JSON API    POST    ${APP_URL}/api/chat    ${payload}
    RETURN    ${response}

Call JSON API
    [Arguments]    ${method}    ${url}    ${payload}=${None}
    ${root}=    Set Variable    ${CURDIR}${/}..${/}..
    ${args}=    Create List    python    scripts/http_json.py    ${method}    ${url}
    IF    $payload is not None
        ${json_payload}=    Evaluate    __import__('json').dumps($payload)
        Append To List    ${args}    ${json_payload}
    END
    ${response}=    Run Process    @{args}    shell=False    cwd=${root}
    Should Be Equal As Integers    ${response.rc}    0
    ${parsed}=    Evaluate    __import__('json').loads(r'''${response.stdout}''')
    RETURN    ${parsed}
