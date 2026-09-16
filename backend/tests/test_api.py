from fastapi.testclient import TestClient
from time import sleep
from uuid import uuid4
from datetime import date, timedelta
from app.main import app, SessionLocal, User, Category, Transaction, period_bounds, comparison_period_bounds, compare_values, custom_period_bounds
client=TestClient(app)
def account(email):
 r=client.post('/api/auth/register',json={'email':email,'name':'Test','password':'password123'}); assert r.status_code==201
 return {'Authorization':'Bearer '+r.json()['access_token']}
def unique_email(prefix):
 return f'{prefix}-{uuid4().hex}@example.com'
def test_health(): assert client.get('/api/health').json()['status']=='ok'
def summary(headers,period='month'):
 response=client.get('/api/financial-summary',headers=headers,params={'period':period})
 assert response.status_code==200
 return response.json()
def create_summary_tx(headers,kind,amount,when='2026-09-15',title='Summary transaction',category_id=None):
 response=client.post('/api/transactions',headers=headers,json={'title':title,'amount':amount,'type':kind,'date':when,'category_id':category_id})
 assert response.status_code==201
 return response.json()
def spending(headers,period='month'):
 response=client.get('/api/spending-analytics',headers=headers,params={'period':period})
 assert response.status_code==200
 return response.json()
def test_financial_summary_requires_authentication_and_returns_empty_zero_state():
 assert client.get('/api/financial-summary').status_code==401
 headers=account(unique_email('summary-empty'))
 result=summary(headers)
 assert result['balance']==result['period_income']==result['period_expenses']==result['net_savings']==result['transaction_count']==0
 assert result['comparison']['income']['change_percent']==0
 assert client.get('/api/financial-summary',headers=headers,params={'period':'invalid'}).status_code==422
def test_financial_summary_calculates_income_expenses_savings_rate_and_count():
 headers=account(unique_email('summary-metrics'))
 create_summary_tx(headers,'income',1000,'2026-09-01','Salary')
 create_summary_tx(headers,'income',500,'2026-09-10','Freelance')
 expense=create_summary_tx(headers,'expense',300,'2026-09-12','Food')
 create_summary_tx(headers,'expense',100,'2026-08-31','Outside period')
 result=summary(headers)
 assert result['balance']==1100.0
 assert result['period_income']==1500.0
 assert result['period_expenses']==300.0
 assert result['net_savings']==1200.0
 assert result['savings_rate']==80.0
 assert result['transaction_count']==3
 assert summary(headers,'week')['transaction_count']==0
 assert expense['type']=='expense'
def test_financial_summary_zero_income_rate_and_periods():
 headers=account(unique_email('summary-zero-income'))
 create_summary_tx(headers,'expense',250,'2026-09-15')
 assert summary(headers)['savings_rate']==0
 assert summary(headers,'year')['period_expenses']==250.0
 assert summary(headers,'year')['transaction_count']==1
def test_period_bounds_use_current_calendar_periods():
 today=date(2026,9,15)
 assert period_bounds('week',today)==(date(2026,9,14),today)
 assert period_bounds('month',today)==(date(2026,9,1),today)
 assert period_bounds('year',today)==(date(2026,1,1),today)
def test_comparison_period_bounds_and_zero_rules():
 today=date(2026,9,15)
 assert comparison_period_bounds('week',today)==(date(2026,9,14),date(2026,9,15),date(2026,9,7),date(2026,9,8))
 assert comparison_period_bounds('month',today)==(date(2026,9,1),today,date(2026,8,1),date(2026,8,15))
 assert comparison_period_bounds('year',today)==(date(2026,1,1),today,date(2025,1,1),date(2025,9,15))
 assert comparison_period_bounds('month',date(2026,3,31))[3]==date(2026,2,28)
 assert comparison_period_bounds('year',date(2028,2,29))[3]==date(2027,2,28)
 assert compare_values(600,500)=={'current':600,'previous':500,'change_amount':100,'change_percent':20.0}
 assert compare_values(0,500)['change_percent']==-100.0
 assert compare_values(0,0)['change_percent']==0
 assert compare_values(500,0)['change_percent'] is None
 assert compare_values(-250,-500)['change_percent'] is None
