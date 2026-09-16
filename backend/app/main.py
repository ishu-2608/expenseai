from datetime import date, datetime, timedelta
from calendar import monthrange
from typing import Optional
import csv, io, os, re, secrets
import bcrypt, jwt
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, Column, Integer, String, Float, Date, DateTime, ForeignKey, Boolean, func, inspect, text, case
from sqlalchemy.orm import declarative_base, sessionmaker, Session, relationship

DB=os.getenv('DATABASE_URL','sqlite:///./expenseai.db'); engine=create_engine(DB,connect_args={'check_same_thread':False} if DB.startswith('sqlite') else {})
SessionLocal=sessionmaker(bind=engine,autocommit=False,autoflush=False); Base=declarative_base(); APP_ENV=os.getenv('APP_ENV','development').lower(); configured_secret=os.getenv('JWT_SECRET'); 
if APP_ENV in ('production','prod') and not configured_secret: raise RuntimeError('JWT_SECRET must be set when APP_ENV is production')
SECRET=configured_secret or secrets.token_urlsafe(32); ALGO=os.getenv('JWT_ALGORITHM','HS256'); TOKEN_DAYS=max(1,int(os.getenv('ACCESS_TOKEN_EXPIRE_MINUTES','10080'))//1440); bearer=HTTPBearer(auto_error=False)
class User(Base):
 __tablename__='users'; id=Column(Integer,primary_key=True); email=Column(String,unique=True,index=True,nullable=False); name=Column(String,nullable=False); password_hash=Column(String,nullable=False); created_at=Column(DateTime,default=datetime.utcnow); transactions=relationship('Transaction',back_populates='user')
class Category(Base):
 __tablename__='categories'; id=Column(Integer,primary_key=True); name=Column(String,unique=True,index=True); color=Column(String,default='#4f7cff'); icon=Column(String,default='circle')
class Transaction(Base):
 __tablename__='transactions'; id=Column(Integer,primary_key=True); user_id=Column(Integer,ForeignKey('users.id'),index=True,nullable=False); title=Column(String,nullable=False); amount=Column(Float,nullable=False); type=Column(String,nullable=False); date=Column(Date,nullable=False,index=True); payment_method=Column(String,default='Other'); notes=Column(String,default=''); merchant=Column(String,default=''); category_id=Column(Integer,ForeignKey('categories.id')); category=relationship('Category'); user=relationship('User',back_populates='transactions'); created_at=Column(DateTime,default=datetime.utcnow); updated_at=Column(DateTime,default=datetime.utcnow,onupdate=datetime.utcnow,nullable=False)
class Budget(Base):
 __tablename__='budgets'; id=Column(Integer,primary_key=True); user_id=Column(Integer,ForeignKey('users.id'),index=True,nullable=True); month=Column(String,index=True); amount=Column(Float); category_id=Column(Integer,ForeignKey('categories.id'),nullable=True); category=relationship('Category')
class Goal(Base):
 __tablename__='goals'; id=Column(Integer,primary_key=True); user_id=Column(Integer,ForeignKey('users.id'),index=True,nullable=True); name=Column(String); target=Column(Float); saved=Column(Float,default=0); deadline=Column(Date,nullable=True); created_at=Column(DateTime,default=datetime.utcnow)
class Recurring(Base):
 __tablename__='recurring'; id=Column(Integer,primary_key=True); user_id=Column(Integer,ForeignKey('users.id'),index=True,nullable=True); name=Column(String); amount=Column(Float); frequency=Column(String,default='monthly'); category_id=Column(Integer,ForeignKey('categories.id')); next_date=Column(Date); active=Column(Boolean,default=True); category=relationship('Category')
Base.metadata.create_all(engine)

def db():
 s=SessionLocal()
 try:
  if s.query(Category).count()==0: seed_categories(s)
  else:
   existing={c.name for c in s.query(Category)}
   missing=[Category(name=n,color=c,icon=i) for n,c,i in CATS if n not in existing]
   if missing: s.add_all(missing); s.commit()
  yield s
 finally:s.close()
def hash_password(p): return bcrypt.hashpw(p.encode(),bcrypt.gensalt()).decode()
def verify_password(p,h): return bcrypt.checkpw(p.encode(),h.encode())
def migrate_transaction_ownership():
 if not DB.startswith('sqlite'): return
 with engine.begin() as c:
  for table in ('transactions','budgets','goals','recurring'):
   cols={x['name'] for x in inspect(engine).get_columns(table)}
   if 'user_id' not in cols: c.execute(text(f'ALTER TABLE {table} ADD COLUMN user_id INTEGER'))
  tx_columns={x['name']:x for x in inspect(engine).get_columns('transactions')}
  if 'updated_at' not in tx_columns: c.execute(text('ALTER TABLE transactions ADD COLUMN updated_at DATETIME'))
  c.execute(text('UPDATE transactions SET updated_at = COALESCE(created_at, CURRENT_TIMESTAMP) WHERE updated_at IS NULL'))
 s=SessionLocal()
 try:
  legacy=s.query(User).filter_by(email='legacy-demo@expenseai.local').first()
  orphan_count=s.query(Transaction).filter(Transaction.user_id.is_(None)).count()
  if orphan_count:
   if legacy is None:
    legacy=User(email='legacy-demo@expenseai.local',name='Legacy Demo User',password_hash=hash_password(secrets.token_urlsafe(24)))
    s.add(legacy); s.flush()
   s.query(Transaction).filter(Transaction.user_id.is_(None)).update({'user_id':legacy.id},synchronize_session=False)
   s.commit()
 finally:s.close()
 tx_columns={x['name']:x for x in inspect(engine).get_columns('transactions')}
 if tx_columns['user_id']['nullable']:
  with engine.begin() as c:
   for index in c.execute(text('PRAGMA index_list(transactions)')).fetchall():
    name=index[1]
    if not name.startswith('sqlite_autoindex_'): c.execute(text(f'DROP INDEX IF EXISTS "{name}"'))
   c.execute(text('PRAGMA foreign_keys=OFF'))
   c.execute(text('ALTER TABLE transactions RENAME TO transactions_legacy'))
   Base.metadata.create_all(c)
   c.execute(text('''INSERT INTO transactions
     (id, user_id, title, amount, type, date, payment_method, notes, merchant, category_id, created_at, updated_at)
     SELECT id, user_id, title, amount, type, date, payment_method, notes, merchant, category_id, created_at, updated_at
     FROM transactions_legacy'''))
   c.execute(text('DROP TABLE transactions_legacy'))
   c.execute(text('PRAGMA foreign_keys=ON'))
migrate_transaction_ownership()
def token(u): return jwt.encode({'sub':str(u.id),'exp':datetime.utcnow()+timedelta(days=TOKEN_DAYS)},SECRET,algorithm=ALGO)
def current_user(creds:HTTPAuthorizationCredentials=Depends(bearer),s:Session=Depends(db)):
 if not creds: raise HTTPException(401,'Authentication required',headers={'WWW-Authenticate':'Bearer'})
 try: uid=int(jwt.decode(creds.credentials,SECRET,algorithms=[ALGO])['sub'])
 except Exception: raise HTTPException(401,'Invalid or expired token',headers={'WWW-Authenticate':'Bearer'})
 u=s.get(User,uid)
 if not u: raise HTTPException(401,'User not found')
 return u
class RegisterIn(BaseModel): email:str; password:str=Field(min_length=8,max_length=128); name:str=Field(min_length=1,max_length=100)
class LoginIn(BaseModel): email:str; password:str
class TxIn(BaseModel): title:str=Field(min_length=1,max_length=160); amount:float=Field(gt=0); type:str=Field(pattern='^(income|expense)$'); category_id:Optional[int]=None; date:date; payment_method:str='Other'; notes:str=''; merchant:str=''
class BudgetIn(BaseModel): amount:float=Field(gt=0); month:str; category_id:Optional[int]=None
class GoalIn(BaseModel): name:str=Field(min_length=1); target:float=Field(gt=0); saved:float=Field(ge=0,default=0); deadline:Optional[date]=None
class Contrib(BaseModel): amount:float=Field(gt=0)
class Ask(BaseModel): question:str=Field(min_length=2,max_length=500)
app=FastAPI(title='ExpenseAI API',version='2.0.0'); app.add_middleware(CORSMiddleware,allow_origins=[origin.strip() for origin in os.getenv('CORS_ORIGINS','http://localhost:5173,http://127.0.0.1:5173').split(',') if origin.strip()],allow_methods=['*'],allow_headers=['*'])
CATS=[('Food','#f59e0b','utensils'),('Transport','#3b82f6','car'),('Shopping','#8b5cf6','shopping-bag'),('Entertainment','#ec4899','music'),('Bills','#ef4444','receipt'),('Education','#06b6d4','book'),('Health','#10b981','heart'),('Travel','#14b8a6','plane'),('Other','#64748b','circle')]
def seed_categories(s): s.add_all([Category(name=n,color=c,icon=i) for n,c,i in CATS]); s.commit()
def seed_demo(s):
 if os.getenv('SEED_DEMO_DATA','').lower() not in ('1','true','yes'): return
 u=s.query(User).filter_by(email='demo@expenseai.local').first()
 if not u: u=User(email='demo@expenseai.local',name='Demo User',password_hash=hash_password('demo-password')); s.add(u); s.flush()
 if s.query(Transaction).filter_by(user_id=u.id).count(): return
 cats={c.name:c for c in s.query(Category)}; today=date.today(); data=[('Salary',55000,'income','Other',1),('Rent',18000,'expense','Bills',2),('Swiggy',620,'expense','Food',3),('Uber',280,'expense','Transport',4),('Amazon',2499,'expense','Shopping',5),('Netflix',649,'expense','Entertainment',7),('Gym',1200,'expense','Health',9),('Electricity',1450,'expense','Bills',11),('Groceries',4200,'expense','Food',13)]
 for title,a,t,c,d in data:s.add(Transaction(user_id=u.id,title=title,amount=a,type=t,category_id=cats[c].id,date=today-timedelta(days=d),payment_method='UPI',merchant=title))
 s.add(Budget(user_id=u.id,month=today.strftime('%Y-%m'),amount=30000)); s.add(Goal(user_id=u.id,name='Emergency fund',target=150000,saved=72000)); s.commit()
@app.on_event('startup')
def startup():
 s=SessionLocal()
 try: seed_demo(s)
 finally:s.close()
def txdict(t): return {'id':t.id,'title':t.title,'amount':t.amount,'type':t.type,'date':t.date.isoformat(),'payment_method':t.payment_method,'notes':t.notes,'merchant':t.merchant,'category_id':t.category_id,'category':{'id':t.category.id,'name':t.category.name,'color':t.category.color,'icon':t.category.icon} if t.category else None,'created_at':t.created_at.isoformat() if t.created_at else None,'updated_at':t.updated_at.isoformat() if t.updated_at else None}
def totals(s,u,start,end):
 rows=s.query(Transaction).filter(Transaction.user_id==u.id,Transaction.date>=start,Transaction.date<=end).all(); return rows,sum(x.amount for x in rows if x.type=='income'),sum(x.amount for x in rows if x.type=='expense')
def period_bounds(period,today=None):
 today=today or date.today()
 if period=='month': return today.replace(day=1),today
 if period=='week': return today-timedelta(days=today.weekday()),today
 if period=='year': return today.replace(month=1,day=1),today
 raise HTTPException(422,'Period must be week, month, or year')
def comparison_period_bounds(period,today=None):
 current_start,current_end=period_bounds(period,today)
 if period=='week': return current_start,current_end,current_start-timedelta(days=7),current_end-timedelta(days=7)
 if period=='month':
  previous_year=current_start.year if current_start.month>1 else current_start.year-1
  previous_month=current_start.month-1 if current_start.month>1 else 12
  previous_start=date(previous_year,previous_month,1)
  previous_end=date(previous_year,previous_month,min(current_end.day,monthrange(previous_year,previous_month)[1]))
  return current_start,current_end,previous_start,previous_end
 previous_year=current_start.year-1
 previous_end_day=min(current_end.day,monthrange(previous_year,current_end.month)[1])
 return current_start,current_end,date(previous_year,1,1),date(previous_year,current_end.month,previous_end_day)
def compare_values(current,previous):
 change_amount=current-previous
 if previous==0: change_percent=0 if current==0 else None
 elif previous<0: change_percent=None
 else: change_percent=round(change_amount/previous*100,2)
 return {'current':current,'previous':previous,'change_amount':change_amount,'change_percent':change_percent}
def period_data(s,u,start,end):
 rows, income, expenses=totals(s,u,start,end)
 expense_rows=[t for t in rows if t.type=='expense']
 categories={}
 for transaction in expense_rows:
  name=transaction.category.name if transaction.category else 'Uncategorized'
  key=(transaction.category_id,name)
  categories[key]=categories.get(key,0)+transaction.amount
 largest=max(expense_rows,key=lambda t:(t.amount,-t.id),default=None)
 return {'rows':rows,'income':income,'expenses':expenses,'expense_rows':expense_rows,'categories':categories,'largest':largest}
def category_comparison(current,previous):
 keys=set(current['categories'])|set(previous['categories'])
 result=[]
 for category_id,category_name in keys:
  current_amount=current['categories'].get((category_id,category_name),0)
  previous_amount=previous['categories'].get((category_id,category_name),0)
  if current_amount or previous_amount:
   values=compare_values(current_amount,previous_amount)
   result.append({'category_id':category_id,'category_name':category_name,'current_amount':current_amount,'previous_amount':previous_amount,'change_amount':values['change_amount'],'change_percent':values['change_percent']})
 return sorted(result,key=lambda category:(-category['current_amount'],-category['previous_amount'],category['category_name']))
def custom_period_bounds(start_date,end_date):
 if start_date is None or end_date is None: raise HTTPException(422,'Both start_date and end_date are required')
 if start_date>end_date: raise HTTPException(422,'start_date must be on or before end_date')
 if end_date>date.today(): raise HTTPException(422,'end_date cannot be in the future')
 days=(end_date-start_date).days+1
 previous_end=start_date-timedelta(days=1)
 return start_date,end_date,previous_end-timedelta(days=days-1),previous_end
def comparison_context(s,u,period,start_date=None,end_date=None):
 if start_date is not None or end_date is not None:
  current_start,current_end,previous_start,previous_end=custom_period_bounds(start_date,end_date)
 else:
  current_start,current_end,previous_start,previous_end=comparison_period_bounds(period)
 return current_start,current_end,previous_start,previous_end,period_data(s,u,current_start,current_end),period_data(s,u,previous_start,previous_end)
def financial_summary(s,u,period,start_date=None,end_date=None):
 start,end,previous_start,previous_end,current,previous=comparison_context(s,u,period,start_date,end_date)
 rows,period_income,period_expenses=current['rows'],current['income'],current['expenses']
 all_time=s.query(
  func.coalesce(func.sum(case((Transaction.type=='income',Transaction.amount),else_=0)),0),
  func.coalesce(func.sum(case((Transaction.type=='expense',Transaction.amount),else_=0)),0)
 ).filter(Transaction.user_id==u.id).one()
 total_income,total_expenses=float(all_time[0]),float(all_time[1])
 net_savings=period_income-period_expenses
 savings_rate=(net_savings/period_income*100) if period_income else 0
 previous_savings=previous['income']-previous['expenses']
 previous_rate=(previous_savings/previous['income']*100) if previous['income'] else 0
 response={'balance':total_income-total_expenses,'period_income':period_income,'period_expenses':period_expenses,'net_savings':net_savings,'savings_rate':savings_rate,'transaction_count':len(rows),'comparison':{'previous_period':{'start':previous_start.isoformat(),'end':previous_end.isoformat()},'income':compare_values(period_income,previous['income']),'expenses':compare_values(period_expenses,previous['expenses']),'savings':compare_values(net_savings,previous_savings),'savings_rate':{'current':savings_rate,'previous':previous_rate,'change_percentage_points':round(savings_rate-previous_rate,2)},'transaction_count':compare_values(len(rows),len(previous['rows']))}}
 if start_date is not None or end_date is not None: response.update({'period':'custom','start_date':start.isoformat(),'end_date':end.isoformat()})
 return response
def spending_analytics(s,u,period,start_date=None,end_date=None):
 start,end,previous_start,previous_end,current,previous=comparison_context(s,u,period,start_date,end_date)
 rows,total_expenses=current['rows'],current['expenses']
 expenses=current['expense_rows']; by_category=current['categories']
 categories=sorted(
  [{'category_id':category_id,'category_name':category_name,'amount':amount,'share':(amount/total_expenses*100) if total_expenses else 0}
   for (category_id,category_name),amount in by_category.items()],
  key=lambda category:(-category['amount'],category['category_name'],category['category_id'] is not None,category['category_id'] or 0)
 )
 largest=current['largest']; previous_largest=previous['largest']
 top=categories[0] if categories else None
 response={
  'period':period,
  'total_expenses':total_expenses,
  'expense_transaction_count':len(expenses),
  'average_expense':total_expenses/len(expenses) if expenses else 0,
  'largest_expense':{'id':largest.id,'title':largest.title,'amount':largest.amount,'date':largest.date.isoformat()} if largest else None,
  'top_category':top,
  'categories':categories,
  'comparison':{'previous_period':{'start':previous_start.isoformat(),'end':previous_end.isoformat()},'total_expenses':compare_values(total_expenses,previous['expenses']),'expense_transaction_count':compare_values(len(expenses),len(previous['expense_rows'])),'average_expense':compare_values(total_expenses/len(expenses) if expenses else 0,previous['expenses']/len(previous['expense_rows']) if previous['expense_rows'] else 0),'largest_expense':compare_values(largest.amount if largest else 0,previous_largest.amount if previous_largest else 0),'categories':category_comparison(current,previous)}
 }
 if start_date is not None or end_date is not None: response.update({'period':'custom','start_date':start.isoformat(),'end_date':end.isoformat()})
 return response
@app.get('/api/health')
def health(): return {'status':'ok'}
@app.post('/api/auth/register',status_code=201)
def register(x:RegisterIn,s:Session=Depends(db)):
 email=x.email.strip().lower()
 if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',email): raise HTTPException(422,'Please enter a valid email')
 if not x.name.strip(): raise HTTPException(422,'Name is required')
 if s.query(User).filter(func.lower(User.email)==email).first(): raise HTTPException(409,'Email already registered')
 u=User(email=email,name=x.name.strip(),password_hash=hash_password(x.password)); s.add(u); s.commit(); s.refresh(u); return {'access_token':token(u),'token_type':'bearer','user':{'id':u.id,'email':u.email,'name':u.name}}
@app.post('/api/auth/login')
def login(x:LoginIn,s:Session=Depends(db)):
 u=s.query(User).filter(func.lower(User.email)==x.email.strip().lower()).first()
 if not u or not verify_password(x.password,u.password_hash): raise HTTPException(401,'Invalid email or password')
 return {'access_token':token(u),'token_type':'bearer','user':{'id':u.id,'email':u.email,'name':u.name}}
@app.get('/api/auth/me')
def me(u:User=Depends(current_user)): return {'id':u.id,'email':u.email,'name':u.name}
@app.get('/api/categories')
def categories(s:Session=Depends(db),u:User=Depends(current_user)): return [{'id':c.id,'name':c.name,'color':c.color,'icon':c.icon} for c in s.query(Category).order_by(Category.id)]
@app.get('/api/transactions')
def transactions(search:str='',type:Optional[str]=None,category_id:Optional[int]=None,limit:int=100,offset:int=0,s:Session=Depends(db),u:User=Depends(current_user)):
 q=s.query(Transaction).filter(Transaction.user_id==u.id).order_by(Transaction.date.desc(),Transaction.id.desc());
 if search:q=q.filter((Transaction.title.ilike(f'%{search}%'))|(Transaction.merchant.ilike(f'%{search}%')))
 if type:q=q.filter(Transaction.type==type)
 if category_id:q=q.filter(Transaction.category_id==category_id)
 return [txdict(x) for x in q.offset(offset).limit(min(limit,200)).all()]
@app.post('/api/transactions',status_code=201)
def create_tx(x:TxIn,s:Session=Depends(db),u:User=Depends(current_user)):
 if x.category_id is not None and not s.get(Category,x.category_id): raise HTTPException(400,'Category not found')
 t=Transaction(user_id=u.id,**x.model_dump()); s.add(t); s.commit(); s.refresh(t); return txdict(t)
@app.get('/api/transactions/{id}')
def get_tx(id:int,s:Session=Depends(db),u:User=Depends(current_user)):
 t=s.query(Transaction).filter_by(id=id,user_id=u.id).first()
 if not t: raise HTTPException(404,'Transaction not found')
 return txdict(t)
@app.put('/api/transactions/{id}')
def update_tx(id:int,x:TxIn,s:Session=Depends(db),u:User=Depends(current_user)):
 t=s.query(Transaction).filter_by(id=id,user_id=u.id).first()
 if not t: raise HTTPException(404,'Transaction not found')
 if x.category_id is not None and not s.get(Category,x.category_id): raise HTTPException(400,'Category not found')
 for key,value in x.model_dump().items(): setattr(t,key,value)
 s.commit(); s.refresh(t); return txdict(t)
@app.delete('/api/transactions/{id}',status_code=204)
def delete_tx(id:int,s:Session=Depends(db),u:User=Depends(current_user)):
 t=s.query(Transaction).filter_by(id=id,user_id=u.id).first()
 if not t: raise HTTPException(404,'Transaction not found')
 s.delete(t); s.commit()
@app.get('/api/dashboard')
def dashboard(s:Session=Depends(db),u:User=Depends(current_user)):
 today=date.today(); start=today.replace(day=1); rows,inc,exp=totals(s,u,start,today); budget=s.query(Budget).filter_by(user_id=u.id,month=today.strftime('%Y-%m'),category_id=None).first(); counts={}
 for t in rows:
  if t.type=='expense' and t.category: counts[t.category.name]=counts.get(t.category.name,0)+t.amount
 top=max(counts,key=counts.get) if counts else None; allrows=s.query(Transaction).filter_by(user_id=u.id).all(); balance=sum(t.amount if t.type=='income' else -t.amount for t in allrows)
 return {'balance':balance,'income':inc,'expenses':exp,'savings':inc-exp,'budget':budget.amount if budget else 0,'budget_remaining':(budget.amount-exp) if budget else 0,'top_category':top,'top_category_amount':counts.get(top,0) if top else 0,'recent':[txdict(t) for t in s.query(Transaction).filter_by(user_id=u.id).order_by(Transaction.date.desc(),Transaction.id.desc()).limit(8)]}
@app.get('/api/balance')
def balance(s:Session=Depends(db),u:User=Depends(current_user)):
 totals=s.query(
  func.coalesce(func.sum(case((Transaction.type=='income',Transaction.amount),else_=0)),0),
  func.coalesce(func.sum(case((Transaction.type=='expense',Transaction.amount),else_=0)),0)
 ).filter(Transaction.user_id==u.id).one()
 income,expenses=(float(totals[0]),float(totals[1]))
 return {'balance':income-expenses,'total_income':income,'total_expenses':expenses}
@app.get('/api/financial-summary')
def financial_summary_endpoint(period:Optional[str]=None,start_date:Optional[date]=None,end_date:Optional[date]=None,s:Session=Depends(db),u:User=Depends(current_user)):
 if period is not None and (start_date is not None or end_date is not None): raise HTTPException(422,'Use either period or start_date/end_date, not both')
 return financial_summary(s,u,period or 'month',start_date,end_date)
@app.get('/api/spending-analytics')
def spending_analytics_endpoint(period:Optional[str]=None,start_date:Optional[date]=None,end_date:Optional[date]=None,s:Session=Depends(db),u:User=Depends(current_user)):
 if period is not None and (start_date is not None or end_date is not None): raise HTTPException(422,'Use either period or start_date/end_date, not both')
 return spending_analytics(s,u,period or 'month',start_date,end_date)
@app.get('/api/analytics')
def analytics(period:Optional[str]=None,start_date:Optional[date]=None,end_date:Optional[date]=None,s:Session=Depends(db),u:User=Depends(current_user)):
 if period is not None and (start_date is not None or end_date is not None): raise HTTPException(422,'Use either period or start_date/end_date, not both')
 start,today,previous_start,previous_end,current,previous=comparison_context(s,u,period or 'month',start_date,end_date); rows,inc,exp=current['rows'],current['income'],current['expenses']; by={}; trend={}
 for t in rows:
  if t.type=='expense':by[t.category.name if t.category else 'Uncategorized']=by.get(t.category.name if t.category else 'Uncategorized',0)+t.amount
  key=t.date.isoformat(); trend.setdefault(key,{'income':0,'expenses':0}); trend[key]['income' if t.type=='income' else 'expenses']+=t.amount
 if start_date is not None or end_date is not None:
  cursor=start
  while cursor<=today:
   trend.setdefault(cursor.isoformat(),{'income':0,'expenses':0})
   cursor+=timedelta(days=1)
 response={'period':'custom' if start_date is not None or end_date is not None else period,'income':inc,'expenses':exp,'savings':inc-exp,'by_category':[{'name':k,'value':v} for k,v in sorted(by.items(),key=lambda z:-z[1])],'trend':[{'date':k,**v} for k,v in sorted(trend.items())],'comparison':{'previous_period':{'start':previous_start.isoformat(),'end':previous_end.isoformat()},'income':compare_values(inc,previous['income']),'expenses':compare_values(exp,previous['expenses']),'savings':compare_values(inc-exp,previous['income']-previous['expenses'])}}
 if start_date is not None or end_date is not None: response.update({'start_date':start.isoformat(),'end_date':today.isoformat()})
 return response
@app.get('/api/budgets')
def budgets(month:Optional[str]=None,s:Session=Depends(db),u:User=Depends(current_user)):
 month=month or date.today().strftime('%Y-%m'); bs=s.query(Budget).filter_by(user_id=u.id,month=month).all(); start=date.fromisoformat(month+'-01'); end=date(start.year+int(start.month/12),start.month%12+1,1)-timedelta(days=1); rows,_,_=totals(s,u,start,end)
 return [{'id':b.id,'month':b.month,'amount':b.amount,'spent':sum(t.amount for t in rows if t.type=='expense' and (b.category_id is None or t.category_id==b.category_id)),'remaining':b.amount-sum(t.amount for t in rows if t.type=='expense' and (b.category_id is None or t.category_id==b.category_id)),'category':b.category.name if b.category else 'Overall','category_id':b.category_id} for b in bs]
@app.post('/api/budgets',status_code=201)
def budget(x:BudgetIn,s:Session=Depends(db),u:User=Depends(current_user)): b=Budget(user_id=u.id,**x.model_dump()); s.add(b); s.commit(); s.refresh(b); return {'id':b.id,**x.model_dump()}
@app.get('/api/goals')
def goals(s:Session=Depends(db),u:User=Depends(current_user)): return [{'id':g.id,'name':g.name,'target':g.target,'saved':g.saved,'deadline':g.deadline.isoformat() if g.deadline else None,'progress':round(g.saved/g.target*100,1)} for g in s.query(Goal).filter_by(user_id=u.id).order_by(Goal.created_at.desc())]
@app.post('/api/goals',status_code=201)
def goal(x:GoalIn,s:Session=Depends(db),u:User=Depends(current_user)): g=Goal(user_id=u.id,**x.model_dump()); s.add(g); s.commit(); s.refresh(g); return {'id':g.id,**x.model_dump(),'progress':g.saved/g.target*100}
@app.post('/api/goals/{id}/contribute')
def contribute(id:int,x:Contrib,s:Session=Depends(db),u:User=Depends(current_user)):
 g=s.query(Goal).filter_by(id=id,user_id=u.id).first()
 if not g: raise HTTPException(404,'Goal not found')
 g.saved+=x.amount; s.commit(); return {'saved':g.saved,'progress':min(100,g.saved/g.target*100)}
@app.get('/api/insights')
def insights(s:Session=Depends(db),u:User=Depends(current_user)):
 d=dashboard(s,u); out=[]
 if d['expenses']>d['budget']>0:out.append({'type':'warning','title':'Budget exceeded','body':f"You’re ₹{d['expenses']-d['budget']:,.0f} over your monthly budget."})
 if d['top_category']:out.append({'type':'info','title':f"{d['top_category']} leads spending",'body':f"{d['top_category']} is your largest category this month."})
 return out or [{'type':'info','title':'More data, better insights','body':'Add a few transactions to unlock personalized spending patterns.'}]
@app.post('/api/ai/ask')
def ask(x:Ask,s:Session=Depends(db),u:User=Depends(current_user)):
 today=date.today(); rows,inc,exp=totals(s,u,today.replace(day=1),today); q=x.question.lower()
 if 'save' in q:return {'answer':f'You saved ₹{inc-exp:,.0f} this month (income ₹{inc:,.0f} minus expenses ₹{exp:,.0f}).'}
 e=max((t for t in rows if t.type=='expense'),key=lambda z:z.amount,default=None)
 if 'biggest' in q or 'largest' in q:return {'answer':f'Your biggest expense this month was {e.title} at ₹{e.amount:,.0f}.' if e else 'No expenses recorded this month.'}
 return {'answer':f'This month you spent ₹{exp:,.0f} across {len([t for t in rows if t.type=="expense"])} expenses.'}
@app.post('/api/import/preview')
async def import_preview(file:UploadFile=File(...),u:User=Depends(current_user)):
 if not file.filename.lower().endswith('.csv'): raise HTTPException(400,'Please upload a CSV file')
 raw=await file.read()
 if len(raw)>5_000_000: raise HTTPException(400,'File too large')
 rows=[]; errors=[]
 for i,r in enumerate(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))),2):
  try: rows.append({'title':r.get('title') or r.get('description'),'amount':abs(float((r.get('amount') or '').replace(',','').replace('₹',''))),'date':date.fromisoformat((r.get('date') or '')[:10]).isoformat(),'type':(r.get('type') or 'expense').lower(),'category':r.get('category') or 'Other','payment_method':r.get('payment_method') or 'Other'})
  except Exception: errors.append({'row':i,'error':'Invalid date or amount'})
 return {'rows':rows[:500],'errors':errors,'total':len(rows)}
@app.post('/api/import/commit')
def import_commit(payload:list[dict],s:Session=Depends(db),u:User=Depends(current_user)):
 count=0
 for row in payload:
  c=s.query(Category).filter(func.lower(Category.name)==str(row.get('category','')).lower()).first(); x=TxIn(title=row['title'],amount=row['amount'],type=row.get('type','expense'),category_id=c.id if c else None,date=row['date'],payment_method=row.get('payment_method','Other'),notes=row.get('notes',''),merchant=row.get('merchant',row['title'])); s.add(Transaction(user_id=u.id,**x.model_dump())); count+=1
 s.commit(); return {'imported':count}
@app.get('/api/recurring')
def recurring(s:Session=Depends(db),u:User=Depends(current_user)): return []
