from fastapi import APIRouter

from app.routers.junior_shared_threads import router as threads_router
from app.routers.junior_shared_messages import router as messages_router
from app.routers.junior_shared_search import router as search_router
from app.routers.junior_shared_memories import router as memories_router
from app.routers.junior_shared_sessions import router as sessions_router
from app.routers.junior_shared_agents import router as agents_router
from app.routers.junior_shared_documents import router as documents_router
from app.routers.junior_shared_files import router as files_router
from app.routers.junior_shared_projects import router as projects_router

router = APIRouter(prefix="/junior", tags=["junior-shared-memory"])

router.include_router(threads_router)
router.include_router(messages_router)
router.include_router(search_router)
router.include_router(memories_router)
router.include_router(sessions_router)
router.include_router(agents_router)
router.include_router(documents_router)
router.include_router(files_router)
router.include_router(projects_router)
