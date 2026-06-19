from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.config import DB_FILE
from app.database import connect, initialize_database
from app.exceptions import AppError, AuthenticationError, PermissionDeniedError

@dataclass(frozen=True)
class User:
    username: str
    display_name: str
    role: str
    role_name_value: str

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def role_name(self) -> str:
        return self.role_name_value

def authenticate(username: str, password: str, db_path: str | Path = DB_FILE) -> User:
    initialize_database(db_path)
    username = username.strip()
    with connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT u.username, u.password, u.display_name, u.role_code, u.active, r.name AS role_name
            FROM users u
            JOIN roles r ON r.code = u.role_code
            WHERE u.username = ?
            """,
            (username,),
        ).fetchone()
    if not row or row["password"] != password:
        raise AuthenticationError("账号或密码错误。")
    if not row["active"]:
        raise AuthenticationError("该账号已停用，请联系管理员。")
    return User(
        username=row["username"],
        display_name=row["display_name"],
        role=row["role_code"],
        role_name_value=row["role_name"],
    )

def has_permission(user: User, permission: str, db_path: str | Path = DB_FILE) -> bool:
    initialize_database(db_path)
    with connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM role_permissions
            WHERE role_code = ? AND permission_code = ?
            """,
            (user.role, permission),
        ).fetchone()
    return row is not None

def require_permission(user: User, permission: str, db_path: str | Path = DB_FILE) -> None:
    if not has_permission(user, permission, db_path):
        raise PermissionDeniedError(f"{user.role_name}无权执行该操作。")

def list_usernames(db_path: str | Path = DB_FILE, active_only: bool = True) -> list[str]:
    initialize_database(db_path)
    sql = "SELECT username FROM users"
    if active_only:
        sql += " WHERE active = 1"
    sql += " ORDER BY username"
    with connect(db_path) as conn:
        rows = conn.execute(sql).fetchall()
    return [row["username"] for row in rows]

def list_users(db_path: str | Path = DB_FILE) -> list[dict]:
    initialize_database(db_path)
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT u.username, u.display_name, u.role_code, r.name AS role_name, u.active
            FROM users u
            JOIN roles r ON r.code = u.role_code
            ORDER BY u.username
            """
        ).fetchall()
    return [dict(row) for row in rows]

def list_roles(db_path: str | Path = DB_FILE) -> list[dict]:
    initialize_database(db_path)
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT code, name, description, is_system
            FROM roles
            ORDER BY is_system DESC, code
            """
        ).fetchall()
    return [dict(row) for row in rows]

def list_permissions(db_path: str | Path = DB_FILE) -> list[dict]:
    initialize_database(db_path)
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT code, name, module, description
            FROM permissions
            ORDER BY module, code
            """
        ).fetchall()
    return [dict(row) for row in rows]

def permissions_for_role(role_code: str, db_path: str | Path = DB_FILE) -> set[str]:
    initialize_database(db_path)
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT permission_code
            FROM role_permissions
            WHERE role_code = ?
            """,
            (role_code,),
        ).fetchall()
    return {row["permission_code"] for row in rows}

def create_user(username: str, password: str, display_name: str, role_code: str, db_path: str | Path = DB_FILE) -> None:
    username = username.strip()
    display_name = display_name.strip()
    if not username or not password or not display_name:
        raise AppError("账号、密码和显示名称不能为空。")
    initialize_database(db_path)
    with connect(db_path) as conn:
        try:
            conn.execute(
                """
                INSERT INTO users(username, password, display_name, role_code, active)
                VALUES (?, ?, ?, ?, 1)
                """,
                (username, password, display_name, role_code),
            )
        except Exception as exc:
            raise AppError("用户创建失败，请检查账号是否重复、角色是否存在。") from exc

def reset_password(username: str, password: str, db_path: str | Path = DB_FILE) -> None:
    if not password:
        raise AppError("新密码不能为空。")
    initialize_database(db_path)
    with connect(db_path) as conn:
        conn.execute("UPDATE users SET password = ? WHERE username = ?", (password, username))

def update_user_role(username: str, role_code: str, db_path: str | Path = DB_FILE) -> None:
    initialize_database(db_path)
    _ensure_not_removing_last_admin(username, role_code=role_code, active=None, db_path=db_path)
    with connect(db_path) as conn:
        conn.execute("UPDATE users SET role_code = ? WHERE username = ?", (role_code, username))

def set_user_active(username: str, active: bool, db_path: str | Path = DB_FILE) -> None:
    initialize_database(db_path)
    _ensure_not_removing_last_admin(username, role_code=None, active=active, db_path=db_path)
    with connect(db_path) as conn:
        conn.execute("UPDATE users SET active = ? WHERE username = ?", (1 if active else 0, username))

def create_role(code: str, name: str, description: str = "", db_path: str | Path = DB_FILE) -> None:
    code = code.strip()
    name = name.strip()
    if not code or not name:
        raise AppError("角色编码和角色名称不能为空。")
    initialize_database(db_path)
    with connect(db_path) as conn:
        try:
            conn.execute(
                """
                INSERT INTO roles(code, name, description, is_system)
                VALUES (?, ?, ?, 0)
                """,
                (code, name, description.strip()),
            )
        except Exception as exc:
            raise AppError("角色创建失败，请检查角色编码是否重复。") from exc

def set_role_permission(role_code: str, permission_code: str, enabled: bool, db_path: str | Path = DB_FILE) -> None:
    initialize_database(db_path)
    with connect(db_path) as conn:
        if enabled:
            conn.execute(
                """
                INSERT OR IGNORE INTO role_permissions(role_code, permission_code)
                VALUES (?, ?)
                """,
                (role_code, permission_code),
            )
        else:
            if role_code == "admin" and permission_code in {"role_manage", "user_manage"}:
                raise AppError("不能移除管理员的用户管理或角色权限。")
            conn.execute(
                """
                DELETE FROM role_permissions
                WHERE role_code = ? AND permission_code = ?
                """,
                (role_code, permission_code),
            )

def _ensure_not_removing_last_admin(
    username: str,
    role_code: str | None,
    active: bool | None,
    db_path: str | Path,
) -> None:
    with connect(db_path) as conn:
        current = conn.execute("SELECT role_code, active FROM users WHERE username = ?", (username,)).fetchone()
        if current is None:
            raise AppError("用户不存在。")
        would_remove_admin = current["role_code"] == "admin" and (
            (role_code is not None and role_code != "admin") or (active is not None and not active)
        )
        if not would_remove_admin:
            return
        active_admin_count = conn.execute(
            "SELECT COUNT(*) FROM users WHERE role_code = 'admin' AND active = 1"
        ).fetchone()[0]
        if active_admin_count <= 1:
            raise AppError("至少需要保留一个启用状态的管理员账号。")