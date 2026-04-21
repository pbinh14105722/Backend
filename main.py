from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import models, database

# Import all routers
import auth
import items
import tasks
import username_password_update
import pomodoro
import statistic
import sort
import filter as filter_router
import roadmap
import chatbot

app = FastAPI()

# Tạo bảng trong DB (chỉ dùng cho demo, thực tế nên dùng Alembic)
# models.Base.metadata.create_all(bind=database.engine)

import os
from dotenv import load_dotenv

load_dotenv()

# Cấu hình CORS
allowed_origins = os.getenv("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins, # Cho phép các nguồn từ .env
    allow_credentials=True,
    allow_methods=["*"], # Có thể hạn chế các phương thức nếu cần thiết
    allow_headers=["*"], # Có thể hạn chế các headers
)

# =====================================================================
# Đăng ký các Router vào app (gộp các chức năng từ file rời)
# =====================================================================

app.include_router(auth.router)
app.include_router(items.router)
app.include_router(tasks.router)

# Các Router khác
app.include_router(username_password_update.router)
app.include_router(pomodoro.router)
app.include_router(statistic.router)
app.include_router(sort.router)
app.include_router(filter_router.router)
app.include_router(roadmap.router)
app.include_router(chatbot.router)

# Simple health check endpoint
@app.api_route('/health', methods=['GET', 'HEAD'])
def health():
    return {"status": "ok"}
