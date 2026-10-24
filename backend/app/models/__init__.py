"""SQLModel table classes.

Importing this package registers every table on ``SQLModel.metadata`` for
Alembic and for in-memory test databases.
"""

from app.models.account import Account
from app.models.activity import Activity
from app.models.category import Category
from app.models.expense import Expense
from app.models.expense_document import ExpenseDocument
from app.models.expense_paid_for import ExpensePaidFor
from app.models.group import Group
from app.models.import_run import ImportRun
from app.models.participant import Participant
from app.models.receipt import Receipt
from app.models.receipt_item import ReceiptItem
from app.models.receipt_item_portion import ReceiptItemPortion
from app.models.receipt_opt_out import ReceiptOptOut
from app.models.recurring_expense_link import RecurringExpenseLink
from app.models.refresh_token import RefreshToken
from app.models.sync_change import SyncChange
from app.models.sync_operation import SyncOperation
from app.models.user import User
from app.models.user_group import UserGroup

__all__ = [
    "Account",
    "Activity",
    "Category",
    "Expense",
    "ExpenseDocument",
    "ExpensePaidFor",
    "Group",
    "ImportRun",
    "Participant",
    "Receipt",
    "ReceiptItem",
    "ReceiptItemPortion",
    "ReceiptOptOut",
    "RecurringExpenseLink",
    "RefreshToken",
    "SyncChange",
    "SyncOperation",
    "User",
    "UserGroup",
]
