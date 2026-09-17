#!/usr/bin/env python3
"""Expense Tracker v3 - full-featured desktop expense manager."""
import csv, json, sqlite3, calendar
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

try:
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
except ImportError:
    Figure = FigureCanvasTkAgg = None

BASE = Path(__file__).resolve().parent
DB_FILE = BASE / "expenses.db"
EXPORT_DIR = BASE / "exports"
LEGACY = BASE / "expenses.csv"
CATEGORIES = ["Food","Transport","Shopping","Bills","Entertainment","Health","Education","Travel","Other"]

def money(v): return Decimal(str(v)).quantize(Decimal("0.01"))
def ym(y,m): return f"{y:04d}-{m:02d}"

class DB:
    def __init__(self, path=DB_FILE):
        self.conn=sqlite3.connect(path); self.conn.row_factory=sqlite3.Row
        self.conn.executescript("""
        PRAGMA foreign_keys=ON;
        CREATE TABLE IF NOT EXISTS expenses(id INTEGER PRIMARY KEY,amount REAL NOT NULL CHECK(amount>0),category TEXT NOT NULL,description TEXT NOT NULL,expense_date TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP,recurring_id INTEGER);
        CREATE TABLE IF NOT EXISTS budgets(id INTEGER PRIMARY KEY,category TEXT UNIQUE NOT NULL,monthly_limit REAL NOT NULL CHECK(monthly_limit>=0));
        CREATE TABLE IF NOT EXISTS recurring_expenses(id INTEGER PRIMARY KEY,amount REAL NOT NULL,category TEXT NOT NULL,description TEXT NOT NULL,day_of_month INTEGER NOT NULL,active INTEGER DEFAULT 1,last_generated TEXT);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_exp_date ON expenses(expense_date);
        """); self.conn.commit(); self.migrate()

    def migrate(self):
        if self.conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0] or not LEGACY.exists(): return
        try:
            with LEGACY.open(newline="",encoding="utf-8") as f:
                for r in csv.DictReader(f): self.add(r["amount"],r["category"],r["description"],r["date"])
        except Exception: pass

    def add(self,a,c,d,dt=None,rid=None):
        a=money(a); c=c.strip(); d=d.strip()
        if a<=0 or not c or not d: raise ValueError("Amount must be positive and category/description are required.")
        dt=dt or date.today().isoformat()
        if isinstance(dt,date): dt=dt.isoformat()
        cur=self.conn.execute("INSERT INTO expenses(amount,category,description,expense_date,recurring_id) VALUES(?,?,?,?,?)",(float(a),c,d,dt,rid))
        self.conn.commit(); return cur.lastrowid

    def expenses(self,y=None,m=None,search="",category="All"):
        q="SELECT * FROM expenses WHERE 1=1"; p=[]
        if y: q+=" AND strftime('%Y',expense_date)=?"; p.append(str(y))
        if m: q+=" AND strftime('%m',expense_date)=?"; p.append(f"{m:02d}")
        if category!="All": q+=" AND category=?"; p.append(category)
        if search: q+=" AND (description LIKE ? OR category LIKE ?)"; p += [f"%{search}%",f"%{search}%"]
        return self.conn.execute(q+" ORDER BY expense_date DESC,id DESC",p).fetchall()

    def total(self,y,m):
        return money(self.conn.execute("SELECT COALESCE(SUM(amount),0) FROM expenses WHERE strftime('%Y-%m',expense_date)=?",(ym(y,m),)).fetchone()[0])
    def categories(self,y,m):
        return [(r["category"],money(r["total"])) for r in self.conn.execute("SELECT category,SUM(amount) total FROM expenses WHERE strftime('%Y-%m',expense_date)=? GROUP BY category ORDER BY total DESC",(ym(y,m),))]
    def daily(self,y,m):
        return [(r["day"],money(r["total"])) for r in self.conn.execute("SELECT substr(expense_date,9,2) day,SUM(amount) total FROM expenses WHERE strftime('%Y-%m',expense_date)=? GROUP BY day ORDER BY day",(ym(y,m),))]
    def monthly_series(self,y,m,n=6):
        out=[]; yy,mm=y,m
        for _ in range(n-1,-1,-1):
            mm2=mm-_; yy2=yy
            while mm2<=0: mm2+=12; yy2-=1
            out.append((ym(yy2,mm2),self.total(yy2,mm2)))
        return out
    def budgets(self): return self.conn.execute("SELECT * FROM budgets ORDER BY category").fetchall()
    def budget(self,c,l):
        l=money(l)
        if not c.strip() or l<0: raise ValueError("Enter a category and a non-negative limit.")
        self.conn.execute("INSERT INTO budgets(category,monthly_limit) VALUES(?,?) ON CONFLICT(category) DO UPDATE SET monthly_limit=excluded.monthly_limit",(c.strip(),float(l))); self.conn.commit()
    def delete_budget(self,i): self.conn.execute("DELETE FROM budgets WHERE id=?",(i,)); self.conn.commit()
    def recurring(self,all_rows=False):
        q="SELECT * FROM recurring_expenses"+("" if all_rows else " WHERE active=1")+" ORDER BY active DESC,day_of_month,category"
        return self.conn.execute(q).fetchall()
    def add_rec(self,a,c,d,day):
        day=int(day); a=money(a)
        if not 1<=day<=31 or a<=0 or not c.strip() or not d.strip(): raise ValueError("Enter valid amount, category, description and day 1-31.")
        self.conn.execute("INSERT INTO recurring_expenses(amount,category,description,day_of_month) VALUES(?,?,?,?)",(float(a),c.strip(),d.strip(),day)); self.conn.commit()
    def update_rec(self,i,a,c,d,day,active):
        self.conn.execute("UPDATE recurring_expenses SET amount=?,category=?,description=?,day_of_month=?,active=? WHERE id=?",(float(money(a)),c.strip(),d.strip(),int(day),int(active),i)); self.conn.commit()
    def delete_rec(self,i): self.conn.execute("DELETE FROM recurring_expenses WHERE id=?",(i,)); self.conn.commit()
    def generate(self,today=None):
        today=today or date.today(); n=0
        for r in self.recurring():
            day=min(r["day_of_month"],calendar.monthrange(today.year,today.month)[1]); due=date(today.year,today.month,day).isoformat()
            if due<=today.isoformat() and r["last_generated"]!=due:
                if not self.conn.execute("SELECT 1 FROM expenses WHERE recurring_id=? AND expense_date=?",(r["id"],due)).fetchone():
                    self.add(r["amount"],r["category"],r["description"],due,r["id"]); n+=1
                self.conn.execute("UPDATE recurring_expenses SET last_generated=? WHERE id=?",(due,r["id"]))
        self.conn.commit(); return n
    def setting(self,k,default=""):
        r=self.conn.execute("SELECT value FROM settings WHERE key=?",(k,)).fetchone(); return r["value"] if r else default
    def set_setting(self,k,v):
        self.conn.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(k,str(v))); self.conn.commit()
    def delete_expense(self,i): self.conn.execute("DELETE FROM expenses WHERE id=?",(i,)); self.conn.commit()
    def export(self,y,m,folder,fmt="csv"):
        rows=self.expenses(y,m); folder=Path(folder); folder.mkdir(parents=True,exist_ok=True); prefix=folder/f"expenses_{ym(y,m)}"
        if fmt=="xlsx":
            try:
                from openpyxl import Workbook
            except ImportError: raise RuntimeError("Install openpyxl with: python -m pip install openpyxl")
            wb=Workbook(); ws=wb.active; ws.title="Expenses"; ws.append(["ID","Date","Category","Description","Amount"])
            for r in rows: ws.append([r["id"],r["expense_date"],r["category"],r["description"],r["amount"]])
            s=wb.create_sheet("Summary"); s.append(["Category","Total"])
            for c,t in self.categories(y,m): s.append([c,float(t)])
            path=prefix.with_suffix(".xlsx"); wb.save(path); return [path]
        p=prefix.with_suffix(".csv")
        with p.open("w",newline="",encoding="utf-8") as f:
            w=csv.writer(f); w.writerow(["id","date","category","description","amount"])
            for r in rows: w.writerow([r["id"],r["expense_date"],r["category"],r["description"],f'{r["amount"]:.2f}'])
        s=prefix.with_name(prefix.name+"_summary.csv")
        with s.open("w",newline="",encoding="utf-8") as f:
            w=csv.writer(f); w.writerow(["category","total"])
            for c,t in self.categories(y,m): w.writerow([c,f"{t:.2f}"])
        return [p,s]

