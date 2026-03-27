*** Settings ***
Library    Process
Library    Collections
Library    OperatingSystem
Suite Setup    Start Application Server
Suite Teardown    Stop Application Server

*** Variables ***
${APP_URL}          http://127.0.0.1:5126
${APP_PORT}         5126
${HIERARCHY_HINT}   CORPORATE
${YAML_PATH}        ${CURDIR}${/}glcai_questions.yaml
${REPORT_PATH}      ${CURDIR}${/}..${/}results${/}questions_summary.txt

*** Test Cases ***
YAML Question Coverage
    ${questions}=    Load YAML Questions
    ${results}=      Create List
    FOR    ${q}    IN    @{questions}
        ${row}=    Ask And Classify    ${q}[intent]    ${q}[question]
        Append To List    ${results}    ${row}
        ${icon}=    Evaluate    '[PASS]' if $row['classification']=='ANSWERED' else ('[WARN]' if $row['classification'] in ('ZERO_BALANCE','NO_DB','UNSUPPORTED') else '[FAIL]')
        Log    ${icon} [${row}[elapsed_ms]ms] ${row}[classification]${SPACE*3}${row}[api_path]${SPACE*3}${row}[question]    console=yes
    END
    Write Summary Report    ${results}
    ${errors}=    Evaluate    sum(1 for r in $results if r['classification'] in ('ERROR','DB_ERROR'))
    Should Be Equal As Integers    ${errors}    0
    ...    msg=There were ${errors} errored questions — see robot/results/questions_summary.txt

*** Keywords ***
Start Application Server
    Create Directory    ${CURDIR}${/}..${/}results
    ${root}=    Set Variable    ${CURDIR}${/}..${/}..
    ${handle}=    Start Process    python    app.py
    ...    shell=False    cwd=${root}
    ...    stdout=${CURDIR}${/}..${/}results${/}qcov_server.out
    ...    stderr=${CURDIR}${/}..${/}results${/}qcov_server.err
    ...    alias=qcov_server
    ...    env:FLASK_PORT=${APP_PORT}    env:FLASK_HOST=127.0.0.1    env:FLASK_DEBUG=0
    Set Suite Variable    ${SERVER_HANDLE}    ${handle}
    Wait Until Keyword Succeeds    30s    2s    Server Should Be Healthy

Stop Application Server
    Terminate Process    ${SERVER_HANDLE}    kill=True

Server Should Be Healthy
    ${r}=    Call JSON API    GET    ${APP_URL}/api/health
    Should Be Equal As Integers    ${r}[status]    200
    Should Be Equal    ${r}[body][db_connected]    ${True}

Load YAML Questions
    ${data}=    Evaluate    __import__('yaml').safe_load(open(r'${YAML_PATH}', encoding='utf-8'))
    ${questions}=    Create List
    FOR    ${intent}    IN    @{data}[intents]
        FOR    ${utt}    IN    @{intent}[utterances]
            ${q}=    Create Dictionary    intent=${intent}[name]    question=${utt}
            Append To List    ${questions}    ${q}
        END
    END
    ${count}=    Get Length    ${questions}
    Log    Loaded ${count} questions from YAML    console=yes
    RETURN    ${questions}

Ask And Classify
    [Arguments]    ${intent}    ${question}
    ${t0}=    Evaluate    __import__('time').perf_counter()
    ${payload}=    Create Dictionary    message=${question}
    ${r}=    Call JSON API    POST    ${APP_URL}/api/chat    ${payload}
    ${body}=    Set Variable    ${r}[body]
    # If the assistant asks to choose a hierarchy, auto-select the preferred one
    ${has_options}=    Run Keyword And Return Status    Dictionary Should Contain Key    ${body}    options
    IF    ${has_options}
        ${options}=    Get From Dictionary    ${body}    options
        ${hid}=    Evaluate    next((o['id'] for o in $options if '${HIERARCHY_HINT}'.lower() in o.get('name','').lower()), $options[0]['id'])
        ${payload2}=    Create Dictionary    message=${question}    hierarchy_id=${hid}
        ${r}=    Call JSON API    POST    ${APP_URL}/api/chat    ${payload2}
        ${body}=    Set Variable    ${r}[body]
    END
    ${elapsed}=    Evaluate    int((__import__('time').perf_counter() - ${t0}) * 1000)
    ${cls}=    Classify Result    ${body}
    ${path}=    Evaluate    ($body.get('routing') or {}).get('api_path', 'N/A')
    ${reply}=    Evaluate    ($body.get('reply') or '')[:80]
    ${row}=    Create Dictionary
    ...    intent=${intent}    question=${question}
    ...    classification=${cls}    api_path=${path}
    ...    elapsed_ms=${elapsed}    reply=${reply}
    RETURN    ${row}

