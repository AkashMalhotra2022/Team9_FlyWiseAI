import os
import json
import re
import hashlib
from typing import Dict, Tuple, List

USERS_FILE = os.environ.get("FLYWISE_USERS_FILE", "users.json")

def _ensure_file() -> None:
    if not os.path.exists(USERS_FILE):
        os.makedirs(os.path.dirname(USERS_FILE), exist_ok=True) if os.path.dirname(USERS_FILE) else None
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f)

def load_users() -> Dict[str, Dict[str, str]]:
    _ensure_file()
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_users(users: Dict[str, Dict[str, str]]) -> None:
    os.makedirs(os.path.dirname(USERS_FILE), exist_ok=True) if os.path.dirname(USERS_FILE) else None
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2)

def hash_password(password: str) -> str:
    return hashlib.sha256((password or "").encode("utf-8")).hexdigest()

def validate_email(email: str) -> bool:
    e = (email or "").strip()
    return re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", e) is not None

def validate_password(password: str) -> Tuple[bool, List[str]]:
    """Return (is_valid, errors). Rules: >=8 chars, 1 upper, 1 lower, 1 digit, 1 special."""
    p = password or ""
    errs = []
    if len(p) < 8: errs.append("At least 8 characters.")
    if not re.search(r"[A-Z]", p): errs.append("At least one uppercase letter.")
    if not re.search(r"[a-z]", p): errs.append("At least one lowercase letter.")
    if not re.search(r"\d", p): errs.append("At least one number.")
    if not re.search(r"[\W_]", p): errs.append("At least one special character.")
    return (len(errs) == 0, errs)
