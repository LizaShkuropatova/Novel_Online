import os
from dotenv import load_dotenv
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from contextlib import asynccontextmanager

from utils.firebase import init_firebase, get_db

from routes.auth_routes import router as auth_router
from routes.novel_routes import router as novel_router
from routes.ai_routes import router as ai_router
from routes.multiplayer_routes  import router as multiplayer_router
from routes.friend_routes import router as friends_router

# Завантажуємо змінні оточення
load_dotenv()

@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_firebase()
    yield

app = FastAPI(
  title="Interactive Novel API",
  lifespan=lifespan,
  dependencies=[Depends(get_db)]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:3000"],  # Nuxt/Vue dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Реєстрація роутерів
app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(novel_router, prefix="/novels", tags=["novels"])
app.include_router(ai_router, prefix="/ai", tags=["ai"])
app.include_router(multiplayer_router,  prefix="/sessions",  tags=["multiplayer"])
app.include_router(friends_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=True,
    )
