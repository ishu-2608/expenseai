ExpenseAI — AI-Powered Personal Expense Management

ExpenseAI is a full-stack personal finance management application designed to help users track, understand, and analyze their spending.

It combines a FastAPI backend, PostgreSQL database, and React/Vite frontend with analytics and AI-assisted financial insights. The application provides secure authentication, expense management, budgeting, savings goals, interactive analytics, and natural-language financial queries.

🚀 Live Demo

Frontend: https://expenseai-inky.vercel.app

Backend API: https://expenseai-production-54e4.up.railway.app

API Documentation: https://expenseai-production-54e4.up.railway.app/docs

⸻

✨ Features

🔐 Authentication & Security

* User registration and login
* JWT-based authentication
* Bcrypt password hashing
* Per-user data isolation
* Protected API endpoints
* CORS configuration for production and development environments

💰 Expense Management

* Add, edit, and delete expenses
* Categorize transactions
* Search and filter transactions
* Income and expense tracking
* CSV preview/import support
* Recent transaction activity

📊 Financial Analytics

* Total balance
* Income and expense summaries
* Savings tracking
* Spending trends
* Category-wise spending analysis
* Weekly, monthly, and yearly analytics
* Budget health monitoring

🎯 Budget & Savings Goals

* Monthly budget tracking
* Budget progress monitoring
* Savings goals
* Goal contributions
* Financial progress visualization

🤖 AI-Assisted Financial Intelligence

* Natural-language expense queries
* Financial insights based on user spending data
* Deterministic financial analysis
* Safe query processing without allowing arbitrary SQL execution

🎨 User Experience

* Responsive React interface
* Desktop and mobile support
* Dark/light theme
* Interactive charts and dashboards
* Mobile-friendly layout

⸻

🛠️ Tech Stack

Frontend

* React
* Vite
* JavaScript
* CSS
* Recharts

Backend

* Python
* FastAPI
* SQLAlchemy
* JWT
* Bcrypt
* Pydantic

Database

* PostgreSQL
* SQLite for local development

Deployment

* Frontend: Vercel
* Backend: Railway
* Database: Railway PostgreSQL
* Version Control: Git & GitHub

⸻

🏗️ Architecture

                    ┌──────────────────────┐
                    │       User           │
                    │ Desktop / Mobile     │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │   React + Vite       │
                    │      Vercel          │
                    └──────────┬───────────┘
                               │ REST API
                               ▼
                    ┌──────────────────────┐
                    │      FastAPI         │
                    │      Railway         │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │     SQLAlchemy       │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │ PostgreSQL Database  │
                    │      Railway         │
                    └──────────────────────┘

⸻

📁 Project Structure

expenseai/
│
├── backend/
│   ├── app/
│   │   └── main.py
│   ├── requirements.txt
│   └── ...
│
├── frontend/
│   ├── src/
│   │   ├── main.jsx
│   │   └── ...
│   ├── index.html
│   ├── package.json
│   └── ...
│
├── .gitignore
└── README.md

⸻

⚙️ Run Locally

1. Clone the repository

git clone https://github.com/ishu-2608/expenseai.git
cd expenseai

2. Set up the backend

cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

Start the backend:

uvicorn app.main:app --reload

Backend will be available at:

http://localhost:8000

API documentation:

http://localhost:8000/docs

3. Set up the frontend

Open another terminal:

cd frontend
npm install
npm run dev

Frontend will be available at:

http://localhost:5173

⸻

🔑 Environment Variables

Backend

Create a .env file inside backend/:

DATABASE_URL=<database-url>
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
JWT_SECRET=<your-secret>
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=10080
APP_ENV=development
SEED_DEMO_DATA=false

Frontend

For local development:

VITE_API_URL=http://localhost:8000/api

For production:

VITE_API_URL=https://expenseai-production-54e4.up.railway.app/api

Never commit .env files or API secrets to GitHub.

⸻

☁️ Production Deployment

Frontend — Vercel

The React/Vite frontend is deployed on Vercel.

Production API configuration:

VITE_API_URL=https://expenseai-production-54e4.up.railway.app/api

Backend — Railway

The FastAPI backend is deployed on Railway.

Production backend:

https://expenseai-production-54e4.up.railway.app

Database — PostgreSQL

ExpenseAI uses PostgreSQL in production through Railway.

The backend uses SQLAlchemy for database interaction and supports SQLite for local development.

⸻

🧪 Testing

Backend tests:

cd backend
PYTHONPATH=. pytest -q

Frontend production build:

cd frontend
npm run build

⸻

🔒 Security

ExpenseAI implements several security measures:

* JWT-based authentication
* Bcrypt password hashing
* Protected API endpoints
* User-level data isolation
* Environment-based secret management
* CORS restrictions
* Input validation
* No arbitrary SQL execution through natural-language queries

⸻

🔮 Future Improvements

Potential future improvements include:

* Database migrations with Alembic
* Receipt OCR
* Recurring transaction automation
* More advanced AI-powered financial recommendations
* Additional financial visualizations
* Optional hosted LLM integration
* Exportable financial reports

⸻

👨‍💻 Author

Ishu Yadav

B.Tech Computer Science Engineering

Interested in AI/ML, Data Science, Generative AI, and Full-Stack Development.

GitHub: https://github.com/ishu-2608