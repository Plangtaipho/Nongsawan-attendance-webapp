"""Create an admin account from the command line (for a machine where you have a shell).

Usage:  python -m scripts.create_admin <username> "<full name>"
The password is asked for interactively so it never lands in shell history.
"""
import getpass
import sys

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Role, User
from app.security import MAX_PASSWORD_BYTES, hash_password


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit('Usage: python -m scripts.create_admin <username> "<full name>"')
    username, full_name = sys.argv[1], sys.argv[2]
    password = getpass.getpass("Password (8+ characters): ")
    if len(password) < 8 or len(password.encode()) > MAX_PASSWORD_BYTES:
        sys.exit("Password must be 8-72 bytes long.")
    if password != getpass.getpass("Repeat password: "):
        sys.exit("Passwords do not match.")
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.username == username)):
            sys.exit(f"User {username} already exists.")
        db.add(User(username=username, full_name=full_name, role=Role.admin, password_hash=hash_password(password)))
        db.commit()
    print(f"Admin {username} created.")


if __name__ == "__main__":
    main()
