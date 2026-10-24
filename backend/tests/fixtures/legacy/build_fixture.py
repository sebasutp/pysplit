#!/usr/bin/env python3
"""Build the small legacy fixture used by the import tests.

The fixture intentionally includes every legacy table plus the edge cases the
plan calls out: orphan documents and activities, 0/1 booleans, decimal strings,
microsecond timestamps, negative amounts, zero shares, reimbursement rows,
recurrence links in both open and closed states, receipts with shared and
unassigned portions, and sessions that must not be migrated.

Run from the backend root:
    python tests/fixtures/legacy/build_fixture.py
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

OUTPUT = Path(__file__).resolve().parent / "legacy_fixture.db"

SCHEMA = """
PRAGMA foreign_keys=ON;

CREATE TABLE "Group" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "name" TEXT NOT NULL,
    "information" TEXT,
    "currency" TEXT NOT NULL DEFAULT '$',
    "currencyCode" TEXT,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE "Participant" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "name" TEXT NOT NULL,
    "groupId" TEXT NOT NULL,
    CONSTRAINT "Participant_groupId_fkey" FOREIGN KEY ("groupId")
        REFERENCES "Group" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);
CREATE TABLE "Category" (
    "id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    "grouping" TEXT NOT NULL,
    "name" TEXT NOT NULL
);
CREATE TABLE "Expense" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "expenseDate" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "title" TEXT NOT NULL,
    "categoryId" INTEGER NOT NULL DEFAULT 0,
    "amount" INTEGER NOT NULL,
    "originalAmount" INTEGER,
    "originalCurrency" TEXT,
    "conversionRate" DECIMAL,
    "paidById" TEXT NOT NULL,
    "groupId" TEXT NOT NULL,
    "isReimbursement" BOOLEAN NOT NULL DEFAULT false,
    "splitMode" TEXT NOT NULL DEFAULT 'EVENLY',
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "notes" TEXT,
    "recurrenceRule" TEXT DEFAULT 'NONE',
    "recurringExpenseLinkId" TEXT,
    CONSTRAINT "Expense_groupId_fkey" FOREIGN KEY ("groupId")
        REFERENCES "Group" ("id") ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT "Expense_categoryId_fkey" FOREIGN KEY ("categoryId")
        REFERENCES "Category" ("id") ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT "Expense_paidById_fkey" FOREIGN KEY ("paidById")
        REFERENCES "Participant" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);
CREATE TABLE "ExpenseDocument" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "url" TEXT NOT NULL,
    "width" INTEGER NOT NULL,
    "height" INTEGER NOT NULL,
    "expenseId" TEXT,
    CONSTRAINT "ExpenseDocument_expenseId_fkey" FOREIGN KEY ("expenseId")
        REFERENCES "Expense" ("id") ON DELETE SET NULL ON UPDATE CASCADE
);
CREATE TABLE "RecurringExpenseLink" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "groupId" TEXT NOT NULL,
    "currentFrameExpenseId" TEXT NOT NULL,
    "nextExpenseCreatedAt" DATETIME,
    "nextExpenseDate" DATETIME NOT NULL,
    CONSTRAINT "RecurringExpenseLink_currentFrameExpenseId_fkey"
        FOREIGN KEY ("currentFrameExpenseId") REFERENCES "Expense" ("id")
        ON DELETE CASCADE ON UPDATE CASCADE
);
CREATE UNIQUE INDEX "RecurringExpenseLink_currentFrameExpenseId_key"
    ON "RecurringExpenseLink"("currentFrameExpenseId");
CREATE TABLE "ExpensePaidFor" (
    "expenseId" TEXT NOT NULL,
    "participantId" TEXT NOT NULL,
    "shares" INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY ("expenseId", "participantId"),
    CONSTRAINT "ExpensePaidFor_expenseId_fkey" FOREIGN KEY ("expenseId")
        REFERENCES "Expense" ("id") ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT "ExpensePaidFor_participantId_fkey" FOREIGN KEY ("participantId")
        REFERENCES "Participant" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);
