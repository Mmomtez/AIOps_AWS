# Entry point for running the system
from dotenv import load_dotenv
import os
from aws.collector_service import collect_metrics
from aws.storage import save_metrics
import logging

dotenv_path = os.path.join(os.path.dirname(__file__), "config", ".env")
load_dotenv(dotenv_path)  # Load environment variables from .env file
INSTANCE_ID = os.getenv("INSTANCE_ID")  # Get instance ID from environment variable

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

if __name__ == "__main__":
    metrics = collect_metrics("i-06c19ac0ef2862bd5")

    print("Collected:", metrics)

    save_metrics(metrics)