# Motivation Exploring Platform — Full-Stack Project

A secure, modular, and fully containerized full-stack platform for interactive learning, adaptive questioning, and AI-assisted exploration.  
This system includes user authentication, admin content management, question bank storage, and an AI-powered chat interface enriched with follow-up question suggestions.

## 🚀 Tech Stack

### Frontend
- Next.js
- React + TypeScript
- TailwindCSS
- JWT-based session cookies
- Chat UI with dynamic follow-ups

### Backend
- FastAPI
- Argon2 password hashing
- Secure session cookies
- Pydantic
- MongoDB integration
- AI chat generation

### Database
- MongoDB

### DevOps
- Docker + Docker Compose for local development
- Separate frontend/backend containers
- Heroku deployment for both services (container stack)
- GitHub Actions CI/CD for automatic deploys
- Environment-variable–based configuration (frontend + backend)

## 📦 Project Structure

```
/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── auth.py
│   │   │   ├── chat.py
│   │   │   ├── questions.py
│   │   ├── schemas/
│   │   ├── services/
│   │   ├── core/
│   │   ├── main.py
│   ├── Dockerfile
│   └── requirements.txt
│
├── frontend/
│   ├── pages/
│   │   ├── index.tsx
│   │   ├── login.tsx
│   │   ├── signup.tsx
│   │   ├── dashboard.tsx
│   │   ├── admin.tsx
│   │   ├── playground.tsx
│   ├── components/
│   │   ├── ChatBox.tsx
│   │   ├── QuestionBox.tsx
│   │   ├── AnswerBox.tsx
│   │   ├── FollowUpQuestionBox.tsx
│   ├── lib/
│   │   ├── auth.ts
│   │   ├── fetcher.ts
│   └── Dockerfile
│
├── docker-compose.yml
└── README.md
```


## 🌐 Key Features

✅ Authentication System
- Signup, login, and logout
- Argon2 password hashing
- Secure HTTP-only cookie-based sessions
- Automatic session validation via /auth/me

👑 Admin Panel
Admins can:
- Create questions
- View all questions
- Edit or delete questions (UI coming soon)
- Manage platform content
All users:
- Cannot access /admin
- Cannot view admin-only components (Playground button hidden)
- Admin status is stored in MongoDB:
```
{
  "is_admin": true
}
```

📚 Dynamic Question Bank

Each question includes:
- stem (title)
- subtitle
- Array of multiple-choice answers
- Stored in questions collection in MongoDB
Backend routes:
- POST /questions/
- GET /questions/
- PUT /questions/:id (coming soon)
- DELETE /questions/:id (coming soon)

🤖 AI Chat + Follow-Up Questions
- ChatBox component communicates with backend /chat
- AI assistant replies with custom instruction prompts
- Optional follow-up question suggestions appear after each AI message
- Follow-up selection injects directly into the chat

🧪 Playground Page
- Used during development to preview question/choice combinations:
- Loads real questions from DB
- Allows cycling through question list
- Chat integrated on the right
- Two modes:
    - Base Case (no follow-ups)
    - Follow-Up Case (dynamic follow-up questions appear)

🐳 Dockerized Development
Local dev uses:
```
docker-compose up --build
```
This creates:
- Frontend container
- Backend container
Hot reload works on both frontend and backend.

## 🌍 Production Deployment (Heroku)


## ⚙️ Environment Variables

(See full README in previous message.)

## 🧭 Running Locally

**Docker:**
```
docker-compose up --build
```

**Without Docker:**
```
# backend
uvicorn app.main:app --reload

# frontend
npm run dev
```

## 👣 Next Steps
- User Conversation logging
- User progress tracking

## 🛡️ Security

- HTTP-only cookies
- Argon2 hashing
- Server-side auth checks

## 📄 License
MIT