CREATE TABLE "Activity" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "groupId" TEXT NOT NULL,
    "time" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "activityType" TEXT NOT NULL,
    "participantId" TEXT,
    "expenseId" TEXT,
    "data" TEXT,
    CONSTRAINT "Activity_groupId_fkey" FOREIGN KEY ("groupId")
        REFERENCES "Group" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);
CREATE TABLE "User" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "name" TEXT,
    "email" TEXT,
    "emailVerified" DATETIME,
    "image" TEXT,
    "tier" TEXT NOT NULL DEFAULT 'sync_users',
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL
);
CREATE UNIQUE INDEX "User_email_key" ON "User"("email");
CREATE TABLE "Account" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "userId" TEXT NOT NULL,
    "type" TEXT NOT NULL,
    "provider" TEXT NOT NULL,
    "providerAccountId" TEXT NOT NULL,
    "refresh_token" TEXT,
    "access_token" TEXT,
    "expires_at" INTEGER,
    "token_type" TEXT,
    "scope" TEXT,
    "id_token" TEXT,
    "session_state" TEXT,
    CONSTRAINT "Account_userId_fkey" FOREIGN KEY ("userId")
        REFERENCES "User" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);
CREATE UNIQUE INDEX "Account_provider_providerAccountId_key"
    ON "Account"("provider", "providerAccountId");
CREATE TABLE "Session" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "sessionToken" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "expires" DATETIME NOT NULL,
    CONSTRAINT "Session_userId_fkey" FOREIGN KEY ("userId")
        REFERENCES "User" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);
CREATE TABLE "VerificationToken" (
    "identifier" TEXT NOT NULL,
    "token" TEXT NOT NULL,
    "expires" DATETIME NOT NULL
);
CREATE TABLE "UserGroup" (
    "userId" TEXT NOT NULL,
    "groupId" TEXT NOT NULL,
    "isStarred" BOOLEAN NOT NULL DEFAULT false,
    "isArchived" BOOLEAN NOT NULL DEFAULT false,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY ("userId", "groupId"),
    CONSTRAINT "UserGroup_userId_fkey" FOREIGN KEY ("userId")
        REFERENCES "User" ("id") ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT "UserGroup_groupId_fkey" FOREIGN KEY ("groupId")
        REFERENCES "Group" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);
CREATE TABLE "Receipt" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "groupId" TEXT NOT NULL,
    "imageUrl" TEXT NOT NULL,
    "imageWidth" INTEGER,
    "imageHeight" INTEGER,
    "status" TEXT NOT NULL DEFAULT 'PENDING',
    "rawExtraction" TEXT,
    "provider" TEXT,
    "model" TEXT,
    "merchant" TEXT,
    "receiptDate" DATETIME,
    "currencyCode" TEXT,
    "total" INTEGER,
    "expenseId" TEXT,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL,
    CONSTRAINT "Receipt_groupId_fkey" FOREIGN KEY ("groupId")
        REFERENCES "Group" ("id") ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT "Receipt_expenseId_fkey" FOREIGN KEY ("expenseId")
        REFERENCES "Expense" ("id") ON DELETE SET NULL ON UPDATE CASCADE
);
CREATE UNIQUE INDEX "Receipt_expenseId_key" ON "Receipt"("expenseId");
CREATE UNIQUE INDEX "Receipt_groupId_imageUrl_key"
    ON "Receipt"("groupId", "imageUrl");
CREATE TABLE "ReceiptItem" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "receiptId" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "quantityMilli" INTEGER NOT NULL DEFAULT 1000,
    "unitPrice" INTEGER,
    "amount" INTEGER NOT NULL,
    "isShared" BOOLEAN NOT NULL DEFAULT false,
    "isAdjustment" BOOLEAN NOT NULL DEFAULT false,
    "position" INTEGER NOT NULL DEFAULT 0,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL,
    CONSTRAINT "ReceiptItem_receiptId_fkey" FOREIGN KEY ("receiptId")
        REFERENCES "Receipt" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);
