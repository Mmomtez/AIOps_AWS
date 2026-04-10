# backend/main.py

from backend.pipelines.ingestion_pipeline import run_ingestion_pipeline
from backend.pipelines.inference_pipeline import run_inference_pipeline

if __name__ == "__main__":
    observation = run_ingestion_pipeline()
    print("Observation:", observation)

    result = run_inference_pipeline(observation)
    print("Inference result:", result)