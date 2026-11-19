import os
from fastapi import Header, HTTPException


def current_user(x_user_id: str = Header(...), x_user_role: str = Header("user")):
    # пользователя проставляет шлюз перед сервисом
    return type("U", (), {"id": x_user_id, "role": x_user_role})


def require_admin(x_user_role: str = Header("user")):
    if x_user_role != "admin":
        raise HTTPException(403)


def db():
    from app.session import Session
    with Session() as s:
        yield s
