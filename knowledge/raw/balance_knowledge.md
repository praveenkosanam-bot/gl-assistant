# Balance Retrieval Knowledge for US Primary Ledger

This document explains how balance-related answers should be interpreted in the GL Assistant project.

## Supported Balance Operations

- YTD balance lookup by account
- YTD balance lookup by CCID
- Period activity lookup by account
- Period activity lookup by CCID
- Difference between two periods
- Trend over the last N periods
- Calculation explanation using debit and credit totals
- Diagnostics for null or zero balance situations
- High-level top-account highlights for a period

## Balance Formula

The custom balance package uses the standard Oracle GL style YTD calculation:

`BEGIN_BALANCE_DR - BEGIN_BALANCE_CR + PERIOD_NET_DR - PERIOD_NET_CR`

Period activity is computed as:

`PERIOD_NET_DR - PERIOD_NET_CR`

## Important Data Rules

- Balance results are filtered by ledger, period, and actual flag.
- Default actual flag is `A` for Actual.
- Supported flags in package comments include:
  - `A` for Actual
  - `B` for Budget
  - `E` for Encumbrance
- Currency defaults to `USD` unless overridden.

## Validation Behavior

Before returning results, the app validates:

- ledger name
- period name for the selected ledger
- currency code

If key inputs are missing, the app reports which parameters are required.

## Seed and Default Behavior

- If a query is incomplete, the app may try to complete missing values from a seed lookup.
- If no ledger is provided, the app defaults to `US Primary Ledger`.
- Trend queries sort periods using normalized period keys before selecting the last N periods.

## RAG Guidance

Use this file for conceptual questions such as:

- how YTD is calculated
- what period activity means
- what actual flag values represent
- why the app needs ledger, period, account, or CCID inputs

Do not use this file to answer the actual numeric balance for a live account.
