# FastAPI endpoints
from fastapi import APIRouter

from backend.pipelines.ingestion_pipeline import run_ingestion_pipeline
from backend.pipelines.inference_pipeline import run_inference_pipeline

router = APIRouter(prefix="/api", tags=["aiops"])


@router.post("/run-inference")
def run_inference():
    observation = run_ingestion_pipeline()
    result = run_inference_pipeline(observation)

    return {
        "observation": observation.model_dump(mode="json"),
        "result": result.model_dump(mode="json"),
    }