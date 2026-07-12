import secrets
from fastapi import Request, HTTPException, Depends
from sqlalchemy.orm import Session as DBSession
from .database import get_db, Session as SessionModel
from .crypto import decrypt_token

SESSION_COOKIE_NAME = "apk_builder_session"


def generate_session_id() -> str:
    return secrets.token_urlsafe(32)


def get_current_session(request: Request, db: DBSession = Depends(get_db)) -> SessionModel:
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_id:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=401, detail="Session expired. Please reconnect GitHub.")
    return session


def get_optional_session(request: Request, db: DBSession = Depends(get_db)):
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_id:
        return None
    return db.query(SessionModel).filter(SessionModel.id == session_id).first()


def get_decrypted_token(session: SessionModel) -> str:
    return decrypt_token(session.encrypted_github_token)
