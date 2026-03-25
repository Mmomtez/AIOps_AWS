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