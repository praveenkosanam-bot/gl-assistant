# Oracle OC Cloned Database Notes

This document summarizes the Oracle database assumptions visible in the current GL Assistant codebase.

## Connectivity Defaults

- Database driver: `oracledb`
- Host default in code: `192.168.8.127`
- Port default in code: `1521`
- Service name default in code: `splashgl001`
- Runtime schema default in the repo: `XXSBID_605`

## Purpose of This Environment

- The cloned Oracle environment is used to query GL balances and journal drill details.
- The assistant does not store business balances in files.
- The database is the source of truth for balances, activities, trends, and diagnostics.

## Core GL Tables Referenced by the App

- `GL_BALANCES`
- `GL_CODE_COMBINATIONS`
- `GL_LEDGERS`
- `COA_FIELDS`
- `GLC_HIERARCHIES`
- `GLC_DRILL_DETAILS`

## Package Interfaces Used

- `GLCAI_PKG_BAL` for simplified custom balance helpers
- `glc_balances_pkg.get_balance` for balance retrieval through the enterprise package
- `glc_drill_pkg.get_journal_dtl` for journal drilldown retrieval
- `glc_utility` session setup functions for GL processing context

## RAG Guidance

Use this file for environment and architecture questions such as:

- which Oracle service the assistant is configured to use
- whether the app talks directly to Oracle
- which tables and packages are involved in ledger and balance lookups

Do not treat these defaults as guaranteed production values outside this repository.
