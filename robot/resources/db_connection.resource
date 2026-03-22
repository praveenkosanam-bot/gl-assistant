*** Settings ***
Library    DatabaseLibrary

*** Variables ***
${DB_MODULE}    oracledb
${DB_NAME}      splashgl001
${DB_USER}      XXSBID_605
${DB_PASSWORD}  XXSBID_605
${DB_HOST}      192.168.8.127
${DB_PORT}      1521

*** Keywords ***
Connect To Oracle
    Connect To Database    ${DB_MODULE}    db_name=${DB_NAME}    db_user=${DB_USER}
    ...    db_password=${DB_PASSWORD}    db_host=${DB_HOST}    db_port=${DB_PORT}
