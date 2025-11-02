# motivation_exploring_platform

https://ai-exploration-frontend-4dc13593856a.herokuapp.com/

docker run --rm -it -v "$PWD/../frontend":/app -w /app node:20 \
  sh -lc "npm i -D typescript @types/react @types/react-dom @types/node"


frontend/
├─ components/
│  └─ chat/
│     ├─ ChatBox.tsx            # container component (wires list + input)
│     ├─ MessageList.tsx        # dumb UI component
│     ├─ MessageInput.tsx       # dumb UI component
│     ├─ TypingIndicator.tsx    # tiny UI piece (optional)
│     └─ index.ts               # re-exports for clean imports
├─ hooks/
│  └─ useChat.ts                # state machine for chat
├─ lib/
│  ├─ api/
│  │  └─ chatClient.ts          # fetchers only; no React code
│  └─ types.ts                  # shared TS types (Message, Role, ChatResponse)
├─ pages/
│  └─ index.tsx                 # imports <ChatBox /> when you’re ready



backend/app/
├─ api/
│  ├─ v1/
│  │  ├─ chat.py          # router for chat endpoints
│  │  └─ __init__.py
│  └─ __init__.py
├─ schemas/               # Pydantic models (ChatRequest, ChatResponse)
├─ services/              # business logic (e.g., llm.py, scoring.py)
├─ core/                  # settings, logging, cors, security
└─ main.py                # creates FastAPI app and includes routers
