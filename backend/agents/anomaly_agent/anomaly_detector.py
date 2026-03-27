# Anomaly detection logic

from backend.pipelines.inference_pipeline import run_inference_pipeline


def detect_anomaly():
    return run_inference_pipeline()


if __name__ == "__main__":
    result = detect_anomaly()
    print(result)