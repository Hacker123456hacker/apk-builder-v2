from sqlalchemy import create_engine, Column, String, DateTime, Text, Integer, Boolean, JSON
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "app.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Session(Base):
    __tablename__ = "sessions"
    id = Column(String, primary_key=True)
    encrypted_github_token = Column(Text, nullable=False)
    github_login = Column(String, nullable=True)
    github_avatar_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class BuildJob(Base):
    __tablename__ = "build_jobs"
    id = Column(String, primary_key=True)
    session_id = Column(String, nullable=False, index=True)
    project_name = Column(String, nullable=False)
    project_type = Column(String, nullable=False)
    repo_full_name = Column(String, nullable=False)
    build_type = Column(String, default="apk")

    # Phases: analyzing | fixing | uploading | building | done | error
    phase = Column(String, default="analyzing")
    status = Column(String, default="queued")  # final build status

    # Fix engine results
    issues_found = Column(Integer, default=0)
    issues_fixed = Column(Integer, default=0)
    fix_log = Column(JSON, default=list)          # list of {category, issue, fix, severity}
    fixed_zip_path = Column(String, nullable=True)

    # GitHub Actions
    run_id = Column(String, nullable=True)
    html_url = Column(String, nullable=True)
    artifact_download_url = Column(String, nullable=True)
    artifact_name = Column(String, nullable=True)
    artifact_size_bytes = Column(Integer, nullable=True)

    # AI analysis
    ai_error_summary = Column(Text, nullable=True)
    ai_suggestions = Column(JSON, default=list)

    log_summary = Column(Text, nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
