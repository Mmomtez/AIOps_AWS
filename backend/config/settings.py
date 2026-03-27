# Global config (AWS, LLM, Langfuse)
from dotenv import load_dotenv
import os

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

AWS_REGION = os.getenv("AWS_REGION")
if not AWS_REGION:
    raise ValueError("AWS_REGION is not set in .env")


INSTANCE_ID = os.getenv("INSTANCE_ID")
if not INSTANCE_ID:
    raise ValueError("INSTANCE_ID is not set in .env")

S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
if not S3_BUCKET_NAME:
    raise ValueError("S3_BUCKET_NAME is not set in .env")

LOG_GROUP_NAME = os.getenv("LOG_GROUP_NAME")
if not LOG_GROUP_NAME:
    raise ValueError("LOG_GROUP_NAME is not set in .env")