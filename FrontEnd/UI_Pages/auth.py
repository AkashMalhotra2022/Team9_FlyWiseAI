from .utils import load_users, save_users, hash_password, validate_email, validate_password

def verify_login(username: str, password: str) -> bool:
    users = load_users()
    u = (username or "").strip()
    return u in users and users[u].get("password") == hash_password(password)

def reset_password(username: str, email: str, new_password: str) -> bool:
    users = load_users()
    u = (username or "").strip()
    e = (email or "").strip().lower()
    if u in users and (users[u].get("email") or "").lower() == e:
        users[u]["password"] = hash_password(new_password)
        save_users(users)
        return True
    return False

def is_username_taken(username: str) -> bool:
    return (username or "").strip() in load_users()

def is_email_taken(email: str) -> bool:
    e = (email or "").strip().lower()
    for data in load_users().values():
        if (data.get("email") or "").lower() == e:
            return True
    return False

def register_user(username: str, email: str, password: str):
    """Returns (ok, msg)"""
    u = (username or "").strip()
    e = (email or "").strip()
    if not u or not e or not password:
        return False, "Please fill all fields."
    if not validate_email(e):
        return False, "Please enter a valid email address."
    ok, errs = validate_password(password)
    if not ok:
        return False, "Weak password: " + " ".join(errs)
    if is_username_taken(u):
        return False, "That username is already taken."
    if is_email_taken(e):
        return False, "That email is already registered."

    users = load_users()
    users[u] = {"password": hash_password(password), "email": e}
    save_users(users)
    return True, "Account created successfully."
