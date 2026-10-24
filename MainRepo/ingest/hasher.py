"""
Premise Anonymizer: Generates deterministic, salted SHA-256 hash keys.
Guarantees privacy (Brief R17) by ensuring raw premise numbers and addresses never leave the ingestion boundary.
"""

import hashlib
import os
import secrets
from typing import Optional

SALT_FILE = ".salt"
DEFAULT_DEV_SALT = "hackohio_2026_aep_secure_salt_8f7b2c"


class PremiseHasher:
    def __init__(self, salt: Optional[str] = None, salt_path: str = SALT_FILE):
        if salt:
            self.salt = salt
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