def test_custom_period_bounds_use_equal_length_previous_range():
 assert custom_period_bounds(date(2026,9,1),date(2026,9,15))==(date(2026,9,1),date(2026,9,15),date(2026,8,17),date(2026,8,31))
 assert custom_period_bounds(date(2026,9,10),date(2026,9,10))==(date(2026,9,10),date(2026,9,10),date(2026,9,9),date(2026,9,9))
 assert custom_period_bounds(date(2026,2,28),date(2026,3,1))[2:]==(date(2026,2,26),date(2026,2,27))
def test_custom_range_endpoints_validate_and_fill_daily_trend():
 headers=account(unique_email('custom-range'))
 create_summary_tx(headers,'income',100,'2026-09-01','Start income')
 create_summary_tx(headers,'expense',40,'2026-09-03','Expense')
 create_summary_tx(headers,'expense',60,'2026-09-05','End expense')
 params={'start_date':'2026-09-01','end_date':'2026-09-05'}
 summary_result=client.get('/api/financial-summary',headers=headers,params=params)
 spending_result=client.get('/api/spending-analytics',headers=headers,params=params)
 analytics_result=client.get('/api/analytics',headers=headers,params=params)
 assert summary_result.status_code==spending_result.status_code==analytics_result.status_code==200
 assert summary_result.json()['period']=='custom'
 assert spending_result.json()['start_date']=='2026-09-01'
 body=analytics_result.json()
 assert body['comparison']['previous_period']=={'start':'2026-08-27','end':'2026-08-31'}
 assert [entry['date'] for entry in body['trend']]==[f'2026-09-0{day}' for day in range(1,6)]
 assert body['trend'][1]=={'date':'2026-09-02','income':0,'expenses':0}
 assert body['income']==100.0 and body['expenses']==100.0
def test_custom_range_validation_and_user_isolation():
 headers=account(unique_email('custom-validation'))
 tomorrow=(date.today()+timedelta(days=1)).isoformat()
 for params in ({'start_date':'2026-09-01'},{'end_date':'2026-09-05'},{'start_date':'2026-09-06','end_date':'2026-09-05'},{'start_date':'not-a-date','end_date':'2026-09-05'},{'start_date':'2026-09-01','end_date':tomorrow}):
  assert client.get('/api/analytics',headers=headers,params=params).status_code==422
 other=account(unique_email('custom-private'))
 create_summary_tx(other,'expense',999,'2026-09-02','Private')
 assert client.get('/api/analytics',headers=headers,params={'start_date':'2026-09-01','end_date':'2026-09-05'}).json()['expenses']==0
def test_custom_range_rejects_ambiguous_period_parameter():
 headers=account(unique_email('custom-ambiguous'))
 params={'period':'month','start_date':'2026-09-01','end_date':'2026-09-05'}
 for endpoint in ('/api/financial-summary','/api/spending-analytics','/api/analytics'):
  assert client.get(endpoint,headers=headers,params=params).status_code==422
def test_comparison_endpoint_metrics_and_categories():
 headers=account(unique_email('comparison-metrics'))
 categories=client.get('/api/categories',headers=headers).json()
 food=next(c for c in categories if c['name']=='Food')
 other=next(c for c in categories if c['name']=='Other')
 create_summary_tx(headers,'income',900,'2026-09-15','Current income')
 create_summary_tx(headers,'expense',600,'2026-09-15','Current food',food['id'])
 create_summary_tx(headers,'expense',200,'2026-09-15','Current uncategorized')
 create_summary_tx(headers,'income',800,'2026-08-15','Previous income')
 create_summary_tx(headers,'expense',400,'2026-08-15','Previous food',food['id'])
 create_summary_tx(headers,'expense',100,'2026-08-15','Previous other',other['id'])
 summary_result=summary(headers)
 spending_result=spending(headers)
 analytics_result=client.get('/api/analytics',headers=headers).json()
 assert summary_result['comparison']['income']=={'current':900.0,'previous':800.0,'change_amount':100.0,'change_percent':12.5}
 assert summary_result['comparison']['expenses']['current']==800.0
 assert summary_result['comparison']['savings']['current']==100.0
 assert summary_result['comparison']['savings_rate']['change_percentage_points']==-26.39
 assert spending_result['comparison']['total_expenses']['current']==800.0
 assert spending_result['comparison']['average_expense']['previous']==250.0
 comparison={(x['category_name'],x['current_amount'],x['previous_amount']) for x in spending_result['comparison']['categories']}
 assert comparison=={('Food',600.0,400.0),('Uncategorized',200.0,0),('Other',0,100.0)}
 assert analytics_result['comparison']['income']['current']==analytics_result['income']==900.0
 assert analytics_result['comparison']['expenses']['current']==analytics_result['expenses']==800.0
 assert analytics_result['comparison']['savings']['current']==analytics_result['savings']==100.0
