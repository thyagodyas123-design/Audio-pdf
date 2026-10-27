"""Login por cookie de sessão e CRUD de usuários (somente admin cria e gerencia contas)."""
import hashlib
import logging
import os
import re
import secrets
import threading
import time
import uuid
from pathlib import Path
from typing import Annotated, Literal

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select

from .. import db
from ..db.models import Book, User, UserSession

log = logging.getLogger("audiopdf.auth")
COOKIE = "audiopdf_session"
SESSION_TTL = 30 * 24 * 3600
PUBLIC_PATHS = {"/api/auth/login"}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_FAILS, FAIL_WINDOW = 5, 15 * 60

_hasher = PasswordHasher()
_DUMMY = _hasher.hash("senha-que-nunca-sera-usada")  # igualar o tempo quando o e-mail não existe
_fails: dict[str, list[float]] = {}
_fails_lock = threading.Lock()


def hash_password(pw: str) -> str:
    return _hasher.hash(pw)


def _check(pw: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, pw)
    except (VerificationError, InvalidHashError):
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def public(u: User) -> dict:
    return {"id": u.id, "email": u.email, "name": u.name, "role": u.role, "active": u.active,
            "created_at": u.created_at, "last_login": u.last_login}


def _norm_email(email: str) -> str:
    email = email.strip().lower()
    if not EMAIL_RE.match(email) or len(email) > 254:
        raise HTTPException(422, "e-mail inválido")
    return email


def _check_password(pw: str) -> str:
    if not 8 <= len(pw) <= 128:
        raise HTTPException(422, "a senha deve ter de 8 a 128 caracteres")
    return pw


# --- sessão --------------------------------------------------------------------------------------

def _user_from_request(request: Request) -> dict | None:
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    with db.session() as s:
        row = s.get(UserSession, _token_hash(token))
        if row is None:
            return None
        if row.expires_at < time.time():
            s.delete(row)
            return None
        u = s.get(User, row.user_id)
        return public(u) if u and u.active else None


def current_user(request: Request) -> dict:
    user = getattr(request.state, "user", None) or _user_from_request(request)
    if user is None:
        raise HTTPException(401, "faça login para continuar")
    request.state.user = user
    return user


CurrentUser = Annotated[dict, Depends(current_user)]


def admin_only(user: CurrentUser) -> dict:
    if user["role"] != "admin":
        raise HTTPException(403, "apenas administradores")
    return user


_booted = False
_boot_lock = threading.Lock()


def ensure_ready() -> None:
    """Migrations + primeiro admin, uma vez por processo (e de novo se o banco for reconfigurado)."""
    global _booted
    if _booted and db._ready:
        return
    with _boot_lock:
        try:
            db.init()
            bootstrap(Path(os.environ.get("AUDIOPDF_DATA", "data")).resolve() / "books")
        except Exception as e:  # noqa: BLE001
            log.exception("falha ao preparar o banco de dados")  # o motivo real fica no log; a resposta não vaza a URL/credenciais
            raise HTTPException(503, f"Banco de dados indisponível ({type(e).__name__}). Veja o log do servidor.") from e
        _booted = True


def guard(request: Request) -> None:
    """Dependência global: tudo em /api exige login; rotas com {book_id} exigem ser dono (admin vê todos)."""
    ensure_ready()
    if request.url.path in PUBLIC_PATHS:
        return
    user = current_user(request)
    book_id = request.path_params.get("book_id")
    if book_id and user["role"] != "admin":
        with db.session() as s:
            book = s.get(Book, book_id)
            if book is None or book.owner_id != user["id"]:
                raise HTTPException(404, "livro não encontrado")  # 404 para não revelar que o livro existe


# --- livros ---------------------------------------------------------------------------------------

def register_book(book_id: str, owner_id: str) -> None:
    with db.session() as s:
        s.merge(Book(id=book_id, owner_id=owner_id, created_at=time.time()))


def forget_book(book_id: str) -> None:
    with db.session() as s:
        s.execute(delete(Book).where(Book.id == book_id))


