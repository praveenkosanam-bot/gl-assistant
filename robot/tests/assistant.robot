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
${LEDGER_ID}               300000046975971
${PERIOD_NAME}             01-23
${ACTUAL_FLAG}             A

*** Test Cases ***
Account Balance Question Returns Account Context
    ${payload}=    Create Dictionary    message=What is the YTD balance for account 11200 in ledger ${LEDGER_ID} for period ${PERIOD_NAME}?    history=${EMPTY_HISTORY}
    ${response}=    Call Assistant API    ${payload}
    Should Be Equal As Integers    ${response}[status]    200
    Dictionary Should Contain Item    ${response}[body][balance_context]    lookup_type    account_number
    Dictionary Should Contain Item    ${response}[body][balance_context]    account_number    11200
    Should Not Be Equal    ${response}[body][balance_context][ytd_balance]    ${None}
    Dictionary Should Contain Key    ${response}[body]    timings

CCID Activity Question Returns CCID Context
    ${message}=    Set Variable    What is the period activity for CCID ${CCID} in ledger ${LEDGER_ID} for period ${PERIOD_NAME}?
    ${payload}=    Create Dictionary    message=${message}    history=${EMPTY_HISTORY}
    ${response}=    Call Assistant API    ${payload}
    Should Be Equal As Integers    ${response}[status]    200
    Dictionary Should Contain Item    ${response}[body][balance_context]    lookup_type    ccid
    Should Be Equal As Integers    ${response}[body][balance_context][ccid]    ${CCID}
    Should Not Be Equal    ${response}[body][balance_context][period_activity]    ${None}

API Usage Question Returns No Balance Context
    ${payload}=    Create Dictionary    message=How do I call the /api/chat endpoint from JavaScript?    history=${EMPTY_HISTORY}
    ${response}=    Call Assistant API    ${payload}
    Should Be Equal As Integers    ${response}[status]    200
    Should Be Equal    ${response}[body][balance_context]    ${None}
    Should Contain    ${response}[body][reply]    Mocked assistant reply

Missing Period Question Uses Seeded Context
    ${payload}=    Create Dictionary    message=What is the YTD balance for account 11200 in ledger ${LEDGER_ID}?    history=${EMPTY_HISTORY}
    ${response}=    Call Assistant API    ${payload}
    Should Be Equal As Integers    ${response}[status]    200
    Dictionary Should Contain Item    ${response}[body][balance_context]    lookup_type    account_number
    Dictionary Should Contain Item    ${response}[body][balance_context]    resolved_from_seed    ${True}

*** Keywords ***
Initialize Assistant Suite
    Connect To Oracle
    ${rows}=    Query    SELECT gb.code_combination_id FROM gl_balances gb JOIN gl_code_combinations gcc ON gcc.code_combination_id = gb.code_combination_id WHERE gb.ledger_id = ${LEDGER_ID} AND gb.period_name = '${PERIOD_NAME}' AND gb.actual_flag = '${ACTUAL_FLAG}' AND gcc.segment3 = '11200' FETCH FIRST 1 ROWS ONLY
    Should Not Be Empty    ${rows}
    ${seed}=    Set Variable    ${rows[0]}
    Set Suite Variable    ${CCID}    ${seed[0]}
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
    ${response}=    Run Process    python    scripts/http_json.py    GET    ${APP_URL}/api/health    shell=False    cwd=${CURDIR}${/}..${/}..
    Should Be Equal As Integers    ${response.rc}    0
    ${parsed}=    Evaluate    __import__('json').loads(r'''${response.stdout}''')
    Should Be Equal As Integers    ${parsed}[status]    200
    Should Be Equal    ${parsed}[body][db_connected]    ${True}

Call Assistant API
    [Arguments]    ${payload}
    ${json_payload}=    Evaluate    __import__('json').dumps($payload)
    ${response}=    Run Process    python    scripts/http_json.py    POST    ${APP_URL}/api/chat    ${json_payload}    shell=False    cwd=${CURDIR}${/}..${/}..
    Should Be Equal As Integers    ${response.rc}    0
    ${parsed}=    Evaluate    __import__('json').loads(r'''${response.stdout}''')
    RETURN    ${parsed}