def test_period_boundaries_are_inclusive_and_consistent_across_analytics():
 headers=account(unique_email('period-boundaries'))
 today=date.today(); week_start=today-timedelta(days=today.weekday()); month_start=today.replace(day=1); year_start=today.replace(month=1,day=1)
 transactions=[
  ('week-start',100,'expense',week_start.isoformat()),
  ('week-end',200,'expense',today.isoformat()),
  ('before-week',300,'expense',(week_start-timedelta(days=1)).isoformat()),
  ('month-start',400,'income',month_start.isoformat()),
  ('year-start',50,'expense',year_start.isoformat()),
  ('before-month',70,'expense',(month_start-timedelta(days=1)).isoformat()),
  ('before-year',500,'income',(year_start-timedelta(days=1)).isoformat()),
  ('after-today',600,'expense',(today+timedelta(days=1)).isoformat()),
 ]
 for title,amount,kind,when in transactions:create_summary_tx(headers,kind,amount,when,title)
 for period in ('week','month','year'):
  start,end=period_bounds(period,today)
  included=[(amount,kind,date.fromisoformat(when)) for _,amount,kind,when in transactions if start<=date.fromisoformat(when)<=end]
  values={'income':sum(amount for amount,kind,_ in included if kind=='income'),'expenses':sum(amount for amount,kind,_ in included if kind=='expense'),'count':len(included)}
  summary_result=summary(headers,period)
  spending_result=spending(headers,period)
  analytics_result=client.get('/api/analytics',headers=headers,params={'period':period}).json()
  assert summary_result['period_income']==values['income']
  assert summary_result['period_expenses']==values['expenses']
  assert summary_result['transaction_count']==values['count']
  assert spending_result['total_expenses']==values['expenses']
  assert spending_result['expense_transaction_count']==sum(kind=='expense' for _,kind,_ in included)
  assert sum(category['amount'] for category in spending_result['categories'])==values['expenses']
  assert sum(category['share'] for category in spending_result['categories'])==(100.0 if values['expenses'] else 0)
  assert analytics_result['income']==values['income']
  assert analytics_result['expenses']==values['expenses']
  assert analytics_result['savings']==values['income']-values['expenses']
  trend_dates=[entry['date'] for entry in analytics_result['trend']]
  assert all(set(entry)=={'date','income','expenses'} for entry in analytics_result['trend'])
  assert trend_dates==sorted({when.isoformat() for _,_,when in included})
def test_all_period_endpoints_reject_unsupported_periods():
 headers=account(unique_email('invalid-period'))
 for endpoint in ('/api/financial-summary','/api/spending-analytics','/api/analytics'):
  for period in ('day','quarter','invalid'):
   assert client.get(endpoint,headers=headers,params={'period':period}).status_code==422
def test_financial_summary_reflects_create_edit_and_delete():
 headers=account(unique_email('summary-live'))
 transaction=create_summary_tx(headers,'income',1000)
 assert summary(headers)['balance']==1000.0
 updated=client.put(f"/api/transactions/{transaction['id']}",headers=headers,json={'title':'Updated','amount':600,'type':'expense','date':'2026-09-15'})
 assert updated.status_code==200
 assert summary(headers)['balance']==-600.0
 assert client.delete(f"/api/transactions/{transaction['id']}",headers=headers).status_code==204
 result=summary(headers)
 assert result['balance']==result['period_income']==result['period_expenses']==result['net_savings']==result['transaction_count']==0
def test_financial_summary_isolation_and_user_id_manipulation():
 user_a=account(unique_email('summary-a')); user_b=account(unique_email('summary-b'))
 create_summary_tx(user_a,'income',900)
 create_summary_tx(user_b,'income',700)
 create_summary_tx(user_b,'expense',200)
 assert {k:summary(user_a)[k] for k in ('balance','period_income','period_expenses','net_savings','savings_rate','transaction_count')}=={'balance':900.0,'period_income':900.0,'period_expenses':0,'net_savings':900.0,'savings_rate':100.0,'transaction_count':1}
 assert {k:summary(user_b)[k] for k in ('balance','period_income','period_expenses','net_savings','savings_rate','transaction_count')}=={'balance':500.0,'period_income':700.0,'period_expenses':200.0,'net_savings':500.0,'savings_rate':71.42857142857143,'transaction_count':2}
 assert client.get('/api/financial-summary?user_id=999999',headers=user_a).json()==summary(user_a)
