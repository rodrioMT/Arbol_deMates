import os
from dotenv import load_dotenv

load_dotenv()
from dataclasses import dataclass

@dataclass
class Settings:
    project_id: str = os.getenv("GCP_PROJECT_ID", "")
    location: str = os.getenv("GCP_LOCATION", "us")
    processor_id: str = os.getenv("DOCAI_PROCESSOR_ID", "")
    db_path: str = os.getenv("TREECARE_DB", "data/treecare.sqlite")

settings = Settings()
