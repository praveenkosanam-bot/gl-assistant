# US Primary Ledger

This knowledge file describes the default Oracle General Ledger setup used by GL Assistant in this repository.

## Primary Ledger

- Ledger name: `US Primary Ledger`
- Default ledger ID: `300000046975971`
- Default currency symbol used by the app: `$`
- Default currency code used in requests: `USD`

## Oracle OC Cloned Database Context

- Database service name in this repo: `splashgl001`
- The application treats this as an Oracle cloned environment used for assistant queries and tests.
- The Flask app defaults to connecting through Oracle Database via `oracledb`.

## GL Assistant Assumptions

- If a user does not provide a ledger, the assistant assumes `US Primary Ledger`.
- The application can resolve ledger name from ledger ID when available.
- Health checks validate database connectivity with `SELECT 1 FROM dual`.

## RAG Guidance

Use this document when the question asks:

- what ledger the assistant defaults to
- which ledger is used in the cloned Oracle environment
- what ledger ID belongs to `US Primary Ledger`
- what base currency context the assistant assumes

Do not use this document to answer live balance amounts. Balance values must come from the database, not from static knowledge files.