def test_spending_analytics_requires_authentication_and_returns_empty_zero_state():
 assert client.get('/api/spending-analytics').status_code==401
 headers=account(unique_email('spending-empty'))
 result=spending(headers)
 assert {k:result[k] for k in ('period','total_expenses','expense_transaction_count','average_expense','largest_expense','top_category','categories')}=={'period':'month','total_expenses':0,'expense_transaction_count':0,'average_expense':0,'largest_expense':None,'top_category':None,'categories':[]}
 assert client.get('/api/spending-analytics',headers=headers,params={'period':'invalid'}).status_code==422
def test_spending_analytics_aggregates_categories_and_reconciles_uncategorized():
 headers=account(unique_email('spending-categories'))
 categories=client.get('/api/categories',headers=headers).json()
 food=next(c for c in categories if c['name']=='Food')
 transport=next(c for c in categories if c['name']=='Transport')
 create_summary_tx(headers,'income',9000,title='Income excluded')
 create_summary_tx(headers,'expense',500,'2026-09-01','Food one',food['id'])
 create_summary_tx(headers,'expense',1500,'2026-09-05','Food two',food['id'])
 create_summary_tx(headers,'expense',1000,'2026-09-06','Transport',transport['id'])
 create_summary_tx(headers,'expense',500,'2026-09-07','Uncategorized')
 create_summary_tx(headers,'expense',300,'2026-08-31','Outside period')
 result=spending(headers)
 assert result['total_expenses']==3500.0
 assert result['expense_transaction_count']==4
 assert result['average_expense']==875.0
 assert sum(category['amount'] for category in result['categories'])==result['total_expenses']
 assert [(c['category_name'],c['amount'],c['share']) for c in result['categories']]==[
  ('Food',2000.0,2000/3500*100),('Transport',1000.0,1000/3500*100),('Uncategorized',500.0,500/3500*100)]
 assert result['top_category']['category_name']=='Food'
 assert result['largest_expense']['title']=='Food two'
 assert result['largest_expense']['amount']==1500
 assert food['id'] and transport['id']
def test_spending_analytics_top_category_tie_is_deterministic_and_income_excluded():
 headers=account(unique_email('spending-tie'))
 categories=client.get('/api/categories',headers=headers).json()
 food=next(c for c in categories if c['name']=='Food')
 bills=next(c for c in categories if c['name']=='Bills')
 client.post('/api/transactions',headers=headers,json={'title':'Bills','amount':100,'type':'expense','date':'2026-09-10','category_id':bills['id']})
 client.post('/api/transactions',headers=headers,json={'title':'Food','amount':100,'type':'expense','date':'2026-09-10','category_id':food['id']})
 create_summary_tx(headers,'income',10000,'2026-09-10','Income')
 result=spending(headers)
 assert result['top_category']['category_name']=='Bills'
 assert result['expense_transaction_count']==2
 assert result['total_expenses']==200
def test_spending_analytics_reflects_create_edit_category_date_type_and_delete():
 headers=account(unique_email('spending-live'))
 categories=client.get('/api/categories',headers=headers).json()
 food=next(c for c in categories if c['name']=='Food')
 transport=next(c for c in categories if c['name']=='Transport')
 transaction=client.post('/api/transactions',headers=headers,json={'title':'Live','amount':100,'type':'expense','date':'2026-09-15','category_id':food['id']}).json()
 assert spending(headers)['total_expenses']==100
 updated=client.put(f"/api/transactions/{transaction['id']}",headers=headers,json={'title':'Live','amount':250,'type':'expense','date':'2026-08-01','category_id':transport['id']})
 assert updated.status_code==200 and spending(headers)['total_expenses']==0
 updated=client.put(f"/api/transactions/{transaction['id']}",headers=headers,json={'title':'Live','amount':250,'type':'expense','date':'2026-09-15','category_id':transport['id']})
 assert updated.status_code==200 and spending(headers)['categories'][0]['category_name']=='Transport'
 updated=client.put(f"/api/transactions/{transaction['id']}",headers=headers,json={'title':'Live','amount':250,'type':'income','date':'2026-09-15','category_id':transport['id']})
 assert updated.status_code==200 and spending(headers)['total_expenses']==0
 assert client.delete(f"/api/transactions/{transaction['id']}",headers=headers).status_code==204
 assert spending(headers)['categories']==[]