Classify Result
    [Arguments]    ${body}
    ${has_err}=    Run Keyword And Return Status    Dictionary Should Contain Key    ${body}    error
    IF    ${has_err}    RETURN    ERROR
    ${path}=    Evaluate    ($body.get('routing') or {}).get('api_path', '')
    IF    '${path}' == '/api/db/unsupported'    RETURN    UNSUPPORTED
    IF    '${path}' == '/api/db/none'           RETURN    NO_DB
    ${db}=    Evaluate    $body.get('db_result')
    IF    $db is not None
        # Each API has a different result shape — check the right key
        IF    '${path}' == '/api/db/balance/diff'
            ${ok}=    Evaluate    $db.get('ytd_from') is not None or $db.get('ytd_to') is not None
            IF    ${ok}    RETURN    ANSWERED
            RETURN    ZERO_BALANCE
        END
        IF    '${path}' == '/api/db/balance/trend'
            ${ok}=    Evaluate    bool(($db or {}).get('periods'))
            IF    ${ok}    RETURN    ANSWERED
            RETURN    ZERO_BALANCE
        END
        IF    '${path}' == '/api/db/balance/highlights'
            ${ok}=    Evaluate    bool(($db or {}).get('top_accounts'))
            IF    ${ok}    RETURN    ANSWERED
            RETURN    ZERO_BALANCE
        END
        IF    '${path}' == '/api/db/balance/diagnostics'
            ${ok}=    Evaluate    'balance_row_exists' in ($db or {})
            IF    ${ok}    RETURN    ANSWERED
            RETURN    ZERO_BALANCE
        END
        IF    '${path}' == '/api/db/journal/details'
            RETURN    ANSWERED
        END
        IF    '${path}' == '/api/db/balance/multi-period'
            ${ok}=    Evaluate    bool(($db or {}).get('periods'))
            IF    ${ok}    RETURN    ANSWERED
            RETURN    ZERO_BALANCE
        END
        # by-account / by-ccid / explain — ytd_balance can be 0 for parent accounts; None means no data
        ${ytd}=    Evaluate    ($db or {}).get('ytd_balance')
        IF    $ytd is None    RETURN    ZERO_BALANCE
        RETURN    ANSWERED
    END
    ${reply}=    Evaluate    $body.get('reply') or ''
    IF    len($reply) > 10    RETURN    ANSWERED
    RETURN    UNKNOWN

Write Summary Report
    [Arguments]    ${results}
    ${ts}=          Evaluate    __import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    ${total}=       Get Length    ${results}
    ${answered}=    Evaluate    sum(1 for r in $results if r['classification']=='ANSWERED')
    ${zero}=        Evaluate    sum(1 for r in $results if r['classification']=='ZERO_BALANCE')
    ${unsupported}=    Evaluate    sum(1 for r in $results if r['classification']=='UNSUPPORTED')
    ${no_db}=       Evaluate    sum(1 for r in $results if r['classification']=='NO_DB')
    ${errors}=      Evaluate    sum(1 for r in $results if r['classification'] in ('ERROR','DB_ERROR'))
    ${pass_pct}=    Evaluate    int($answered * 100 / $total) if $total else 0
    ${SEP}=         Set Variable    ======================================================================
    ${DASH}=        Set Variable    ----------------------------------------------------------------------
    ${header}=      Catenate    SEPARATOR=\n
    ...    GL Assistant - Question Coverage Report
    ...    Generated: ${ts}
    ...    ${SEP}
    ...    TOTAL          : ${total}
    ...    PASS  ANSWERED : ${answered} (${pass_pct}%)
    ...    WARN  ZERO BAL : ${zero}
    ...    WARN  NO DB    : ${no_db}
    ...    WARN  UNSUPPRTD: ${unsupported}
    ...    FAIL  ERRORS   : ${errors}
    ...    ${SEP}
    ...    ${EMPTY}
    ...    DETAIL (classification | api_path | question)
    ...    ${DASH}
    Create File    ${REPORT_PATH}    ${header}\n    encoding=UTF-8
    FOR    ${r}    IN    @{results}
        ${cls}=     Set Variable    ${r}[classification]
        ${path}=    Set Variable    ${r}[api_path]
        ${q}=       Set Variable    ${r}[question]
        ${ms}=      Set Variable    ${r}[elapsed_ms]
        ${icon}=    Evaluate    '[PASS]' if $cls=='ANSWERED' else ('[WARN]' if $cls in ('ZERO_BALANCE','NO_DB','UNSUPPORTED') else '[FAIL]')
        ${line}=    Catenate    SEPARATOR=    ${icon}${SPACE}    ${cls}${SPACE}    ${path}${SPACE}    [${ms}ms]${SPACE}    ${q}    \n
        Append To File    ${REPORT_PATH}    ${line}    encoding=UTF-8
    END
    Log    Summary written → ${REPORT_PATH}    console=yes

Call JSON API
    [Arguments]    ${method}    ${url}    ${payload}=${None}
    ${root}=    Set Variable    ${CURDIR}${/}..${/}..
    ${args}=    Create List    python    scripts/http_json.py    ${method}    ${url}
    IF    $payload is not None
        ${json_str}=    Evaluate    __import__('json').dumps($payload)
        Append To List    ${args}    ${json_str}
    END
    ${result}=    Run Process    @{args}    shell=False    cwd=${root}
    Should Be Equal As Integers    ${result.rc}    0
    ...    msg=HTTP call failed: ${result.stderr}
    ${parsed}=    Evaluate    __import__('json').loads(r'''${result.stdout}''')
    RETURN    ${parsed}
