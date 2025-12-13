# Global config for backend server
from dotenv import load_dotenv
import os

load_dotenv()
BACKEND_CONFIG: dict[str, str | float] = {
    "base_url": os.getenv("BACKEND_URL", "http://localhost:8001"),
    "timeout": 30.0,
}