def test_spending_analytics_isolated_from_other_users_and_user_id_query():
 user_a=account(unique_email('spending-a')); user_b=account(unique_email('spending-b'))
 create_summary_tx(user_a,'expense',100,'2026-09-15','A expense')
 create_summary_tx(user_b,'expense',900,'2026-09-15','B expense')
 result=spending(user_a)
 assert result['total_expenses']==100 and result['largest_expense']['title']=='A expense'
 assert result['expense_transaction_count']==1
 assert client.get('/api/spending-analytics?user_id=999999',headers=user_a).json()==result
def test_analytics_uses_uncategorized_label_consistently_and_preserves_isolation():
 user_a=account(unique_email('analytics-category-a')); user_b=account(unique_email('analytics-category-b'))
 categories=client.get('/api/categories',headers=user_a).json()
 food=next(category for category in categories if category['name']=='Food')
 create_summary_tx(user_a,'income',1000,'2026-09-15','Salary')
 create_summary_tx(user_a,'expense',300,'2026-09-15','Dinner',food['id'])
 create_summary_tx(user_a,'expense',200,'2026-09-15','Miscellaneous')
 create_summary_tx(user_b,'expense',900,'2026-09-15','Private')
 analytics=client.get('/api/analytics',headers=user_a).json()
 spending_result=spending(user_a)
 assert analytics['by_category']==[{'name':'Food','value':300.0},{'name':'Uncategorized','value':200.0}]
 assert [(category['category_name'],category['amount']) for category in spending_result['categories']]==[('Food',300.0),('Uncategorized',200.0)]
 assert analytics['income']==1000.0 and analytics['expenses']==500.0
 assert spending_result['total_expenses']==500.0
 assert client.get('/api/analytics',headers=user_b).json()['by_category']==[{'name':'Uncategorized','value':900.0}]
def test_auth_and_empty_workspace():
 h=account(unique_email('empty')); assert client.get('/api/auth/me',headers=h).status_code==200; assert client.get('/api/transactions',headers=h).json()==[]; assert client.get('/api/goals',headers=h).json()==[]
def test_dashboard_categories_and_ask():
 h=account(unique_email('dashboard')); assert 'expenses' in client.get('/api/dashboard',headers=h).json(); assert len(client.get('/api/categories',headers=h).json())>=9; assert 'answer' in client.post('/api/ai/ask',headers=h,json={'question':'How much did I save?'}).json()
def test_categories_are_global_seeded_and_require_authentication():
 assert client.get('/api/categories').status_code==401
 rows=client.get('/api/categories',headers=account(unique_email('category-list'))).json()
 assert {row['name'] for row in rows} >= {'Food','Transport','Other'}
 assert all({'id','name','color','icon'} <= row.keys() for row in rows)
def test_valid_category_is_persisted_and_serialized_on_transaction():
 email=unique_email('category-valid'); headers=account(email)
 category=client.get('/api/categories',headers=headers).json()[0]
 response=client.post('/api/transactions',headers=headers,json={'type':'expense','amount':300,'title':'Categorized','date':'2026-09-13','category_id':category['id']})
 assert response.status_code==201
 body=response.json()
 assert body['category_id']==category['id'] and body['category']['name']==category['name']
 s=SessionLocal()
 try:
  transaction=s.get(Transaction,body['id'])
  assert transaction.category_id==category['id']
  assert transaction.category.name==category['name']
 finally:
  s.close()
def test_invalid_category_is_rejected_on_create_and_edit():
 email=unique_email('category-invalid'); headers=account(email)
 invalid_id=999999999
 created=client.post('/api/transactions',headers=headers,json={'type':'expense','amount':100,'title':'Uncategorized','date':'2026-09-13'}).json()
 create=client.post('/api/transactions',headers=headers,json={'type':'expense','amount':100,'title':'Invalid','date':'2026-09-13','category_id':invalid_id})
 update=client.put(f"/api/transactions/{created['id']}",headers=headers,json={'type':'expense','amount':100,'title':'Invalid','date':'2026-09-13','category_id':invalid_id})
 assert create.status_code==400 and update.status_code==400
 assert client.get(f"/api/transactions/{created['id']}",headers=headers).json()['category_id'] is None
 s=SessionLocal()
 try:
  user=s.query(User).filter_by(email=email).one()
  assert s.query(Transaction).filter_by(user_id=user.id,title='Invalid').count()==0
 finally:
  s.close()