def visible_book_ids(user: dict) -> set[str] | None:
    """None = todos (admin)."""
    if user["role"] == "admin":
        return None
    with db.session() as s:
        return set(s.scalars(select(Book.id).where(Book.owner_id == user["id"])))


# --- primeiro admin ------------------------------------------------------------------------------

def bootstrap(books_dir: Path) -> None:
    """Cria o primeiro admin (ADMIN_EMAIL/ADMIN_PASSWORD) se não houver usuários e entrega ao admin os livros sem dono."""
    with db.session() as s:
        if s.scalar(select(func.count()).select_from(User)) == 0:
            email, pw = os.environ.get("ADMIN_EMAIL", ""), os.environ.get("ADMIN_PASSWORD", "")
            if not email or not pw:
                log.error("Nenhum usuário cadastrado: defina ADMIN_EMAIL e ADMIN_PASSWORD para criar o primeiro admin.")
                return
            s.add(User(id=uuid.uuid4().hex, email=_norm_email(email), name=os.environ.get("ADMIN_NAME", "Administrador"),
                       password_hash=hash_password(_check_password(pw)), role="admin", active=True, created_at=time.time()))
            s.flush()
            log.warning("Primeiro admin criado: %s", email)
        admin = s.scalars(select(User).where(User.role == "admin").order_by(User.created_at)).first()
        if admin is None or not books_dir.is_dir():
            return
        owned = set(s.scalars(select(Book.id)))
        for d in books_dir.iterdir():
            if d.is_dir() and (d / "meta.json").exists() and d.name not in owned:
                s.add(Book(id=d.name, owner_id=admin.id, created_at=time.time()))
                log.warning("Livro %s sem dono entregue a %s", d.name, admin.email)


# --- rotas ----------------------------------------------------------------------------------------

router = APIRouter()


class LoginIn(BaseModel):
    email: str
    password: str


def _secure_cookie() -> bool:
    return os.environ.get("PUBLIC_URL", "").startswith("https://")


def _throttle_key(request: Request, email: str) -> str:
    ip = request.client.host if request.client else "?"
    return f"{email.strip().lower()}|{ip}"


@router.post("/api/auth/login")
def login(body: LoginIn, request: Request, response: Response):
    key = _throttle_key(request, body.email)
    now = time.time()
    with _fails_lock:
        recent = [t for t in _fails.get(key, []) if t > now - FAIL_WINDOW]
        _fails[key] = recent
        if len(recent) >= MAX_FAILS:
            raise HTTPException(429, "muitas tentativas; aguarde alguns minutos")
    with db.session() as s:
        u = s.scalar(select(User).where(User.email == body.email.strip().lower()))
        ok = _check(body.password, u.password_hash if u else _DUMMY) and u is not None and u.active
        if not ok:
            with _fails_lock:
                _fails.setdefault(key, []).append(now)
            raise HTTPException(401, "e-mail ou senha incorretos")
        token = secrets.token_urlsafe(32)
        s.add(UserSession(token_hash=_token_hash(token), user_id=u.id, created_at=now, expires_at=now + SESSION_TTL))
        s.execute(delete(UserSession).where(UserSession.expires_at < now))  # limpeza oportunista
        u.last_login = now
        data = public(u)
    with _fails_lock:
        _fails.pop(key, None)
    response.set_cookie(COOKIE, token, max_age=SESSION_TTL, httponly=True, samesite="lax", secure=_secure_cookie(), path="/")
    return data


