import os
from fastapi import APIRouter, Depends, Response, Request
from sqlalchemy.orm import Session as DBSession
from pydantic import BaseModel
from ..database import get_db, Session as SessionModel
from ..crypto import encrypt_token
from ..services.github_service import GitHubService
from ..session import SESSION_COOKIE_NAME, generate_session_id, get_optional_session

router = APIRouter(prefix="/api/auth", tags=["auth"])


class ConnectRequest(BaseModel):
    token: str


@router.post("/connect")
async def connect(body: ConnectRequest, response: Response, db: DBSession = Depends(get_db)):
    token = body.token.strip()
    if not token:
        return {"success": False, "error": "Token cannot be empty."}
    result = await GitHubService(token).validate_token()
    if not result["valid"]:
        return {"success": False, "error": result["error"]}
    user = result["user"]
    session_id = generate_session_id()
    db.add(SessionModel(
        id=session_id,
        encrypted_github_token=encrypt_token(token),
        github_login=user.get("login"),
        github_avatar_url=user.get("avatar_url"),
    ))
    db.commit()
    is_prod = os.environ.get("RAILWAY_ENVIRONMENT") is not None or os.environ.get("ENV", "").lower() == "production"
    response.set_cookie(
        key=SESSION_COOKIE_NAME, value=session_id, httponly=True,
        samesite="lax", secure=is_prod, max_age=60*60*24*30,
    )
    return {"success": True, "user": {"login": user.get("login"), "name": user.get("name") or user.get("login"), "avatar_url": user.get("avatar_url")}}


@router.get("/me")
async def me(session=Depends(get_optional_session)):
    if not session:
        return {"authenticated": False}
    return {"authenticated": True, "user": {"login": session.github_login, "avatar_url": session.github_avatar_url}}


@router.post("/logout")
async def logout(response: Response, request: Request, db: DBSession = Depends(get_db)):
    sid = request.cookies.get(SESSION_COOKIE_NAME)
    if sid:
        db.query(SessionModel).filter(SessionModel.id == sid).delete()
        db.commit()
    response.delete_cookie(SESSION_COOKIE_NAME)
    return {"success": True}
