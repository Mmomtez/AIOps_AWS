# Global config (AWS, LLM, Langfuse)
from dotenv import load_dotenv
import os
from datetime import timedelta

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


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://aiops_user:aiops_password@localhost:5432/aiops",
)

JWT_ACCESS_SECRET = os.getenv("JWT_ACCESS_SECRET", "change-me-access-secret-at-least-32-chars")
JWT_REFRESH_SECRET = os.getenv("JWT_REFRESH_SECRET", "change-me-refresh-secret-at-least-32-chars")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_ISSUER = os.getenv("JWT_ISSUER", "aiops-auth")
JWT_AUDIENCE = os.getenv("JWT_AUDIENCE", "aiops-clients")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
EMAIL_TOKEN_EXPIRE_HOURS = int(os.getenv("EMAIL_TOKEN_EXPIRE_HOURS", "24"))
PASSWORD_RESET_EXPIRE_MINUTES = int(os.getenv("PASSWORD_RESET_EXPIRE_MINUTES", "30"))

LOCKOUT_THRESHOLD = int(os.getenv("LOCKOUT_THRESHOLD", "5"))
LOCKOUT_MINUTES = int(os.getenv("LOCKOUT_MINUTES", "15"))

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", "noreply@local.aiops")
FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", "http://localhost:3000")


ACCESS_TOKEN_EXPIRES = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
REFRESH_TOKEN_EXPIRES = timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)