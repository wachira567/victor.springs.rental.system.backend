from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

# We will use SQLite for development as per the sample, but allow overriding via .env for PostgreSQL in production
SQLALCHEMY_DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./rental_database.db")

# For SQLite, we must pass check_same_thread=False
# If using PostgreSQL, engine args are empty
connect_args = {"check_same_thread": False} if "sqlite" in SQLALCHEMY_DATABASE_URL else {}

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args=connect_args, echo=True
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
