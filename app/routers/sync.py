from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from ..deps import get_current_user
from ..models import User

router = APIRouter(prefix="/sync", tags=["automatic sync (future)"])


@router.post("", summary="Placeholder for future automatic bank sync")
def sync_transactions(user: User = Depends(get_current_user)):
    return JSONResponse(
        status_code=501,
        content={
            "status": "not_implemented",
            "message": "Automatic sync isn't available yet. Finsathi will connect to an authorized "
            "financial-data provider in a future update — no passwords, ever.",
        },
    )
