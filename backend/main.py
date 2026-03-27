from pipelines.ingestion_pipeline import run_ingestion_pipeline

if __name__ == "__main__":
    result = run_ingestion_pipeline()
    print("Pipeline result:", result)