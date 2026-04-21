import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

from backend.pipelines.ingestion_pipeline import run_ingestion_pipeline
from backend.pipelines.inference_pipeline import run_inference_pipeline
from backend.schemas.observation import Observation
from backend.schemas.anomaly_result import AnomalyResult
from backend.schemas.inference_response import InferenceResponse

router = APIRouter(prefix="/api", tags=["aiops"])


def _read_latest_json(folder: str):
    path = Path(folder)
    if not path.exists():
        return None

    files = sorted(path.glob("*.json"))
    if not files:
        return None

    latest_file = files[-1]
    with latest_file.open("r", encoding="utf-8") as f:
        return json.load(f)


@router.post("/run-ingestion", response_model=Observation)
def run_ingestion():
    observation = run_ingestion_pipeline()
    return observation


@router.post("/run-inference", response_model=InferenceResponse)
def run_inference():
    observation = run_ingestion_pipeline()
    result = run_inference_pipeline(observation)

    return InferenceResponse(
        observation=observation,
        result=result,
    )


@router.get("/latest-observation", response_model=Observation)
def get_latest_observation():
    observation = _read_latest_json("./data/observations")
    if not observation:
        raise HTTPException(status_code=404, detail="No observation found")
    return observation

@router.get("/latest-anomaly", response_model=AnomalyResult)
def get_latest_anomaly():
    result = _read_latest_json("./data/predictions")
    if not result:
        raise HTTPException(status_code=404, detail="No anomaly result found")
    return result