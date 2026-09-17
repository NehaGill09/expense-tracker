# Expense Tracker v2

A desktop expense manager built with Python, SQLite, Tkinter and Matplotlib.

## What's new

- SQLite database instead of CSV-only storage
- Automatic migration from the old `expenses.csv`
- Dashboard with monthly spending cards
- Spending-by-category chart
- Monthly budgets by category
- Automatic recurring expenses
- Smart monthly CSV exports (detailed + category summary)
- JSON monthly reports
- Expense search/listing through the dashboard
- Delete expenses
- Automated tests

## Run

Python 3.10+ is recommended.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python expense_tracker.py
```

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python expense_tracker.py
```

## Test

```bash
python -m pytest
```

## Files created automatically

- `expenses.db` — SQLite database
- `exports/expenses_YYYY-MM.csv` — detailed monthly export
- `exports/expenses_YYYY-MM_summary.csv` — category summary
- `exports/report_YYYY-MM.json` — monthly report

The database and generated exports are ignored by Git so personal spending data is not committed.

## Recurring expenses

Add a recurring expense with a day of the month. When the app starts, it checks whether the current month's recurring expense is due and creates it once automatically. If a month has fewer days than the selected day, the last day of that month is used.

## Budgeting

Set a monthly limit for each category. The dashboard shows spent, budget and remaining amount for the selected month.

## Note

Tkinter is included with most Python installations. On some Linux distributions it must be installed separately (for example, the package commonly named `python3-tk`).