def test_editing_category_preserves_transaction_and_balance():
 headers=account(unique_email('category-edit'))
 categories=client.get('/api/categories',headers=headers).json()
 category_a,category_b=categories[0],categories[1]
 income=client.post('/api/transactions',headers=headers,json={'type':'income','amount':1000,'title':'Salary','date':'2026-09-01','category_id':category_a['id']}).json()
 expense=client.post('/api/transactions',headers=headers,json={'type':'expense','amount':300,'title':'Dinner','date':'2026-09-02','category_id':category_a['id']}).json()
 updated=client.put(f"/api/transactions/{expense['id']}",headers=headers,json={'type':'expense','amount':300,'title':'Dinner','date':'2026-09-02','category_id':category_b['id']})
 assert updated.status_code==200
 body=updated.json()
 assert body['category_id']==category_b['id'] and body['category']['name']==category_b['name']
 assert body['amount']==300 and body['type']=='expense'
 assert client.get('/api/balance',headers=headers).json()=={'balance':700.0,'total_income':1000.0,'total_expenses':300.0}
 assert client.delete(f"/api/transactions/{income['id']}",headers=headers).status_code==204
 assert client.delete(f"/api/transactions/{expense['id']}",headers=headers).status_code==204
def test_idor_transactions_budgets_goals():
 a=account(unique_email('a')); b=account(unique_email('b'))
 tx=client.post('/api/transactions',headers=a,json={'title':'private','amount':10,'type':'expense','date':'2025-01-01'}).json(); assert client.get(f"/api/transactions",headers=b).json()==[]; assert client.get(f"/api/transactions/{tx['id']}",headers=b).status_code==404; assert client.put(f"/api/transactions/{tx['id']}",headers=b,json={'title':'tampered','amount':1,'type':'expense','date':'2025-01-01'}).status_code==404; assert client.delete(f"/api/transactions/{tx['id']}",headers=b).status_code==404
 budget=client.post('/api/budgets',headers=a,json={'amount':100,'month':'2025-01'}).json(); assert client.get('/api/budgets?month=2025-01',headers=b).json()==[]
 goal=client.post('/api/goals',headers=a,json={'name':'private','target':100}).json(); assert client.get('/api/goals',headers=b).json()==[]; assert client.post(f"/api/goals/{goal['id']}/contribute",headers=b,json={'amount':1}).status_code==404
def test_transaction_owner_is_authenticated_user_and_updated():
 email=unique_email('owner'); headers=account(email)
 response=client.post('/api/transactions',headers=headers,json={'title':'owned','amount':25,'type':'expense','date':'2026-09-13','user_id':999999})
 assert response.status_code==201
 transaction_id=response.json()['id']
 s=SessionLocal()
 try:
  user=s.query(User).filter_by(email=email).one()
  transaction=s.get(Transaction,transaction_id)
  assert transaction.user_id==user.id
  assert transaction.user is user
  assert transaction in user.transactions
  assert transaction.updated_at is not None
  original_updated_at=transaction.updated_at
  transaction.title='owned-updated'
  sleep(0.01)
  s.commit()
  s.refresh(transaction)
  assert transaction.updated_at>=original_updated_at
  assert s.query(Transaction).filter(Transaction.user_id.is_(None)).count()==0
 finally:
  s.close()
def test_create_expense_and_income_are_authenticated_and_return_timestamps():
 email=unique_email('create'); headers=account(email)
 expense=client.post('/api/transactions',headers=headers,json={'type':'expense','amount':450,'category_id':None,'title':'Dinner','date':'2026-09-13','payment_method':'UPI','user_id':999999})
 income=client.post('/api/transactions',headers=headers,json={'type':'income','amount':50000,'title':'September salary','date':'2026-09-01','payment_method':'Bank'})
 assert expense.status_code==201 and income.status_code==201
 assert expense.json()['type']=='expense' and expense.json()['amount']==450
 assert income.json()['type']=='income' and income.json()['amount']==50000
 assert expense.json()['created_at'] and expense.json()['updated_at']
 s=SessionLocal()
 try:
  user=s.query(User).filter_by(email=email).one()
  assert s.query(Transaction).filter_by(id=expense.json()['id'],user_id=user.id).count()==1
  assert s.query(Transaction).filter_by(id=income.json()['id'],user_id=user.id).count()==1
 finally:
  s.close()
def test_create_transaction_requires_authentication():
 response=client.post('/api/transactions',json={'type':'expense','amount':10,'title':'Unauthenticated','date':'2026-09-13'})
 assert response.status_code==401
