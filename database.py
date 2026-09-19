"""
Database configuration and session management for Task Management API.

This module sets up SQLAlchemy engine, session factory, and provides
database dependency injection for FastAPI endpoints.
All sensitive credentials are loaded from environment variables.
"""

import os
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# =============================================================================
# DATABASE CONFIGURATION - Loaded from environment variables
# =============================================================================

SQLALCHEMY_DATABASE_URL = os.getenv("SQLALCHEMY_DATABASE_URL")
if not SQLALCHEMY_DATABASE_URL:
    raise ValueError(
        "DATABASE_URL not found in environment variables! "
        "Please set it in your .env file."
    )

# Optional: Get pool configuration from environment (with sensible defaults)
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "10"))
DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "20"))
DB_CONNECT_TIMEOUT = int(os.getenv("DB_CONNECT_TIMEOUT", "10"))

# =============================================================================
# ANTHROPIC API CONFIGURATION
# =============================================================================

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    print("⚠️  WARNING: ANTHROPIC_API_KEY not set. Chatbot features will be disabled.")

# =============================================================================
# SQLALCHEMY ENGINE SETUP
# =============================================================================

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True,  # Test connections before using them
    pool_size=DB_POOL_SIZE,
    max_overflow=DB_MAX_OVERFLOW,
    connect_args={
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5,
        "connect_timeout": DB_CONNECT_TIMEOUT,
    }
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()

# =============================================================================
# DATABASE DEPENDENCY INJECTION
# =============================================================================

def get_db() -> Generator[Session, None, None]:
    """
    Provide a database session for FastAPI endpoints.
    
    This dependency is injected into route handlers using FastAPI's
    Depends() mechanism. The session is automatically closed after the
    request completes.
    
    Yields:
        Session: SQLAlchemy database session
        
    Example:
        @router.get("/items")
        def get_items(db: Session = Depends(get_db)):
            return db.query(models.Item).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =============================================================================
# HEALTH CHECK & VALIDATION
# =============================================================================

def validate_database_connection() -> dict:
    """
    Validate database connection and return status.
    
    Returns:
        dict: Connection status information
        
    Example:
        >>> status = validate_database_connection()
        >>> print(status["status"])  # "✅ Connected" or "❌ Failed"
    """
    try:
        db = SessionLocal()
        # Try a simple query
        db.execute(text("SELECT 1"))
        db.close()
        return {
            "status": "✅ Connected",
            "url": SQLALCHEMY_DATABASE_URL.split("@")[1],  # Hide credentials
            "pool_size": DB_POOL_SIZE,
            "max_overflow": DB_MAX_OVERFLOW,
        }
    except Exception as e:
        return {
            "status": "❌ Failed",
            "error": str(e),
        }


if __name__ == "__main__":
    # For testing: validate database connection
    print("🗄️  Database Configuration:")
    status = validate_database_connection()
    for key, value in status.items():
        print(f"  {key}: {value}")
