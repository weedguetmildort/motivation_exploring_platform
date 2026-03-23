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
│   │   │   ├── demographics.py
│   │   │   ├── questions.py
│   │   │   ├── quiz.py
│   │   │   └── surveys.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   └── security.py
│   │   ├── schemas/
│   │   │   ├── auth.py
│   │   │   ├── message.py
│   │   │   ├── question.py
│   │   │   ├── quiz.py
│   │   │   ├── survey.py
│   │   │   └── user.py
│   │   ├── services/
│   │   │   ├── chat.py
│   │   │   ├── followup.py
│   │   │   ├── questions.py
│   │   │   ├── quiz.py
│   │   │   ├── search.py
│   │   │   ├── surveys.py
│   │   │   └── users.py
│   │   └── main.py
│   ├── Dockerfile
│   └── requirements.txt
│
├── frontend/
│   ├── components/
│   │   ├── AnswerBox.tsx
│   │   ├── AuthForm.tsx
│   │   ├── ChatBox.tsx
│   │   ├── Disclaimer.tsx
│   │   ├── MarkdownMessage.tsx
│   │   ├── MentionSuggestions.tsx
│   │   └── QuestionBox.tsx
│   ├── lib/
│   │   ├── auth.ts
│   │   ├── chat.ts
│   │   ├── demographics.ts
│   │   ├── fetcher.ts
│   │   ├── mentions.ts
│   │   ├── messageMetadataStore.ts
│   │   ├── quiz.ts
│   │   ├── quizSurvey.ts
│   │   └── surveys.ts
│   ├── pages/
│   │   ├── quiz/
│   │   │   └── [quiz_id].tsx
│   │   ├── _app.tsx
│   │   ├── admin.tsx
│   │   ├── chat.tsx
│   │   ├── dashboard.tsx
│   │   ├── demographics.tsx
│   │   ├── index.tsx
│   │   ├── login.tsx
│   │   ├── playground.tsx
│   │   ├── profile.tsx
│   │   ├── questions_panel.tsx
│   │   ├── signup.tsx
│   │   ├── survey.tsx
│   │   └── surveys_panel.tsx
│   ├── public/
│   │   └── favicon.png
│   ├── styles/
│   │   └── globals.css
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
Frontend
- Deployed as a Node container:
- Uses NEXT_PUBLIC_API_URL handled by GitHub Secrets
- Built via GitHub Actions CI
Backend
- Deployed as its own Heroku container
- Uses production MongoDB connection string
- Secure cookies enforced in production
GitHub Secrets Required
Frontend:
```
BACKEND_URL=https://<your-backend>.herokuapp.com
```
Backend:
```
MONGO_URL=<mongodb atlas uri>
COOKIE_DOMAIN=.herokuapp.com
JWT_SECRET=<your secret>
COOKIE_SECURE=true
```

## ⚙️ Environment Variables

Backend (.env)
```
MONGO_URL=mongodb://localhost:27017/motivation
JWT_SECRET=your-secret-key
JWT_EXPIRES_MIN=60
COOKIE_NAME=session
COOKIE_SECURE=false (true in production)
COOKIE_DOMAIN=localhost
SAMESITE=lax
```
Frontend (.env.local)
```
BACKEND_URL=http://localhost:8000
```

## 🧭 Running Locally

**With Docker (recommended):**
```
docker-compose up --build
```
Frontend → http://localhost:3000
Backend → http://localhost:8000
Mongo Express (optional) → http://localhost:8081
**Without Docker:**
```
# backend
cd backend
uvicorn app.main:app --reload

# frontend
cd frontend
npm install
npm run dev
```

## 👣 Next Steps
- User Conversation logging
- User progress tracking

## 🛡️ Security

- HTTP-only cookies prevent client-side JS access
- Argon2id hashing for password safety
- Server-side session validation on every request
- No sensitive data exposed to frontend
- Admin-only pages are server-enforced

## 📄 License
MIT — free to use, modify, and distribute.
