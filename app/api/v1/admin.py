from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile

from app.core.config import get_settings
from app.core.deps import require_admin
from app.schemas.admin import AdminActionResponse
from app.services.dataset_service import get_dataset_service

router = APIRouter(prefix="/admin", tags=["Admin"], dependencies=[Depends(require_admin)])


@router.post("/upload-dataset", response_model=AdminActionResponse)
async def upload_dataset(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    settings = get_settings()
    target = Path(settings.dataset_root) / "uploads" / file.filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(await file.read())
    background_tasks.add_task(get_dataset_service().ingest_file, target)
    return AdminActionResponse(status="accepted", detail=f"Uploaded {file.filename} and queued ingestion")


@router.post("/rebuild-embeddings", response_model=AdminActionResponse)
def rebuild_embeddings():
    result = get_dataset_service().rebuild()
    return AdminActionResponse(status="success", detail=f"Rebuilt embeddings for {result['files']} files")


@router.post("/reindex", response_model=AdminActionResponse)
def reindex(background_tasks: BackgroundTasks):
    background_tasks.add_task(get_dataset_service().ingest_all, False)
    return AdminActionResponse(status="accepted", detail="Dataset reindex started in background")


@router.get("/dataset-stats")
def dataset_stats():
    return get_dataset_service().stats()
