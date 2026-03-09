from fastapi import APIRouter, Depends

from app.core.deps import get_current_user
from app.schemas.common import UserOut


router = APIRouter(tags=['users'])


@router.get('/me', response_model=UserOut)
def me(current_user=Depends(get_current_user)):
    return UserOut.model_validate(current_user)
