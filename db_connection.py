"""
PostgreSQL Database Connection using SQLAlchemy
Works on both local and Railway environments
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import QueuePool
import os
from models import Base

# ============================================
# DATABASE CONNECTION STRING
# ============================================

# Check if running on Railway (Railway provides DATABASE_URL)
# If not, use individual environment variables for local setup
if os.environ.get('DATABASE_URL'):
    # Railway environment - use DATABASE_URL directly
    # Railway's DATABASE_URL starts with postgres:// but SQLAlchemy needs postgresql://
    DATABASE_URL = os.environ.get('DATABASE_URL')
    if DATABASE_URL.startswith('postgres://'):
        DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
    print("🚂 Railway database connection detected")
else:
    # Local environment - use individual variables
    POSTGRES_USER = os.environ.get('POSTGRES_USER', 'postgres')
    POSTGRES_PASSWORD = os.environ.get('POSTGRES_PASSWORD', 'sajid123')
    POSTGRES_HOST = os.environ.get('POSTGRES_HOST', 'localhost')
    POSTGRES_PORT = os.environ.get('POSTGRES_PORT', '5432')
    POSTGRES_DB = os.environ.get('POSTGRES_DB', 'kitchen_guardian')
    
    DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    print("💻 Local database connection detected")

# ============================================
# CREATE ENGINE WITH CONNECTION POOLING
# ============================================

engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=10,          # Number of connections to keep open
    max_overflow=20,       # Max extra connections beyond pool_size
    pool_pre_ping=True,    # Verify connections before using
    pool_recycle=3600,     # Recycle connections after 1 hour
    echo=False             # Set to True for SQL query logging (development only)
)

# ============================================
# CREATE SESSION FACTORY
# ============================================

# Session factory for creating sessions
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False
)

# Scoped session for thread-safe access
db_session = scoped_session(SessionLocal)

# ============================================
# CREATE ALL TABLES
# ============================================

def init_db():
    """
    Create all tables in the database.
    Call this once when setting up the database.
    """
    Base.metadata.create_all(bind=engine)
    print("✅ All tables created successfully!")

# ============================================
# SESSION MANAGEMENT HELPER
# ============================================

def get_session():
    """
    Get a new database session.
    Always use with try/finally to ensure session.close() is called.
    
    Example usage:
        session = get_session()
        try:
            user = session.query(User).filter(User.email == email).first()
            session.commit()
        except Exception as e:
            session.rollback()
            raise
        finally:
            session.close()
    """
    return SessionLocal()

# ============================================
# CLEANUP
# ============================================

def close_db_session():
    """
    Remove the scoped session.
    Call this when shutting down the application.
    """
    db_session.remove()

# ============================================
# INITIALIZE DATABASE ON IMPORT
# ============================================

print("✅ PostgreSQL connection established")
print(f"🔗 Connection URL: {DATABASE_URL.split('@')[0]}@***")  # Hide password in logs