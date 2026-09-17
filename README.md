# Expense Tracker v3

A full-featured desktop personal expense manager using Python, SQLite, Tkinter and Matplotlib.

## Features
- SQLite persistence with automatic migration from legacy \`expenses.csv\`
- Dashboard: monthly total, daily average, month-over-month change and top category
- Spending by category chart and six-month trend chart
- Search and category filtering
- Add and delete expenses
- Monthly category budgets with remaining/over-budget status
- Recurring expenses with automatic monthly generation
- Pause/resume and delete recurring rules
- Smart CSV exports (detailed + category summary)
- Excel workbook export
- JSON-style analytics are available through the database/reporting layer
- Currency setting
- Automated tests

## Run

\`\`\`bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python expense_tracker.py
\`\`\`

Windows PowerShell:
\`\`\`powershell
python -m venv .venv
.venv\\Scripts\\Activate.ps1
python -m pip install -r requirements.txt
python expense_tracker.py
\`\`\`

Test:
\`\`\`bash
python -m pytest
\`\`\`

## Generated files
- \`expenses.db\` — local SQLite database
- \`exports/expenses_YYYY-MM.csv\` — detailed export
- \`exports/expenses_YYYY-MM_summary.csv\` — category summary
- \`exports/expenses_YYYY-MM.xlsx\` — Excel export when selected

Generated personal data is ignored by Git.
