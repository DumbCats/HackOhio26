"""
Premise Anonymizer: Generates deterministic, salted SHA-256 hash keys.
Guarantees privacy (Brief R17) by ensuring raw premise numbers and addresses never leave the ingestion boundary.
"""

import hashlib
import os
import secrets
from typing import Optional

try:  # .env holds the shared CONCIERGE_SALT
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
except ImportError:
    pass

SALT_FILE = ".salt"
DEFAULT_DEV_SALT = "hackohio_2026_aep_secure_salt_8f7b2c"


class PremiseHasher:
    def __init__(self, salt: Optional[str] = None, salt_path: str = SALT_FILE):
        env_salt = os.environ.get("CONCIERGE_SALT", "").strip()
        if salt:
            self.salt = salt
        elif env_salt and env_salt != "change-me":
            # Shared team salt from .env: same salt on every machine -> same home ids (MASTER_PLAN Lane A).
            self.salt = env_salt
        elif os.path.exists(salt_path):
            with open(salt_path, "r", encoding="utf-8") as f:
                self.salt = f.read().strip()
        else:
            # Generate and persist salt for reproducible sessions
            self.salt = secrets.token_hex(16)
            try:
                with open(salt_path, "w", encoding="utf-8") as f:
                    f.write(self.salt)
            except OSError:
                self.salt = DEFAULT_DEV_SALT

    def hash_premise(self, premise_nu: str) -> str:
        """
        Hashes premise number with salt to produce a 16-character hexadecimal anonymous ID.
        Example output: 'p_8a4b2c1d9e3f0174'
        """
        clean_id = str(premise_nu).strip()
        h = hashlib.sha256(f"{self.salt}:{clean_id}".encode("utf-8")).hexdigest()
        return f"p_{h[:16]}"

    def hash_device(self, loc: str) -> str:
        """Salted key for a network device (topology token LOC field). Never leaves the backend."""
        h = hashlib.sha256(f"{self.salt}:dev:{str(loc).strip()}".encode("utf-8")).hexdigest()
        return f"d_{h[:12]}"
