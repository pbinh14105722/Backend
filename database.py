from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from fastapi.security import OAuth2PasswordBearer

# Tôi đã thêm ?sslmode=require vào cuối link để Render không chặn kết nối
SQLALCHEMY_DATABASE_URL = "postgresql://postgres.quarzvpkrjjdhhnekwka:binh14105722@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres"

# --- THAY ĐỔI Ở ĐÂY: Tăng thời gian chờ lên 60 giây ---
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True,       # Kiểm tra kết nối trước khi dùng
#    pool_size=10,            # Nên giới hạn số lượng kết nối tới Supabase
#    max_overflow=20,
    connect_args={
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5,
        "connect_timeout": 10  # Đợi tối đa 10 giây
    }
)
# -----------------------------------------------------

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

#oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