@router.post("/api/auth/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE)
    if token:
        with db.session() as s:
            s.execute(delete(UserSession).where(UserSession.token_hash == _token_hash(token)))
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/api/auth/me")
def me(user: CurrentUser):
    return user


class PasswordIn(BaseModel):
    current: str
    new: str


@router.post("/api/auth/password")
def change_password(body: PasswordIn, request: Request, user: CurrentUser):
    _check_password(body.new)
    with db.session() as s:
        u = s.get(User, user["id"])
        if not _check(body.current, u.password_hash):
            raise HTTPException(403, "senha atual incorreta")
        u.password_hash = hash_password(body.new)
        keep = _token_hash(request.cookies.get(COOKIE, ""))
        s.execute(delete(UserSession).where(UserSession.user_id == u.id, UserSession.token_hash != keep))  # derruba os outros dispositivos
    return {"ok": True}


class UserIn(BaseModel):
    email: str
    name: str = Field(min_length=1, max_length=120)
    password: str
    role: Literal["admin", "user"] = "user"


class UserPatch(BaseModel):
    email: str | None = None
    name: str | None = Field(default=None, min_length=1, max_length=120)
    password: str | None = None
    role: Literal["admin", "user"] | None = None
    active: bool | None = None


def _active_admins(s, excluding: str | None = None) -> int:
    q = select(func.count()).select_from(User).where(User.role == "admin", User.active.is_(True))
    if excluding:
        q = q.where(User.id != excluding)
    return s.scalar(q)


@router.get("/api/users")
def list_users(_: Annotated[dict, Depends(admin_only)]):
    with db.session() as s:
        books = dict(s.execute(select(Book.owner_id, func.count()).group_by(Book.owner_id)).all())
        return [{**public(u), "books": books.get(u.id, 0)} for u in s.scalars(select(User).order_by(User.created_at))]


@router.post("/api/users", status_code=201)
def create_user(body: UserIn, _: Annotated[dict, Depends(admin_only)]):
    email = _norm_email(body.email)
    with db.session() as s:
        if s.scalar(select(User.id).where(User.email == email)):
            raise HTTPException(409, "já existe um usuário com esse e-mail")
        u = User(id=uuid.uuid4().hex, email=email, name=body.name.strip(), password_hash=hash_password(_check_password(body.password)),
                 role=body.role, active=True, created_at=time.time())
        s.add(u)
        s.flush()
        return public(u)


def _get(s, user_id: str) -> User:
    u = s.get(User, user_id)
    if u is None:
        raise HTTPException(404, "usuário não encontrado")
    return u


@router.get("/api/users/{user_id}")
def get_user(user_id: str, _: Annotated[dict, Depends(admin_only)]):
    with db.session() as s:
        return public(_get(s, user_id))


@router.patch("/api/users/{user_id}")
def update_user(user_id: str, body: UserPatch, admin: Annotated[dict, Depends(admin_only)]):
    with db.session() as s:
        u = _get(s, user_id)
        loses_admin = (body.role == "user" and u.role == "admin") or (body.active is False and u.active and u.role == "admin")
        if loses_admin and _active_admins(s, excluding=u.id) == 0:
            raise HTTPException(409, "o sistema precisa de ao menos um administrador ativo")
        if body.email is not None:
            email = _norm_email(body.email)
            if email != u.email and s.scalar(select(User.id).where(User.email == email)):
                raise HTTPException(409, "já existe um usuário com esse e-mail")
            u.email = email
        if body.name is not None:
            u.name = body.name.strip()
        if body.role is not None:
            u.role = body.role
        revoke = False
        if body.active is not None:
            revoke = revoke or (not body.active)
            u.active = body.active
        if body.password is not None:
            u.password_hash = hash_password(_check_password(body.password))
            revoke = True
        if revoke:  # conta desativada ou senha trocada: derruba as sessões abertas
            s.execute(delete(UserSession).where(UserSession.user_id == u.id))
        return public(u)


@router.delete("/api/users/{user_id}")
def delete_user(user_id: str, admin: Annotated[dict, Depends(admin_only)]):
    """Remove a conta; os livros dela passam para quem excluiu."""
    if user_id == admin["id"]:
        raise HTTPException(409, "você não pode excluir a própria conta")
    with db.session() as s:
        u = _get(s, user_id)
        if u.role == "admin" and _active_admins(s, excluding=u.id) == 0:
            raise HTTPException(409, "o sistema precisa de ao menos um administrador ativo")
        for b in s.scalars(select(Book).where(Book.owner_id == u.id)):
            b.owner_id = admin["id"]
        s.execute(delete(UserSession).where(UserSession.user_id == u.id))
        s.delete(u)
    return {"ok": True}