CREATE TABLE "ReceiptItemPortion" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "itemId" TEXT NOT NULL,
    "target" TEXT NOT NULL,
    "participantId" TEXT,
    "quantityMilli" INTEGER NOT NULL,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL,
    CONSTRAINT "ReceiptItemPortion_itemId_fkey" FOREIGN KEY ("itemId")
        REFERENCES "ReceiptItem" ("id") ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT "ReceiptItemPortion_participantId_fkey" FOREIGN KEY ("participantId")
        REFERENCES "Participant" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);
CREATE TABLE "ReceiptOptOut" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "receiptId" TEXT NOT NULL,
    "participantId" TEXT NOT NULL,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "ReceiptOptOut_receiptId_fkey" FOREIGN KEY ("receiptId")
        REFERENCES "Receipt" ("id") ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT "ReceiptOptOut_participantId_fkey" FOREIGN KEY ("participantId")
        REFERENCES "Participant" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);
CREATE UNIQUE INDEX "ReceiptOptOut_receiptId_participantId_key"
    ON "ReceiptOptOut"("receiptId", "participantId");
"""


def execute_many(connection: sqlite3.Connection, sql: str, rows: list[tuple]) -> None:
    if rows:
        connection.executemany(sql, rows)


def build(path: Path = OUTPUT) -> Path:
    if path.exists():
        path.unlink()
    connection = sqlite3.connect(path)
    try:
        connection.executescript(SCHEMA)

        execute_many(
            connection,
            'INSERT INTO "Group" (id, name, information, currency, currencyCode,'
            " createdAt) VALUES (?, ?, ?, ?, ?, ?)",
            [
                (
                    "group-1",
                    "Cabin trip",
                    None,
                    "€",
                    "EUR",
                    "2026-01-02T03:04:05.678+00:00",
                ),
                (
                    "group-2",
                    "Empty-ish group",
                    "Second group",
                    "$",
                    None,
                    "2026-02-03T04:05:06.789+00:00",
                ),
            ],
        )
        execute_many(
            connection,
            'INSERT INTO "Participant" (id, name, groupId) VALUES (?, ?, ?)',
            [
                ("p1", "Alice", "group-1"),
                ("p2", "Bob", "group-1"),
                ("p3", "Chloé", "group-1"),
                ("p4", "Dana", "group-2"),
            ],
        )
        execute_many(
            connection,
            'INSERT INTO "Category" (id, grouping, name) VALUES (?, ?, ?)',
            [
                (0, "Uncategorized", "General"),
                (1, "Uncategorized", "Payment"),
                (7, "Food and Drink", "Food and Drink"),
                (43, "Life", "Donation"),
            ],
        )

        execute_many(
            connection,
            'INSERT INTO "Expense" (id, expenseDate, title, categoryId, amount,'
            " originalAmount, originalCurrency, conversionRate, paidById, groupId,"
            " isReimbursement, splitMode, createdAt, notes, recurrenceRule,"
            " recurringExpenseLinkId) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,"
            " ?, ?, ?)",
            [
                (
                    "exp-even",
                    "2026-03-01T10:11:12.345678+00:00",
                    "Groceries",
                    7,
                    1000,
                    None,
                    None,
                    None,
                    "p1",
                    "group-1",
                    0,
                    "EVENLY",
                    "2026-03-01T10:11:12.345678+00:00",
                    "with receipt",
                    "NONE",
                    None,
                ),
                (
                    "exp-shares",
                    "2026-03-02T00:00:00.000+00:00",
                    "Firewood",
                    7,
                    1000,
                    None,
                    None,
                    None,
                    "p2",
                    "group-1",
                    0,
                    "BY_SHARES",
                    "2026-03-02T08:00:00.000+00:00",
                    None,
                    "NONE",
                    None,
                ),
                (
                    "exp-percentage",
                    "2026-03-03T00:00:00.000+00:00",
                    "Percentage split",
                    1,
                    999,
                    None,
                    None,
                    None,
                    "p3",
                    "group-1",
                    0,
                    "BY_PERCENTAGE",
                    "2026-03-03T08:00:00.000+00:00",
                    None,
                    "NONE",
                    None,
                ),
                (
                    "exp-amount",
                    "2026-03-04T00:00:00.000+00:00",
                    "Exact amounts",
                    0,
                    1000,
                    None,
                    None,
                    None,
                    "p1",
                    "group-1",
                    0,
                    "BY_AMOUNT",
                    "2026-03-04T08:00:00.000+00:00",
                    None,
                    "NONE",
                    None,
                ),
                (
                    "exp-negative",
                    "2026-03-05T00:00:00.000+00:00",
                    "Refund / income",
                    43,
                    -500,
                    None,
                    None,
                    None,
                    "p2",
                    "group-1",
                    0,
                    "EVENLY",
                    "2026-03-05T08:00:00.000+00:00",
                    None,
                    "NONE",
                    None,
                ),
                (
                    "exp-reimbursement",
                    "2026-03-06T00:00:00.000+00:00",
                    "Paid back in USD",
                    0,
                    2500,
                    2600,
                    "USD",
                    "1.0812345678901234",
                    "p2",
                    "group-1",
                    1,
                    "EVENLY",
                    "2026-03-06T08:00:00.000+00:00",
                    "reimburse",
                    "NONE",
                    None,
                ),
                (
                    "exp-float-decimal",
                    "2026-03-07T00:00:00.000+00:00",
                    "Legacy REAL rate",
                    7,
                    400,
                    500,
                    "GBP",
                    0.5,
                    "p1",
                    "group-1",
                    0,
                    "EVENLY",
                    "2026-03-07T08:00:00.000+00:00",
                    None,
                    "NONE",
                    None,
                ),
                (
                    "exp-weekly",
                    "2026-03-08T00:00:00.000+00:00",
                    "Weekly rent",
                    0,
                    9000,
                    None,
                    None,
                    None,
                    "p4",
                    "group-2",
                    0,
                    "EVENLY",
                    "2026-03-08T08:00:00.000+00:00",
                    None,
                    "WEEKLY",
                    "link-open",
                ),
                (
                    "exp-monthly",
                    "2026-01-31T00:00:00.000+00:00",
                    "Monthly internet",
                    1,
                    3000,
                    None,
                    None,
                    None,
                    "p4",
                    "group-2",
                    0,
                    "EVENLY",
                    "2026-01-31T08:00:00.000+00:00",
                    None,
                    "MONTHLY",
                    "link-closed",
                ),
            ],
        )

        execute_many(
            connection,
            'INSERT INTO "ExpensePaidFor" (expenseId, participantId, shares) VALUES (?, ?, ?)',
            [
                ("exp-even", "p1", 1),
                ("exp-even", "p2", 1),
                ("exp-even", "p3", 1),
                ("exp-shares", "p1", 1),
                ("exp-shares", "p2", 2),
                ("exp-shares", "p3", 0),
                ("exp-percentage", "p1", 3333),
                ("exp-percentage", "p2", 3333),
                ("exp-percentage", "p3", 3334),
                ("exp-amount", "p1", 100),
                ("exp-amount", "p2", 200),
                ("exp-amount", "p3", 700),
                ("exp-negative", "p1", 1),
                ("exp-negative", "p2", 1),
                ("exp-reimbursement", "p2", 1),
                ("exp-reimbursement", "p3", 1),
                ("exp-float-decimal", "p1", 1),
                ("exp-float-decimal", "p2", 1),
                ("exp-weekly", "p4", 1),
                ("exp-monthly", "p4", 1),
            ],
        )

        execute_many(
            connection,
            'INSERT INTO "ExpenseDocument" (id, url, width, height, expenseId)'
            " VALUES (?, ?, ?, ?, ?)",
            [
                (
                    "doc-attached",
                    "https://example.test/receipt.jpg",
                    1200,
                    1600,
                    "exp-even",
                ),
                (
                    "doc-orphan",
                    "https://example.test/orphan.jpg",
                    800,
                    600,
                    None,
                ),
            ],
        )

        execute_many(
            connection,
            'INSERT INTO "RecurringExpenseLink" (id, groupId, currentFrameExpenseId,'
            " nextExpenseCreatedAt, nextExpenseDate) VALUES (?, ?, ?, ?, ?)",
            [
                (
                    "link-open",
                    "group-2",
                    "exp-weekly",
                    None,
                    "2099-03-15T00:00:00.000+00:00",
                ),
                (
                    "link-closed",
                    "group-2",
                    "exp-monthly",
                    "2026-02-28T00:00:00.000+00:00",
                    "2026-02-28T00:00:00.000+00:00",
                ),
            ],
        )

        execute_many(
            connection,
            'INSERT INTO "Activity" (id, groupId, time, activityType,'
            " participantId, expenseId, data) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    "act-create",
                    "group-1",
                    "2026-03-01T10:11:12.345678+00:00",
                    "CREATE_EXPENSE",
                    "p1",
                    "exp-even",
                    "Groceries",
                ),
                (
                    "act-delete",
                    "group-1",
                    "2026-03-09T10:11:12.000000+00:00",
                    "DELETE_EXPENSE",
                    "p2",
                    "exp-deleted-long-ago",
                    "Old expense",
                ),
                (
                    "act-group",
                    "group-2",
                    "2026-03-10T00:00:00.000+00:00",
                    "UPDATE_GROUP",
                    None,
                    None,
                    None,
                ),
            ],
        )

        execute_many(
            connection,
            'INSERT INTO "User" (id, name, email, emailVerified, image, tier,'
            " createdAt, updatedAt) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    "user-admin",
                    "Admin",
                    "admin@example.com",
                    "2026-01-01T00:00:00.000+00:00",
                    "https://example.test/admin.png",
                    "admin",
                    "2026-01-01T00:00:00.000+00:00",
                    "2026-04-01T12:00:00.500+00:00",
                ),
                (
                    "user-plain",
                    None,
                    None,
                    None,
                    None,
                    "sync_users",
                    "2026-01-02T00:00:00.000+00:00",
                    "2026-01-02T00:00:00.000+00:00",
                ),
            ],
        )

        execute_many(
            connection,
            'INSERT INTO "Account" (id, userId, type, provider, providerAccountId,'
            " refresh_token, access_token, expires_at, token_type, scope, id_token,"
            " session_state) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    "acc-google",
                    "user-admin",
                    "oauth",
                    "google",
                    "google-123",
                    "refresh-secret",
                    "access-secret",
                    1800000000,
                    "bearer",
                    "openid email profile",
                    "id-token",
                    "state",
                ),
                (
                    "acc-github",
                    "user-plain",
                    "oauth",
                    "github",
                    "github-456",
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                ),
            ],
        )

        execute_many(
            connection,
            'INSERT INTO "UserGroup" (userId, groupId, isStarred, isArchived,'
            " createdAt) VALUES (?, ?, ?, ?, ?)",
            [
                (
                    "user-admin",
                    "group-1",
                    1,
                    0,
                    "2026-01-03T00:00:00.000+00:00",
                ),
                (
                    "user-admin",
                    "group-2",
                    0,
                    1,
                    "2026-01-04T00:00:00.000+00:00",
                ),
                (
                    "user-plain",
                    "group-1",
                    0,
                    0,
                    "2026-01-05T00:00:00.000+00:00",
                ),
            ],
        )

        execute_many(
            connection,
            'INSERT INTO "Receipt" (id, groupId, imageUrl, imageWidth, imageHeight,'
            " status, rawExtraction, provider, model, merchant, receiptDate,"
            " currencyCode, total, expenseId, createdAt, updatedAt) VALUES (?, ?, ?,"
            " ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    "receipt-1",
                    "group-1",
                    "https://example.test/receipt.jpg",
                    1200,
                    1600,
                    "READY",
                    '{"items": 3}',
                    "openai",
                    "gpt-test",
                    "Corner Shop",
                    "2026-02-28T00:00:00.000+00:00",
                    "EUR",
                    1000,
                    "exp-even",
                    "2026-03-01T09:00:00.000+00:00",
                    "2026-03-01T09:30:00.000+00:00",
                ),
                (
                    "receipt-2",
                    "group-2",
                    "https://example.test/pending.jpg",
                    None,
                    None,
                    "PENDING",
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    "2026-03-11T00:00:00.000+00:00",
                    "2026-03-11T00:00:00.000+00:00",
                ),
            ],
        )

        execute_many(
            connection,
            'INSERT INTO "ReceiptItem" (id, receiptId, name, quantityMilli,'
            " unitPrice, amount, isShared, isAdjustment, position, createdAt,"
            " updatedAt) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    "item-bread",
                    "receipt-1",
                    "Bread",
                    2000,
                    250,
                    500,
                    0,
                    0,
                    0,
                    "2026-03-01T09:10:00.000+00:00",
                    "2026-03-01T09:10:00.000+00:00",
                ),
                (
                    "item-shared",
                    "receipt-1",
                    "Shared tax",
                    1000,
                    None,
                    300,
                    1,
                    1,
                    1,
                    "2026-03-01T09:11:00.000+00:00",
                    "2026-03-01T09:11:00.000+00:00",
                ),
                (
                    "item-cheese",
                    "receipt-1",
                    "Cheese",
                    1000,
                    200,
                    200,
                    0,
                    0,
                    2,
                    "2026-03-01T09:12:00.000+00:00",
                    "2026-03-01T09:12:00.000+00:00",
                ),
            ],
        )

        execute_many(
            connection,
            'INSERT INTO "ReceiptItemPortion" (id, itemId, target, participantId,'
            " quantityMilli, createdAt, updatedAt) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    "portion-1",
                    "item-bread",
                    "p1",
                    "p1",
                    1000,
                    "2026-03-01T09:20:00.000+00:00",
                    "2026-03-01T09:20:00.000+00:00",
                ),
                (
                    "portion-2",
                    "item-bread",
                    "p2",
                    "p2",
                    500,
                    "2026-03-01T09:20:00.000+00:00",
                    "2026-03-01T09:20:00.000+00:00",
                ),
                (
                    "portion-shared",
                    "item-shared",
                    "shared",
                    None,
                    1000,
                    "2026-03-01T09:21:00.000+00:00",
                    "2026-03-01T09:21:00.000+00:00",
                ),
                (
                    "portion-unassigned",
                    "item-cheese",
                    "unassigned",
                    None,
                    500,
                    "2026-03-01T09:22:00.000+00:00",
                    "2026-03-01T09:22:00.000+00:00",
                ),
            ],
        )

        execute_many(
            connection,
            'INSERT INTO "ReceiptOptOut" (id, receiptId, participantId, createdAt)'
            " VALUES (?, ?, ?, ?)",
            [
                (
                    "optout-1",
                    "receipt-1",
                    "p3",
                    "2026-03-01T09:25:00.000+00:00",
                )
            ],
        )

        # These must never be migrated.
        execute_many(
            connection,
            'INSERT INTO "Session" (id, sessionToken, userId, expires) VALUES (?, ?, ?, ?)',
            [
                (
                    "session-1",
                    "session-token",
                    "user-admin",
                    "2027-01-01T00:00:00.000+00:00",
                )
            ],
        )
        execute_many(
            connection,
            'INSERT INTO "VerificationToken" (identifier, token, expires) VALUES (?, ?, ?)',
            [
                (
                    "admin@example.com",
                    "verification-token",
                    "2026-12-31T00:00:00.000+00:00",
                )
            ],
        )

        connection.commit()
    finally:
        connection.close()
    return path


if __name__ == "__main__":
    print(build())
