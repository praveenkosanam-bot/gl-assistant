# Periods, Flags, and Common GL Terms

This file provides vocabulary and normalization guidance for the assistant in the US Primary Ledger context.

## Common Terms

- `ledger`: the accounting ledger used for balances
- `period`: the accounting period, for example `01-23` or `MAR-25`
- `CCID`: code combination ID
- `account number`: the natural account value stored in `SEGMENT3`
- `YTD`: year-to-date balance
- `PTD`: period-to-date or period activity context
- `actual flag`: balance type selector

## Typical Period Formats Seen in This Repo

- `01-23`
- `02-23`
- `03-23`
- `JAN-24`
- `MAR-25`

The assistant normalizes period values and sorts them using internal period sort logic.

## Actual Flag Meanings

- `A` = Actual
- `B` = Budget
- `E` = Encumbrance

If the user omits the actual flag, the application defaults to `A`.

## Typical Question Types

- "What is the balance for account 11200 in 01-23?"
- "Compare 01-23 vs 02-23 for account 11200."
- "Show last 4 periods for account 11200."
- "Explain how the balance was calculated."
- "Why is the balance zero or null?"

## RAG Guidance

Use this file when the user asks for terminology explanations or when retrieved context should clarify:

- period naming
- actual flag meaning
- the difference between account number and CCID
- the difference between YTD and period activity