def test_create_transaction_validates_amount_and_type():
 headers=account(unique_email('validation'))
 for amount in (0,-1):
  assert client.post('/api/transactions',headers=headers,json={'type':'expense','amount':amount,'title':'Invalid','date':'2026-09-13'}).status_code==422
 assert client.post('/api/transactions',headers=headers,json={'type':'transfer','amount':10,'title':'Invalid','date':'2026-09-13'}).status_code==422
def test_get_transactions_returns_only_authenticated_users_data_in_newest_order():
 a=account(unique_email('reader-a')); b=account(unique_email('reader-b'))
 a_first=client.post('/api/transactions',headers=a,json={'type':'expense','amount':10,'title':'A older','date':'2026-09-10'}).json()
 a_latest=client.post('/api/transactions',headers=a,json={'type':'income','amount':100,'title':'A latest','date':'2026-09-13'}).json()
 client.post('/api/transactions',headers=b,json={'type':'expense','amount':20,'title':'B private','date':'2026-09-13'})
 response=client.get('/api/transactions?user_id=999999',headers=a)
 assert response.status_code==200
 rows=response.json()
 assert [row['id'] for row in rows[:2]]==[a_latest['id'],a_first['id']]
 assert {row['title'] for row in rows}=={'A latest','A older'}
 assert all('created_at' in row and 'updated_at' in row for row in rows)
 assert client.get('/api/transactions',headers=b).json()[0]['title']=='B private'
def test_get_transactions_requires_authentication_and_returns_empty_collection():
 assert client.get('/api/transactions').status_code==401
 assert client.get('/api/transactions',headers=account(unique_email('empty-reader'))).json()==[]
def test_update_transaction_changes_owned_record_and_persists():
 email=unique_email('editor'); headers=account(email)
 created=client.post('/api/transactions',headers=headers,json={'type':'expense','amount':450,'title':'Dinner','date':'2026-09-13','payment_method':'UPI'}).json()
 original_updated_at=created['updated_at']
 sleep(0.01)
 response=client.put(f"/api/transactions/{created['id']}",headers=headers,json={'type':'income','amount':50000,'title':'September salary','date':'2026-09-01','payment_method':'Bank','user_id':999999})
 assert response.status_code==200
 updated=response.json()
 assert updated['id']==created['id']
 assert updated['type']=='income' and updated['amount']==50000
 assert updated['title']=='September salary' and updated['date']=='2026-09-01'
 assert updated['payment_method']=='Bank'
 assert updated['updated_at']!=original_updated_at
 s=SessionLocal()
 try:
  user=s.query(User).filter_by(email=email).one()
  transaction=s.get(Transaction,created['id'])
  assert transaction.user_id==user.id
  assert transaction.type=='income' and transaction.amount==50000
  assert transaction.title=='September salary'
 finally:
  s.close()
def test_update_transaction_blocks_cross_user_and_preserves_original():
 owner=account(unique_email('owner-edit')); attacker=account(unique_email('attacker-edit'))
 created=client.post('/api/transactions',headers=owner,json={'type':'expense','amount':800,'title':'Owner private','date':'2026-09-13'}).json()
 response=client.put(f"/api/transactions/{created['id']}",headers=attacker,json={'type':'income','amount':1,'title':'Tampered','date':'2026-09-13'})
 assert response.status_code==404
 original=client.get(f"/api/transactions/{created['id']}",headers=owner).json()
 assert original['title']=='Owner private' and original['amount']==800 and original['type']=='expense'
def test_update_transaction_rejects_missing_or_unauthenticated_resource():
 headers=account(unique_email('missing-edit'))
 assert client.put('/api/transactions/999999999',headers=headers,json={'type':'expense','amount':10,'title':'Missing','date':'2026-09-13'}).status_code==404
 assert client.put('/api/transactions/999999999',json={'type':'expense','amount':10,'title':'Missing','date':'2026-09-13'}).status_code==401
def test_update_transaction_validates_amount_and_type():
 headers=account(unique_email('update-validation'))
 created=client.post('/api/transactions',headers=headers,json={'type':'expense','amount':100,'title':'Valid','date':'2026-09-13'}).json()
 for amount in (0,-1):
  assert client.put(f"/api/transactions/{created['id']}",headers=headers,json={'type':'expense','amount':amount,'title':'Invalid','date':'2026-09-13'}).status_code==422
 assert client.put(f"/api/transactions/{created['id']}",headers=headers,json={'type':'transfer','amount':100,'title':'Invalid','date':'2026-09-13'}).status_code==422
