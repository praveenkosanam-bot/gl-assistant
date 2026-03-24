# Chart of Accounts and Account Lookup Rules

This document captures how GL Assistant interprets account-related inputs for the default ledger environment.

## Chart of Accounts Context

- The code uses `COA_ID = 21` when resolving account hierarchies.
- The natural account is mapped from `GL_CODE_COMBINATIONS.SEGMENT3`.
- Account-based balance queries aggregate all code combinations with the same natural account in `SEGMENT3`.

## Hierarchy Resolution

- For account hierarchy lookup, the app checks `COA_FIELDS` for field name `Account`.
- It then checks `GLC_HIERARCHIES` for hierarchy options tied to that field group.
- If exactly one hierarchy exists, the app uses it.
- If multiple hierarchies exist, the app asks the user to select one.
- If no hierarchy is found, the current fallback table name is `GLC_HIER_1169`.

## Built-In Account Aliases

These aliases exist in the current application defaults:

- `cash` -> `11101`
- `receivables` -> `12101`
- `revenue` -> `41000`
- `sales` -> `41000`
- `payables` -> `22100`
- `inventory` -> `14100`
- `expenses` -> `51100`

## Input Interpretation Rules

- A user may ask by natural account number, such as `11200`.
- A user may ask by `CCID`.
- If the user gives a bare number in a balance question, the parser may treat it as an account number.
- Company and department style questions are routed toward account-based balance lookup patterns.

## RAG Guidance

Use this file when the user asks:

- what field represents the natural account
- how account hierarchy selection works
- what `SEGMENT3` means in this app
- whether account aliases such as `cash` or `sales` are supported
