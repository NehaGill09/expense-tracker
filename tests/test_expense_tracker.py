from datetime import date
from decimal import Decimal
from expense_tracker import Expense, add_expense, category_totals, load_expenses, monthly_total, save_expenses

def test_add_expense():
    e = add_expense(Decimal("12.345"), " Food ", " Lunch ", date(2026, 9, 1))
    assert e.amount == Decimal("12.35")
    assert e.category == "Food"
    assert e.description == "Lunch"

def test_rejects_non_positive_amount():
    try:
        add_expense(Decimal("0"), "Food", "Lunch")
        assert False
    except ValueError:
        assert True

def test_monthly_total():
    expenses = [Expense(Decimal("10.50"), "Food", "Lunch", date(2026, 9, 2)), Expense(Decimal("20"), "Transport", "Bus", date(2026, 9, 3))]
    assert monthly_total(expenses, 2026, 9) == Decimal("30.50")

def test_category_totals():
    expenses = [Expense(Decimal("10"), "Food", "Lunch", date(2026, 9, 2)), Expense(Decimal("5"), "Food", "Coffee", date(2026, 9, 3))]
    assert category_totals(expenses) == {"Food": Decimal("15.00")}

def test_save_and_load(tmp_path):
    path = tmp_path / "expenses.csv"
    expenses = [Expense(Decimal("10.50"), "Food", "Lunch", date(2026, 9, 2))]
    save_expenses(expenses, path)
    assert load_expenses(path) == expenses