class App(tk.Tk):
    def __init__(self):
        super().__init__(); self.title("Expense Tracker v3"); self.geometry("1250x820"); self.minsize(1050,700)
        self.db=DB(); generated=self.db.generate(); self.y,self.m=date.today().year,date.today().month
        self.cur=self.db.setting("currency","$"); self.build(); self.refresh()
        if generated: self.after(300,lambda:messagebox.showinfo("Recurring expenses",f"{generated} recurring expense(s) were added automatically."))
        self.protocol("WM_DELETE_WINDOW",lambda:(self.db.conn.close(),self.destroy()))

    def money(self,v): return f"{self.cur}{Decimal(str(v)):,.2f}"
    def build(self):
        head=ttk.Frame(self,padding=12); head.pack(fill="x")
        ttk.Label(head,text="EXPENSE TRACKER",font=("TkDefaultFont",20,"bold")).pack(side="left")
        ttk.Label(head,text="v3 • Smart personal finance dashboard").pack(side="left",padx=15)
        ttk.Button(head,text="Settings",command=self.settings).pack(side="right")
        ttk.Button(head,text="Export",command=self.export).pack(side="right",padx=6)
        ttk.Button(head,text="Report",command=self.report).pack(side="right",padx=6)
        self.nb=ttk.Notebook(self); self.nb.pack(fill="both",expand=True,padx=12,pady=(0,12))
        self.dash=ttk.Frame(self.nb,padding=12); self.expt=ttk.Frame(self.nb,padding=12); self.bud=ttk.Frame(self.nb,padding=12); self.rec=ttk.Frame(self.nb,padding=12)
        for tab,name in [(self.dash,"Dashboard"),(self.expt,"Expenses"),(self.bud,"Budgets"),(self.rec,"Recurring")]: self.nb.add(tab,text=name)
        self.build_dash(); self.build_expenses(); self.build_budgets(); self.build_recurring()

    def build_dash(self):
        bar=ttk.Frame(self.dash); bar.pack(fill="x")
        ttk.Button(bar,text="‹",width=3,command=lambda:self.move(-1)).pack(side="left")
        self.period=ttk.Label(bar,font=("TkDefaultFont",14,"bold")); self.period.pack(side="left",padx=12)
        ttk.Button(bar,text="›",width=3,command=lambda:self.move(1)).pack(side="left")
        ttk.Button(bar,text="Current",command=self.current).pack(side="left",padx=8)
        self.cards=ttk.Frame(self.dash); self.cards.pack(fill="x",pady=12)
        self.c_total=self.card("Spent"); self.c_avg=self.card("Daily average"); self.c_prev=self.card("vs previous month"); self.c_top=self.card("Top category")
        self.chart=ttk.Frame(self.dash); self.chart.pack(fill="both",expand=True)
        self.insight=ttk.Label(self.dash,text="",wraplength=1000,justify="left"); self.insight.pack(fill="x",pady=8)

    def card(self,title):
        f=ttk.LabelFrame(self.cards,text=title,padding=12); f.pack(side="left",fill="x",expand=True,padx=4)
        l=ttk.Label(f,text="—",font=("TkDefaultFont",16,"bold")); l.pack(); return l

    def build_expenses(self):
        f=ttk.LabelFrame(self.expt,text="Add expense",padding=10); f.pack(fill="x")
        self.av,self.cv,self.dv,self.datev=[tk.StringVar() for _ in range(4)]; self.datev.set(date.today().isoformat())
        for i,(lab,var) in enumerate([("Amount",self.av),("Category",self.cv),("Description",self.dv),("Date",self.datev)]):
            ttk.Label(f,text=lab).grid(row=0,column=i*2,sticky="w"); ttk.Entry(f,textvariable=var,width=20).grid(row=1,column=i*2,padx=5)
        ttk.Button(f,text="Add",command=self.add_exp).grid(row=1,column=8)
        filt=ttk.Frame(self.expt); filt.pack(fill="x",pady=8)
        self.search=tk.StringVar(); self.filtercat=tk.StringVar(value="All")
        ttk.Label(filt,text="Search").pack(side="left"); ttk.Entry(filt,textvariable=self.search,width=25).pack(side="left",padx=5)
        ttk.Label(filt,text="Category").pack(side="left"); ttk.Combobox(filt,textvariable=self.filtercat,values=["All"]+CATEGORIES,state="readonly",width=16).pack(side="left",padx=5)
        ttk.Button(filt,text="Filter",command=self.refresh_expenses).pack(side="left")
        ttk.Button(filt,text="Clear",command=self.clear_filter).pack(side="left",padx=5)
        ttk.Button(filt,text="Delete selected",command=self.delete_exp).pack(side="right")
        self.et=tk.Treeview(self.expt,columns=("id","date","category","description","amount"),show="headings")
        for c,h,w in [("id","ID",55),("date","Date",110),("category","Category",140),("description","Description",500),("amount","Amount",120)]:
            self.et.heading(c,text=h); self.et.column(c,width=w)
        self.et.pack(fill="both",expand=True)

    def build_budgets(self):
        f=ttk.Frame(self.bud); f.pack(fill="x")
        self.bc,self.bl=tk.StringVar(),tk.StringVar()
        ttk.Label(f,text="Category").grid(row=0,column=0); ttk.Entry(f,textvariable=self.bc).grid(row=1,column=0,padx=5)
        ttk.Label(f,text="Monthly limit").grid(row=0,column=1); ttk.Entry(f,textvariable=self.bl).grid(row=1,column=1,padx=5)
        ttk.Button(f,text="Save / update",command=self.save_budget).grid(row=1,column=2)
        ttk.Button(f,text="Delete selected",command=self.del_budget).grid(row=1,column=3,padx=5)
        self.bt=ttk.Treeview(self.bud,columns=("id","category","limit","spent","remaining","status"),show="headings")
        for c,h in [("id","ID"),("category","Category"),("limit","Budget"),("spent","Spent"),("remaining","Remaining"),("status","Status")]: self.bt.heading(c,text=h)
        self.bt.pack(fill="both",expand=True,pady=12)

    def build_recurring(self):
        f=ttk.Frame(self.rec); f.pack(fill="x")
        self.ra,self.rc,self.rd,self.rday=[tk.StringVar() for _ in range(4)]
        for i,(lab,var) in enumerate([("Amount",self.ra),("Category",self.rc),("Description",self.rd),("Day 1-31",self.rday)]):
            ttk.Label(f,text=lab).grid(row=0,column=i*2); ttk.Entry(f,textvariable=var,width=18).grid(row=1,column=i*2,padx=5)
        ttk.Button(f,text="Add recurring",command=self.add_rec).grid(row=1,column=8)
        ttk.Button(f,text="Toggle active",command=self.toggle_rec).grid(row=1,column=9,padx=5)
        ttk.Button(f,text="Delete",command=self.del_rec).grid(row=1,column=10)
        self.rt=ttk.Treeview(self.rec,columns=("id","amount","category","description","day","active","last"),show="headings")
        for c,h in [("id","ID"),("amount","Amount"),("category","Category"),("description","Description"),("day","Day"),("active","Active"),("last","Last generated")]: self.rt.heading(c,text=h)
        self.rt.pack(fill="both",expand=True,pady=12)

    def move(self,d):
        self.m+=d
        if self.m<1:self.m=12;self.y-=1
        if self.m>12:self.m=1;self.y+=1
        self.refresh()
    def current(self): self.y,self.m=date.today().year,date.today().month; self.refresh()
    def add_exp(self):
        try:self.db.add(self.av.get(),self.cv.get(),self.dv.get(),self.datev.get()); [v.set("") for v in (self.av,self.cv,self.dv)]; self.refresh()
        except (ValueError,InvalidOperation) as e: messagebox.showerror("Invalid expense",str(e))
    def refresh_expenses(self):
        for x in self.et.get_children(): self.et.delete(x)
        for r in self.db.expenses(self.y,self.m,self.search.get(),self.filtercat.get()):
            self.et.insert("","end",values=(r["id"],r["expense_date"],r["category"],r["description"],self.money(r["amount"])))
    def clear_filter(self): self.search.set(""); self.filtercat.set("All"); self.refresh_expenses()
    def delete_exp(self):
        for x in self.et.selection():
            if messagebox.askyesno("Delete","Delete selected expense?"): self.db.delete_expense(self.et.item(x)["values"][0])
        self.refresh()
    def save_budget(self):
        try:self.db.budget(self.bc.get(),self.bl.get()); self.bc.set("");self.bl.set("");self.refresh()
        except (ValueError,InvalidOperation) as e: messagebox.showerror("Budget",str(e))
    def del_budget(self):
        for x in self.bt.selection(): self.db.delete_budget(self.bt.item(x)["values"][0])
        self.refresh()
    def add_rec(self):
        try:self.db.add_rec(self.ra.get(),self.rc.get(),self.rd.get(),self.rday.get()); [v.set("") for v in (self.ra,self.rc,self.rd,self.rday)]; self.db.generate();self.refresh()
        except (ValueError,InvalidOperation) as e: messagebox.showerror("Recurring",str(e))
    def toggle_rec(self):
        for x in self.rt.selection():
            r=self.rt.item(x)["values"]; row=next(z for z in self.db.recurring(True) if z["id"]==r[0]); self.db.update_rec(row["id"],row["amount"],row["category"],row["description"],row["day_of_month"],not row["active"])
        self.refresh()
    def del_rec(self):
        for x in self.rt.selection(): self.db.delete_rec(self.rt.item(x)["values"][0])
        self.refresh()

    def refresh(self):
        self.period.config(text=f"{calendar.month_name[self.m]} {self.y}")
        total=self.db.total(self.y,self.m); prev_m=self.m-1; prev_y=self.y
        if prev_m==0: prev_m=12;prev_y-=1
        prev=self.db.total(prev_y,prev_m); diff=total-prev
        self.c_total.config(text=self.money(total))
        self.c_avg.config(text=self.money(total/calendar.monthrange(self.y,self.m)[1]))
        self.c_prev.config(text=("+" if diff>=0 else "")+self.money(diff))
        cats=self.db.categories(self.y,self.m); self.c_top.config(text=cats[0][0] if cats else "—")
        if cats:
            top=cats[0]; self.insight.config(text=f"Insights: {top[0]} is your largest category at {self.money(top[1])}. "+(f"Spending is {self.money(abs(diff))} higher than last month." if diff>0 else f"Spending is {self.money(abs(diff))} lower than last month." if diff<0 else "Spending matches last month."))
        else:self.insight.config(text="Insights: no expenses recorded for this month yet.")
        self.refresh_expenses(); self.refresh_budgets(); self.refresh_recurring(); self.draw_charts(cats)

    def refresh_budgets(self):
        for x in self.bt.get_children(): self.bt.delete(x)
        spent=dict(self.db.categories(self.y,self.m))
        for r in self.db.budgets():
            rem=money(r["monthly_limit"])-spent.get(r["category"],Decimal("0")); status="OVER BUDGET" if rem<0 else "OK"
            self.bt.insert("","end",values=(r["id"],r["category"],self.money(r["monthly_limit"]),self.money(spent.get(r["category"],0)),self.money(rem),status))
    def refresh_recurring(self):
        for x in self.rt.get_children(): self.rt.delete(x)
        for r in self.db.recurring(True): self.rt.insert("","end",values=(r["id"],self.money(r["amount"]),r["category"],r["description"],r["day_of_month"],"Yes" if r["active"] else "No",r["last_generated"] or "Never"))

    def draw_charts(self,cats):
        for w in self.chart.winfo_children(): w.destroy()
        if Figure is None:
            ttk.Label(self.chart,text="Charts require matplotlib. Run: python -m pip install -r requirements.txt").pack(pady=40); return
        fig=Figure(figsize=(10,4),dpi=90)
        a=fig.add_subplot(121); labels=[x[0] for x in cats]; vals=[float(x[1]) for x in cats]
        if labels: a.bar(labels,vals); a.set_title("Spending by category"); a.tick_params(axis="x",rotation=35)
        else:a.text(.5,.5,"No category data",ha="center");a.axis("off")
        b=fig.add_subplot(122); series=self.db.monthly_series(self.y,self.m,6); b.plot([x[0] for x in series],[float(x[1]) for x in series],marker="o"); b.set_title("Six-month trend"); b.tick_params(axis="x",rotation=35)
        fig.tight_layout(); c=FigureCanvasTkAgg(fig,master=self.chart); c.draw(); c.get_tk_widget().pack(fill="both",expand=True)

    def export(self):
        fmt=tk.StringVar(value="csv")
        win=tk.Toplevel(self);win.title("Export");win.transient(self);win.grab_set()
        ttk.Label(win,text=f"Export {calendar.month_name[self.m]} {self.y}").pack(padx=20,pady=12)
        ttk.Radiobutton(win,text="CSV (detailed + summary)",variable=fmt,value="csv").pack(anchor="w",padx=20)
        ttk.Radiobutton(win,text="Excel workbook (.xlsx)",variable=fmt,value="xlsx").pack(anchor="w",padx=20)
        def go():
            try:
                paths=self.db.export(self.y,self.m,EXPORT_DIR,fmt.get()); win.destroy(); messagebox.showinfo("Export complete","Created:\\n" + "\\n".join(map(str,paths)))
            except Exception as e: messagebox.showerror("Export failed",str(e))
        ttk.Button(win,text="Export",command=go).pack(pady=15)

    def report(self):
        total=self.db.total(self.y,self.m); cats=self.db.categories(self.y,self.m)
        days=calendar.monthrange(self.y,self.m)[1]; prev_m=self.m-1; prev_y=self.y
        if prev_m==0: prev_m=12; prev_y-=1
        prev=self.db.total(prev_y,prev_m)
        data={"month":ym(self.y,self.m),"total":f"{total:.2f}","transactions":len(self.db.expenses(self.y,self.m)),
              "daily_average":f"{(total/days):.2f}","previous_month_total":f"{prev:.2f}",
              "change":f"{(total-prev):.2f}","categories":[{"category":c,"total":f"{v:.2f}"} for c,v in cats]}
        EXPORT_DIR.mkdir(parents=True,exist_ok=True); path=EXPORT_DIR/f"report_{ym(self.y,self.m)}.json"
        path.write_text(json.dumps(data,indent=2),encoding="utf-8")
        messagebox.showinfo("Report created",f"Created:\n{path}")

    def settings(self):
        win=tk.Toplevel(self);win.title("Settings");win.transient(self);win.grab_set()
        v=tk.StringVar(value=self.cur)
        ttk.Label(win,text="Currency symbol").pack(padx=20,pady=(20,4)); ttk.Entry(win,textvariable=v,width=10).pack()
        def save():
            self.cur=v.get().strip() or "$"; self.db.set_setting("currency",self.cur); win.destroy(); self.refresh()
        ttk.Button(win,text="Save",command=save).pack(pady=15)

def main(): App().mainloop()
if __name__=="__main__": main()
