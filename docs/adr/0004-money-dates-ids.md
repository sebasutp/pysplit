# ADR 0004 — Money, dates and identifiers

Status: Accepted
Date: 2026-10-24
Related: ADR 0000 decision 7

## Context

Parity depends on exactly reproducing the reference's arithmetic and data
formats. The reference uses integer minor units for money, integer thousandths
for quantities, Prisma `Decimal` for conversion rates, ISO text timestamps and
nanoid string IDs. Shared URLs embed group and expense IDs, so identifiers are
part of the public contract.

## Decision

### Money

- All monetary values are **integer minor units** (cents, paise, yen units,
  etc.). No `float` ever touches an amount.
- Currency codes are ISO 4217 strings; the group's display `currency` symbol is
  separate from its `currencyCode`.
- Conversion rates are `Decimal` in Python and **decimal strings** at the HTTP
  boundary (`"1.2345"`). Import parses the reference `DECIMAL` text with
  `Decimal`, never `float`.
- `original_amount` is integer minor units in `original_currency`;
  `amount` is the converted amount in the group currency.
- Splitting rounds with the reference's allocation algorithm (largest remainder,
  stable ordering). The sum of participant shares must equal `amount` exactly;
  no minor unit is created or lost.
- Receipt quantities are integer thousandths (`1000` = 1 unit).

### Dates and times

- Internal timestamps are timezone-aware UTC `datetime` values.
- `expense_date` is stored as a full UTC timestamp to preserve ordering, but
  exposed and treated as `YYYY-MM-DD` at the API boundary and in statistics.
- API timestamps serialize as ISO 8601 UTC with `Z`
  (`2026-10-24T12:00:00Z`).
- Monthly recurrence clamps to the last valid day of the target month
  (Jan 31 → Feb 28/29 → Mar 31), matching the reference.
- Import keeps the reference timestamp text semantics; comparison is done on
  the parsed instant, not the string.

### Identifiers

- IDs are strings, never UUID-only. Legacy nanoid/cuid IDs are imported
  verbatim so every shared link keeps working.
- New IDs are UUIDv4 for new entities, generated **client-side** when the
  repository contract allows offline creation, and accepted verbatim by the
  server inside the sync envelope.
- Clients must not assume UUID format; validation is "non-empty string within
  length limits".
- Composite join tables (`ExpensePaidFor`, `UserGroup`) use their natural
  composite primary keys.

### JSON and HTTP

- `snake_case` everywhere in JSON, including nested objects.
- Lists use `{items, total, limit, offset}`; activities use a cursor.
- Errors use `{"detail": "..."}`; FastAPI validation errors keep the 422 shape.
- Create returns 201, delete returns 204, partial update uses PATCH.
- Booleans are real JSON booleans, never `0`/`1`; the importer converts SQLite
  integers explicitly.
- `None`/`null` means absent, not zero or empty string.

### Import rules

- Open the source database read-only.
- Preserve IDs, timestamps, orphan documents (`expenseId = NULL`) and orphan
  activities (`expenseId` without a matching row).
- Do not import `Session` or `VerificationToken`; users log in again.
- Seed the 44 default categories if `Category` is empty.
- Refuse a non-empty target unless `--reset`; write an `ImportRun` with source
  checksum, counts and duration.

## Consequences

- Python and JavaScript domain functions must agree bit-for-bit; shared golden
  fixtures enforce this in Stages 3 and 9C.
- Conversion-rate strings avoid binary floating-point drift.
- Preserved IDs keep the capability-URL model intact across cutover.
- The UI may show `YYYY-MM-DD` while the API retains full timestamps; tests
  must assert both layers deliberately.

## Rejected alternatives

- **Floating-point money.** Rejected: rounding drift and parity failures.
- **UUID-only IDs.** Rejected: breaks every existing shared link.
- **Date-only storage.** Rejected: loses intra-day ordering used by the
  reference.
- **Local-time timestamps.** Rejected: statistics and recurrence are defined in
  UTC dates.
