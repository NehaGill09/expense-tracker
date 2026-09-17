#!/usr/bin/env python3
"""
Expense Tracker v2
Desktop expense manager using SQLite, Tkinter and Matplotlib.
"""
import csv
import sqlite3
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
import calendar
import json
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

try:
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
except ImportError:
    Figure = None
    FigureCanvasTkAgg = None

BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "expenses.db"
EXPORT_DIR = BASE_DIR / "exports"
LEGACY_CSV = BASE_DIR / "expenses.csv"
CURRENCY = "$"


def money(value):
    return Decimal(str(value)).quantize(Decimal("0.01"))


class ExpenseDB:
    def __init__(self, path=DB_FILE):
        self.path = Path(path)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.init_db()
        self.migrate_legacy_csv()

    def init_db(self):
        self.conn.executescript("""
        PRAGMA foreign_keys = ON;
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            amount REAL NOT NULL CHECK(amount > 0),
            category TEXT NOT NULL,
            description TEXT NOT NULL,
            expense_date TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            recurring_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL UNIQUE,
            monthly_limit REAL NOT NULL CHECK(monthly_limit >= 0)
        );
        CREATE TABLE IF NOT EXISTS recurring_expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            amount REAL NOT NULL CHECK(amount > 0),
            category TEXT NOT NULL,
            description TEXT NOT NULL,
            day_of_month INTEGER NOT NULL CHECK(day_of_month BETWEEN 1 AND 31),
            active INTEGER NOT NULL DEFAULT 1,
            last_generated TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(expense_date);
        CREATE INDEX IF NOT EXISTS idx_expenses_category ON expenses(category);
        """)
        self.conn.commit()

    def migrate_legacy_csv(self):
        count = self.conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
        if count or not LEGACY_CSV.exists():
            return
        try:
            with LEGACY_CSV.open(newline="", encoding="utf-8") as f:
                rows = csv.DictReader(f)
                for r in rows:
                    self.add_expense(Decimal(r["amount"]), r["category"], r["description"], r["date"])
        except (OSError, KeyError, ValueError, InvalidOperation):
            pass

    def add_expense(self, amount, category, description, expense_date=None, recurring_id=None):
        amount = money(amount)
        category, description = category.strip(), description.strip()
        if amount <= 0 or not category or not description:
            raise ValueError("Amount must be positive and category/description are required.")
        d = expense_date or date.today().isoformat()
        if isinstance(d, date):
            d = d.isoformat()
        cur = self.conn.execute(
            "INSERT INTO expenses(amount,category,description,expense_date,recurring_id) VALUES(?,?,?,?,?)",
            (float(amount), category, description, d, recurring_id))
        self.conn.commit()
        return cur.lastrowid

    def expenses(self, year=None, month=None, category=None):
        q = "SELECT * FROM expenses WHERE 1=1"
        args = []
        if year:
            q += " AND strftime('%Y', expense_date)=?"
            args.append(str(year))
        if month:
            q += " AND strftime('%m', expense_date)=?"
            args.append(f"{month:02d}")
        if category and category != "All":
            q += " AND category=?"
            args.append(category)
        q += " ORDER BY expense_date DESC, id DESC"
        return self.conn.execute(q, args).fetchall()

    def monthly_total(self, year, month):
        row = self.conn.execute(
            "SELECT COALESCE(SUM(amount),0) FROM expenses WHERE strftime('%Y',expense_date)=? AND strftime('%m',expense_date)=?",
            (str(year), f"{month:02d}")).fetchone()
        return money(row[0])

    def category_totals(self, year, month):
        rows = self.conn.execute(
            "SELECT category, SUM(amount) total FROM expenses WHERE strftime('%Y',expense_date)=? AND strftime('%m',expense_date)=? GROUP BY category ORDER BY total DESC",
            (str(year), f"{month:02d}")).fetchall()
        return [(r["category"], money(r["total"])) for r in rows]

    def budgets(self):
        return self.conn.execute("SELECT * FROM budgets ORDER BY category").fetchall()

    def set_budget(self, category, limit):
        limit = money(limit)
        if not category.strip() or limit < 0:
            raise ValueError("Enter a category and a non-negative budget.")
        self.conn.execute(
            "INSERT INTO budgets(category,monthly_limit) VALUES(?,?) ON CONFLICT(category) DO UPDATE SET monthly_limit=excluded.monthly_limit",
            (category.strip(), float(limit)))
        self.conn.commit()

    def recurring(self):
        return self.conn.execute("SELECT * FROM recurring_expenses WHERE active=1 ORDER BY day_of_month, category").fetchall()

    def add_recurring(self, amount, category, description, day_of_month):
        day = int(day_of_month)
        if day < 1 or day > 31:
            raise ValueError("Day must be between 1 and 31.")
        self.conn.execute(
            "INSERT INTO recurring_expenses(amount,category,description,day_of_month) VALUES(?,?,?,?)",
            (float(money(amount)), category.strip(), description.strip(), day))
        self.conn.commit()

    def generate_recurring(self, today=None):
        today = today or date.today()
        generated = 0
        for r in self.recurring():
            day = min(r["day_of_month"], calendar.monthrange(today.year, today.month)[1])
            due = date(today.year, today.month, day)
            marker = due.isoformat()
            if due <= today and r["last_generated"] != marker:
                exists = self.conn.execute(
                    "SELECT 1 FROM expenses WHERE recurring_id=? AND expense_date=?",
                    (r["id"], marker)).fetchone()
                if not exists:
                    self.add_expense(r["amount"], r["category"], r["description"], marker, r["id"])
                    generated += 1
                self.conn.execute("UPDATE recurring_expenses SET last_generated=? WHERE id=?", (marker, r["id"]))
        self.conn.commit()
        return generated

    def delete_expense(self, expense_id):
        self.conn.execute("DELETE FROM expenses WHERE id=?", (expense_id,))
        self.conn.commit()

    def export_month(self, year, month, folder=None):
        folder = Path(folder or EXPORT_DIR)
        folder.mkdir(parents=True, exist_ok=True)
        rows = self.expenses(year, month)
        prefix = folder / f"expenses_{year}-{month:02d}"
        detailed = prefix.with_suffix(".csv")
        with detailed.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["id", "date", "category", "description", "amount"])
            for r in rows:
                w.writerow([r["id"], r["expense_date"], r["category"], r["description"], f'{r["amount"]:.2f}'])
        summary = prefix.with_name(prefix.name + "_summary.csv")
        with summary.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["category", "total"])
            for cat, total in self.category_totals(year, month):
                w.writerow([cat, f"{total:.2f}"])
        return detailed, summary

    def close(self):
        self.conn.close()


class ExpenseTrackerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Expense Tracker v2")
        self.geometry("1100x720")
        self.minsize(950, 620)
        self.db = ExpenseDB()
        self.db.generate_recurring()
        self.year = date.today().year
        self.month = date.today().month
        self.style = ttk.Style(self)
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass
        self.build()
        self.refresh_all()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def build(self):
        top = ttk.Frame(self, padding=12)
        top.pack(fill="x")
        ttk.Label(top, text="EXPENSE TRACKER", font=("TkDefaultFont", 18, "bold")).pack(side="left")
        ttk.Label(top, text="v2 • SQLite dashboard").pack(side="left", padx=12)
        ttk.Button(top, text="Export Month", command=self.export).pack(side="right")
        ttk.Button(top, text="Reports", command=self.report).pack(side="right", padx=6)

        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True, padx=12, pady=(0,12))
        self.dashboard_tab = ttk.Frame(self.tabs, padding=12)
        self.expenses_tab = ttk.Frame(self.tabs, padding=12)
        self.budget_tab = ttk.Frame(self.tabs, padding=12)
        self.recurring_tab = ttk.Frame(self.tabs, padding=12)
        self.tabs.add(self.dashboard_tab, text="Dashboard")
        self.tabs.add(self.expenses_tab, text="Expenses")
        self.tabs.add(self.budget_tab, text="Budgets")
        self.tabs.add(self.recurring_tab, text="Recurring")

        self.build_dashboard()
        self.build_expenses()
        self.build_budgets()
        self.build_recurring()

    def build_dashboard(self):
        controls = ttk.Frame(self.dashboard_tab)
        controls.pack(fill="x")
        ttk.Button(controls, text="‹", width=3, command=lambda: self.shift_month(-1)).pack(side="left")
        self.period_label = ttk.Label(controls, text="", font=("TkDefaultFont", 13, "bold"))
        self.period_label.pack(side="left", padx=12)
        ttk.Button(controls, text="›", width=3, command=lambda: self.shift_month(1)).pack(side="left")
        ttk.Button(controls, text="Current", command=self.current_month).pack(side="left", padx=8)

        cards = ttk.Frame(self.dashboard_tab)
        cards.pack(fill="x", pady=15)
        self.card_total = self.card(cards, "Spent this month")
        self.card_avg = self.card(cards, "Daily average")
        self.card_count = self.card(cards, "Transactions")
        self.card_top = self.card(cards, "Top category")

        self.chart_frame = ttk.Frame(self.dashboard_tab)
        self.chart_frame.pack(fill="both", expand=True)

        self.budget_tree = ttk.Treeview(self.dashboard_tab, columns=("category","spent","limit","remaining"), show="headings", height=5)
        for c, h in zip(("category","spent","limit","remaining"), ("Category","Spent","Budget","Remaining")):
            self.budget_tree.heading(c, text=h)
            self.budget_tree.column(c, width=160)
        self.budget_tree.pack(fill="x", pady=(10,0))

    def card(self, parent, title):
        f = ttk.LabelFrame(parent, text=title, padding=12)
        f.pack(side="left", fill="x", expand=True, padx=4)
        label = ttk.Label(f, text="—", font=("TkDefaultFont", 16, "bold"))
        label.pack()
        return label

    def build_expenses(self):
        form = ttk.LabelFrame(self.expenses_tab, text="Add expense", padding=10)
        form.pack(fill="x")
        self.amount_var = tk.StringVar()
        self.category_var = tk.StringVar()
        self.description_var = tk.StringVar()
        self.date_var = tk.StringVar(value=date.today().isoformat())
        for i, (label, var) in enumerate([
            ("Amount", self.amount_var), ("Category", self.category_var),
            ("Description", self.description_var), ("Date", self.date_var)]):
            ttk.Label(form, text=label).grid(row=0,column=i*2,padx=5,sticky="w")
            ttk.Entry(form, textvariable=var, width=18).grid(row=1,column=i*2,padx=5)
        ttk.Button(form, text="Add", command=self.add_expense).grid(row=1,column=8,padx=8)
        ttk.Button(form, text="Delete selected", command=self.delete_selected).grid(row=1,column=9)

        self.exp_tree = ttk.Treeview(self.expenses_tab, columns=("id","date","category","description","amount"), show="headings")
        for c,h,w in [("id","ID",55),("date","Date",110),("category","Category",130),("description","Description",430),("amount","Amount",110)]:
            self.exp_tree.heading(c,text=h); self.exp_tree.column(c,width=w)
        self.exp_tree.pack(fill="both",expand=True,pady=12)

    def build_budgets(self):
        form = ttk.LabelFrame(self.budget_tab, text="Monthly category budget", padding=10)
        form.pack(fill="x")
        self.budget_cat = tk.StringVar()
        self.budget_limit = tk.StringVar()
        ttk.Label(form,text="Category").grid(row=0,column=0); ttk.Entry(form,textvariable=self.budget_cat).grid(row=1,column=0,padx=5)
        ttk.Label(form,text="Limit").grid(row=0,column=1); ttk.Entry(form,textvariable=self.budget_limit).grid(row=1,column=1,padx=5)
        ttk.Button(form,text="Save budget",command=self.save_budget).grid(row=1,column=2,padx=8)
        ttk.Label(self.budget_tab,text="Budgets apply every month and are shown on the dashboard.").pack(anchor="w",pady=10)
        self.budget_list = ttk.Treeview(self.budget_tab,columns=("category","limit"),show="headings")
        self.budget_list.heading("category",text="Category"); self.budget_list.heading("limit",text="Monthly limit")
        self.budget_list.pack(fill="x")

    def build_recurring(self):
        form = ttk.LabelFrame(self.recurring_tab, text="Recurring expense", padding=10)
        form.pack(fill="x")
        self.rec_amount=tk.StringVar(); self.rec_cat=tk.StringVar(); self.rec_desc=tk.StringVar(); self.rec_day=tk.StringVar(value="1")
        for i,(label,var) in enumerate([("Amount",self.rec_amount),("Category",self.rec_cat),("Description",self.rec_desc),("Day",self.rec_day)]):
            ttk.Label(form,text=label).grid(row=0,column=i*2,padx=5); ttk.Entry(form,textvariable=var,width=18).grid(row=1,column=i*2,padx=5)
        ttk.Button(form,text="Add recurring",command=self.add_recurring).grid(row=1,column=8,padx=8)
        ttk.Label(self.recurring_tab,text="Due recurring expenses are automatically created when the app starts.").pack(anchor="w",pady=10)
        self.rec_tree=ttk.Treeview(self.recurring_tab,columns=("amount","category","description","day"),show="headings")
        for c,h in [("amount","Amount"),("category","Category"),("description","Description"),("day","Day")]:
            self.rec_tree.heading(c,text=h)
        self.rec_tree.pack(fill="both",expand=True)

    def shift_month(self, delta):
        m = self.month + delta
        y = self.year + (m-1)//12
        self.year, self.month = y, (m-1)%12+1
        self.refresh_all()

    def current_month(self):
        d=date.today(); self.year,self.month=d.year,d.month; self.refresh_all()

    def add_expense(self):
        try:
            self.db.add_expense(Decimal(self.amount_var.get()), self.category_var.get(), self.description_var.get(), self.date_var.get())
            self.amount_var.set(""); self.category_var.set(""); self.description_var.set("")
            self.refresh_all()
        except (ValueError, InvalidOperation) as e:
            messagebox.showerror("Invalid expense", str(e))

    def delete_selected(self):
        selected=self.exp_tree.selection()
        if not selected: return
        if not messagebox.askyesno("Delete", "Delete selected expense?"): return
        for item in selected:
            self.db.delete_expense(self.exp_tree.item(item)["values"][0])
        self.refresh_all()

    def save_budget(self):
        try:
            self.db.set_budget(self.budget_cat.get(), Decimal(self.budget_limit.get()))
            self.budget_cat.set(""); self.budget_limit.set(""); self.refresh_all()
        except (ValueError, InvalidOperation) as e:
            messagebox.showerror("Invalid budget", str(e))

    def add_recurring(self):
        try:
            self.db.add_recurring(Decimal(self.rec_amount.get()),self.rec_cat.get(),self.rec_desc.get(),int(self.rec_day.get()))
            self.rec_amount.set(""); self.rec_cat.set(""); self.rec_desc.set(""); self.rec_day.set("1")
            self.db.generate_recurring(); self.refresh_all()
        except (ValueError, InvalidOperation) as e:
            messagebox.showerror("Invalid recurring expense", str(e))

    def refresh_all(self):
        total=self.db.monthly_total(self.year,self.month)
        categories=self.db.category_totals(self.year,self.month)
        days=calendar.monthrange(self.year,self.month)[1]
        self.period_label.config(text=f"{calendar.month_name[self.month]} {self.year}")
        self.card_total.config(text=f"{CURRENCY}{total:,.2f}")
        self.card_avg.config(text=f"{CURRENCY}{(total/days):,.2f}")
        self.card_count.config(text=str(len(self.db.expenses(self.year,self.month))))
        self.card_top.config(text=categories[0][0] if categories else "—")
        for item in self.exp_tree.get_children(): self.exp_tree.delete(item)
        for r in self.db.expenses(self.year,self.month):
            self.exp_tree.insert("", "end", values=(r["id"],r["expense_date"],r["category"],r["description"],f'{CURRENCY}{r["amount"]:,.2f}'))
        for item in self.budget_list.get_children(): self.budget_list.delete(item)
        for r in self.db.budgets(): self.budget_list.insert("", "end", values=(r["category"],f'{CURRENCY}{r["monthly_limit"]:,.2f}'))
        for item in self.rec_tree.get_children(): self.rec_tree.delete(item)
        for r in self.db.recurring(): self.rec_tree.insert("", "end", values=(f'{CURRENCY}{r["amount"]:,.2f}',r["category"],r["description"],r["day_of_month"]))
        self.refresh_budget_table(categories)
        self.draw_chart(categories)

    def refresh_budget_table(self, categories):
        for item in self.budget_tree.get_children(): self.budget_tree.delete(item)
        spent=dict(categories)
        for r in self.db.budgets():
            s=spent.get(r["category"],Decimal("0")); limit=money(r["monthly_limit"]); remaining=limit-s
            self.budget_tree.insert("", "end", values=(r["category"],f'{CURRENCY}{s:,.2f}',f'{CURRENCY}{limit:,.2f}',f'{CURRENCY}{remaining:,.2f}'))

    def draw_chart(self,categories):
        for w in self.chart_frame.winfo_children(): w.destroy()
        if Figure is None:
            ttk.Label(self.chart_frame,text="Install requirements.txt to enable charts.").pack(pady=40); return
        fig=Figure(figsize=(7,3.2),dpi=100)
        ax=fig.add_subplot(111)
        labels=[x[0] for x in categories][:8]; values=[float(x[1]) for x in categories][:8]
        if labels:
            ax.bar(labels,values)
            ax.set_title("Spending by category")
            ax.set_ylabel("Amount")
            ax.tick_params(axis="x",rotation=25)
        else:
            ax.text(.5,.5,"No expenses for this month",ha="center",va="center")
            ax.axis("off")
        fig.tight_layout()
        canvas=FigureCanvasTkAgg(fig,master=self.chart_frame); canvas.draw(); canvas.get_tk_widget().pack(fill="both",expand=True)

    def export(self):
        try:
            detailed,summary=self.db.export_month(self.year,self.month)
            messagebox.showinfo("Export complete",f"Created:\n{detailed}\n{summary}")
        except OSError as e: messagebox.showerror("Export failed",str(e))

    def report(self):
        rows=self.db.expenses(self.year,self.month); total=self.db.monthly_total(self.year,self.month)
        categories=self.db.category_totals(self.year,self.month)
        EXPORT_DIR.mkdir(exist_ok=True)
        path=EXPORT_DIR/f"report_{self.year}-{self.month:02d}.json"
        data={"month":f"{self.year}-{self.month:02d}","total":f"{total:.2f}","transactions":len(rows),
              "daily_average":f"{(total/calendar.monthrange(self.year,self.month)[1]):.2f}",
              "categories":[{"category":c,"total":f"{v:.2f}"} for c,v in categories]}
        path.write_text(json.dumps(data,indent=2),encoding="utf-8")
        messagebox.showinfo("Report created",str(path))

    def on_close(self):
        self.db.close(); self.destroy()


def main():
    app=ExpenseTrackerApp()
    app.mainloop()


if __name__=="__main__":
    main()
