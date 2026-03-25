# Entry point for running the system
from dotenv import load_dotenv
import os
from aws.collector_service import collect_metrics
from aws.storage import save_metrics
import logging
from config.settings import INSTANCE_ID

# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s [%(levelname)s] %(message)s",
#     datefmt="%Y-%m-%d %H:%M:%S",
# )

if __name__ == "__main__":
    metrics = collect_metrics(INSTANCE_ID)

    print("Collected:", metrics)

    save_metrics(metrics)