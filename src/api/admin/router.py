from fastapi import APIRouter, Depends

from src.api.admin.deps import require_admin
from src.api.admin.routes import actions, ai, matches, settings, teams

admin_router = APIRouter(
    prefix="/api/admin/v1",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)

admin_router.include_router(matches.router)
admin_router.include_router(teams.router)
admin_router.include_router(ai.router)
admin_router.include_router(settings.router)
admin_router.include_router(actions.router)
