import os
from typing import Dict, List, Any

def ensure_download_dir(directory: str) -> None:
    """Ensures download directory exists"""
    os.makedirs(directory, exist_ok=True)