def test_delete_transaction_removes_owned_record():
 email=unique_email('delete-owner'); headers=account(email)
 created=client.post('/api/transactions',headers=headers,json={'type':'expense','amount':125,'title':'Remove me','date':'2026-09-13'}).json()
 response=client.delete(f"/api/transactions/{created['id']}",headers=headers)
 assert response.status_code==204
 assert response.content==b''
 s=SessionLocal()
 try:
  user=s.query(User).filter_by(email=email).one()
  assert s.get(Transaction,created['id']) is None
  assert all(transaction.id!=created['id'] for transaction in user.transactions)
 finally:
  s.close()
def test_delete_transaction_blocks_cross_user_and_preserves_record():
 owner=account(unique_email('delete-owner')); attacker=account(unique_email('delete-attacker'))
 created=client.post('/api/transactions',headers=owner,json={'type':'expense','amount':300,'title':'Keep private','date':'2026-09-13'}).json()
 response=client.delete(f"/api/transactions/{created['id']}",headers=attacker)
 assert response.status_code==404
 original=client.get(f"/api/transactions/{created['id']}",headers=owner)
 assert original.status_code==200
 assert original.json()['title']=='Keep private' and original.json()['amount']==300
def test_delete_transaction_requires_authentication_and_handles_missing_id():
 headers=account(unique_email('delete-missing'))
 assert client.delete('/api/transactions/999999999',headers=headers).status_code==404
 assert client.delete('/api/transactions/999999999').status_code==401
def test_balance_starts_at_zero_and_requires_authentication():
 assert client.get('/api/balance').status_code==401
 assert client.get('/api/balance',headers=account(unique_email('balance-empty'))).json()=={'balance':0.0,'total_income':0.0,'total_expenses':0.0}
def test_balance_calculates_income_and_expenses_for_current_user_only():
 a=account(unique_email('balance-a')); b=account(unique_email('balance-b'))
 for headers,payload in [
  (a,{'type':'income','amount':5000,'title':'A income','date':'2026-09-01'}),
  (a,{'type':'expense','amount':1000,'title':'A expense','date':'2026-09-02'}),
  (b,{'type':'income','amount':100000,'title':'B income','date':'2026-09-01'}),
  (b,{'type':'expense','amount':500,'title':'B expense','date':'2026-09-02'}),
 ]:
  assert client.post('/api/transactions',headers=headers,json=payload).status_code==201
 assert client.get('/api/balance?user_id=999999',headers=a).json()=={'balance':4000.0,'total_income':5000.0,'total_expenses':1000.0}
 assert client.get('/api/balance',headers=b).json()=={'balance':99500.0,'total_income':100000.0,'total_expenses':500.0}
def test_balance_reflects_multiple_transactions_edits_and_deletes():
 headers=account(unique_email('balance-mutations'))
 income=client.post('/api/transactions',headers=headers,json={'type':'income','amount':7000,'title':'Income one','date':'2026-09-01'}).json()
 expense=client.post('/api/transactions',headers=headers,json={'type':'expense','amount':1000,'title':'Expense one','date':'2026-09-02'}).json()
 second_expense=client.post('/api/transactions',headers=headers,json={'type':'expense','amount':500,'title':'Expense two','date':'2026-09-03'}).json()
 assert client.get('/api/balance',headers=headers).json()=={'balance':5500.0,'total_income':7000.0,'total_expenses':1500.0}
 updated=client.put(f"/api/transactions/{expense['id']}",headers=headers,json={'type':'expense','amount':1750,'title':'Expense one','date':'2026-09-02'}); assert updated.status_code==200
 assert client.get('/api/balance',headers=headers).json()=={'balance':4750.0,'total_income':7000.0,'total_expenses':2250.0}
 assert client.delete(f"/api/transactions/{second_expense['id']}",headers=headers).status_code==204
 assert client.get('/api/balance',headers=headers).json()=={'balance':5250.0,'total_income':7000.0,'total_expenses':1750.0}
 assert client.put(f"/api/transactions/{income['id']}",headers=headers,json={'type':'expense','amount':7000,'title':'Income one','date':'2026-09-01'}).status_code==200
 assert client.get('/api/balance',headers=headers).json()=={'balance':-8750.0,'total_income':0.0,'total_expenses':8750.0}
