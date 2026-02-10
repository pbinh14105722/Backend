from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from fastapi.security import OAuth2PasswordBearer

# Tôi đã thêm ?sslmode=require vào cuối link để Render không chặn kết nối
SQLALCHEMY_DATABASE_URL = "postgresql://postgres.quarzvpkrjjdhhnekwka:binh14105722@aws-1-ap-southeast-1.pooler.supabase.com:6543/postgres?sslmode=require"

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
