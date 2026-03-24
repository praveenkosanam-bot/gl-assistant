# Journal Drilldown Knowledge

This document explains the journal-related behavior configured in the current GL Assistant repository.

## Current Assistant State

- Journal questions are recognized by the parser.
- The legacy rule-based inventory still maps some journal intents to `/api/db/unsupported`.
- The Flask app also contains a direct path for `/api/db/journal/details`.
- Journal drilldown is therefore partially implemented in the codebase and still evolving.

## Package Used for Journal Detail

The application uses:

- `glc_drill_pkg.get_journal_dtl`

This call is used with inputs such as:

- ledger name
- period name
- actual flag
- currency code
- account number or CCID-derived account
- hierarchy selection data

## Drill Storage

- Drill output is associated with a generated process ID.
- The debug script checks `GLC_DRILL_DETAILS` after execution.
- The application may return a status message and a raw drill CLOB payload.

## What the App Returns

For journal drill requests, the app can return:

- ledger metadata
- selected period
- account number used for the drill
- drill status message
- raw drill payload

If the drill package reports an error, the API returns an error-oriented reply.

## RAG Guidance

Use this file when the user asks:

- whether journal drilldown exists
- how journal detail retrieval works
- what package is used for journal drill
- why journal questions may be marked unsupported in some paths
