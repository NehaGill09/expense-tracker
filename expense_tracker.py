#!/usr/bin/env python3
import csv
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

DATA_FILE = Path("expenses.csv")

@dataclass(frozen=True)
class Expense:
    amount: Decimal
    category: str
    description: str
    expense_date: date

def load_expenses(path=DATA_FILE):
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return [Expense(Decimal(r["amount"]), r["category"], r["description"], date.fromisoformat(r["date"])) for r in csv.DictReader(f)]

def save_expenses(expenses, path=DATA_FILE):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["amount", "category", "description", "date"])
        for e in expenses:
            w.writerow([format(e.amount, ".2f"), e.category, e.description, e.expense_date.isoformat()])

def add_expense(amount, category, description, expense_date=None):
    if amount <= 0:
        raise ValueError("Amount must be greater than zero.")
    category, description = category.strip(), description.strip()
    if not category or not description:
        raise ValueError("Category and description cannot be empty.")
    return Expense(amount.quantize(Decimal("0.01")), category, description, expense_date or date.today())

def monthly_total(expenses, year, month):
    return sum((e.amount for e in expenses if e.expense_date.year == year and e.expense_date.month == month), Decimal("0")).quantize(Decimal("0.01"))

def category_totals(expenses):
    totals = {}
    for e in expenses:
        totals[e.category] = totals.get(e.category, Decimal("0")) + e.amount
    return {k: v.quantize(Decimal("0.01")) for k, v in sorted(totals.items())}

def export_csv(expenses, output_path):
    save_expenses(expenses, Path(output_path))

def get_amount():
    while True:
        try:
            value = Decimal(input("Amount: ").strip())
            if value <= 0:
                raise ValueError
            return value
        except (InvalidOperation, ValueError):
            print("Enter a valid positive amount.")

def get_date():
    while True:
        raw = input("Date (YYYY-MM-DD, blank for today): ").strip()
        if not raw:
            return date.today()
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            print("Use YYYY-MM-DD.")

def main():
    expenses = load_expenses()
    while True:
        print("\n=== Expense Tracker ===")
        print("1. Add expense")
        print("2. Monthly total")
        print("3. Category totals")
        print("4. Export CSV")
        print("5. List expenses")
        print("6. Exit")
        choice = input("Choose an option: ").strip()
        if choice == "1":
            try:
                e = add_expense(get_amount(), input("Category: "), input("Description: "), get_date())
                expenses.append(e)
                save_expenses(expenses)
                print("Expense added.")
            except ValueError as exc:
                print("Error:", exc)
        elif choice == "2":
            raw = input("Month (YYYY-MM, blank for current month): ").strip()
            try:
                d = datetime.strptime(raw, "%Y-%m").date() if raw else date.today()
                print("Monthly total:", monthly_total(expenses, d.year, d.month))
            except ValueError:
                print("Use YYYY-MM.")
        elif choice == "3":
            for category, total in category_totals(expenses).items():
                print(category + ":", total)
        elif choice == "4":
            name = input("Export filename [expenses_export.csv]: ").strip() or "expenses_export.csv"
            export_csv(expenses, name)
            print("Exported to", name)
        elif choice == "5":
            if not expenses:
                print("No expenses recorded.")
            for i, e in enumerate(expenses, 1):
                print(i, e.expense_date, "|", e.category, "|", e.amount, "|", e.description)
        elif choice == "6":
            print("Goodbye!")
            break
        else:
            print("Choose 1-6.")

if __name__ == "__main__":
    main()
