from datetime import date
from decimal import Decimal
from expense_tracker import ExpenseDB, money

def test_sqlite_expense_and_totals(tmp_path):
    db = ExpenseDB(tmp_path / "test.db")
    db.add_expense(Decimal("10.50"), "Food", "Lunch", date(2026, 9, 2))
    db.add_expense(Decimal("5"), "Food", "Coffee", date(2026, 9, 3))
    assert db.monthly_total(2026, 9) == Decimal("15.50")
    assert db.category_totals(2026, 9) == [("Food", Decimal("15.50"))]
    db.close()

def test_budget(tmp_path):
    db = ExpenseDB(tmp_path / "test.db")
    db.set_budget("Food", Decimal("200"))
    assert db.budgets()[0]["monthly_limit"] == 200
    db.close()

def test_recurring_generation(tmp_path):
    db = ExpenseDB(tmp_path / "test.db")
    db.add_recurring(Decimal("50"), "Bills", "Internet", 10)
    assert db.generate_recurring(date(2026, 9, 10)) == 1
    assert db.generate_recurring(date(2026, 9, 10)) == 0
    assert db.monthly_total(2026, 9) == Decimal("50.00")
    db.close()

def test_money():
    assert money("12.345") == Decimal("12.35")
