from datetime import date
from decimal import Decimal
from expense_tracker import DB, money

def test_add_and_totals(tmp_path):
    db=DB(tmp_path/"x.db"); db.add("10.50","Food","Lunch",date(2026,9,2)); db.add("5","Food","Coffee",date(2026,9,3))
    assert db.total(2026,9)==Decimal("15.50"); assert db.categories(2026,9)==[("Food",Decimal("15.50"))]

def test_budget_and_recurring(tmp_path):
    db=DB(tmp_path/"x.db"); db.budget("Food","200"); assert db.budgets()[0]["monthly_limit"]==200
    db.add_rec("50","Bills","Internet",10); assert db.generate(date(2026,9,10))==1; assert db.generate(date(2026,9,10))==0
    assert db.total(2026,9)==Decimal("50.00")

def test_search_and_series(tmp_path):
    db=DB(tmp_path/"x.db"); db.add("25","Travel","Airport",date(2026,9,2))
    assert len(db.expenses(2026,9,"Airport"))==1
    assert len(db.monthly_series(2026,9,6))==6
    assert money("12.345")==Decimal("12.35")
