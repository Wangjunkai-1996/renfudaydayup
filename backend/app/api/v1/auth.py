from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.security import clear_auth_cookies, set_auth_cookies
from app.schemas.auth import LoginRequest, SessionOut
from app.schemas.common import ApiMessage, UserOut
from app.services.auth import authenticate_user, create_session_tokens, refresh_session, revoke_session


router = APIRouter(prefix='/auth', tags=['auth'])


@router.post('/login', response_model=SessionOut)
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    user = authenticate_user(db, payload.username, payload.password)
    access_token, refresh_token, _ = create_session_tokens(
        db,
        user,
        user_agent=request.headers.get('user-agent'),
        ip_address=request.client.host if request.client else None,
    )
    set_auth_cookies(response, access_token, refresh_token)
    return SessionOut(user=UserOut.model_validate(user))


@router.post('/refresh', response_model=SessionOut)
def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    settings = get_settings()
    refresh_token_value = request.cookies.get(settings.refresh_cookie_name)
    access_token, refresh_token, user = refresh_session(
        db,
        refresh_token_value or '',
        user_agent=request.headers.get('user-agent'),
        ip_address=request.client.host if request.client else None,
    )
    set_auth_cookies(response, access_token, refresh_token)
    return SessionOut(user=UserOut.model_validate(user))


@router.post('/logout', response_model=ApiMessage)
def logout(request: Request, response: Response, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    settings = get_settings()
    revoke_session(db, request.cookies.get(settings.refresh_cookie_name))
    clear_auth_cookies(response)
    return ApiMessage(message=f'bye {current_user.username}')
