import pytest
from fastapi.testclient import TestClient

ADMIN = {"email": "admin@teste.com", "password": "senha-do-admin-1"}


@pytest.fixture(scope="module")
def web():
    from audiopdf.web import app as web
    return web


def new_client(web) -> TestClient:
    return TestClient(web.app)


def login(c: TestClient, email: str, password: str):
    return c.post("/api/auth/login", json={"email": email, "password": password})


@pytest.fixture
def admin(web):
    c = new_client(web)
    assert login(c, **ADMIN).status_code == 200
    return c


def make_user(admin, email, role="user", password="senha-forte-123", name="Pessoa"):
    r = admin.post("/api/users", json={"email": email, "name": name, "password": password, "role": role})
    assert r.status_code == 201, r.text
    return r.json()


def test_api_exige_login(web):
    c = new_client(web)
    for path in ("/api/books", "/api/voices", "/api/users", "/api/auth/me"):
        assert c.get(path).status_code == 401, path
    assert c.get("/").status_code == 200  # a página estática continua pública (a tela de login mora nela)


def test_login_logout_me(web):
    c = new_client(web)
    assert login(c, ADMIN["email"], "errada").status_code == 401
    r = login(c, ADMIN["email"].upper(), ADMIN["password"])  # e-mail sem diferenciar maiúsculas
    assert r.status_code == 200 and r.json()["role"] == "admin" and "password" not in r.text
    assert "httponly" in r.headers["set-cookie"].lower()
    assert c.get("/api/auth/me").json()["email"] == ADMIN["email"]
    assert c.post("/api/auth/logout").status_code == 200
    assert c.get("/api/auth/me").status_code == 401


def test_crud_usuario(web, admin):
    u = make_user(admin, "ana@teste.com", name="Ana")
    assert admin.post("/api/users", json={"email": "ANA@teste.com", "name": "x", "password": "senha-forte-123"}).status_code == 409
    assert admin.post("/api/users", json={"email": "invalido", "name": "x", "password": "senha-forte-123"}).status_code == 422
    assert admin.post("/api/users", json={"email": "b@teste.com", "name": "x", "password": "curta"}).status_code == 422
    assert admin.get(f"/api/users/{u['id']}").json()["name"] == "Ana"
    assert any(x["email"] == "ana@teste.com" for x in admin.get("/api/users").json())
    r = admin.patch(f"/api/users/{u['id']}", json={"name": "Ana Souza", "role": "admin"})
    assert r.json()["name"] == "Ana Souza" and r.json()["role"] == "admin"
    assert admin.delete(f"/api/users/{u['id']}").status_code == 200
    assert admin.get(f"/api/users/{u['id']}").status_code == 404


def test_usuario_comum_nao_gerencia_usuarios(web, admin):
    make_user(admin, "comum@teste.com")
    c = new_client(web)
    assert login(c, "comum@teste.com", "senha-forte-123").status_code == 200
    assert c.get("/api/users").status_code == 403
    assert c.post("/api/users", json={"email": "x@teste.com", "name": "x", "password": "senha-forte-123"}).status_code == 403


def test_desativar_derruba_sessao_e_bloqueia_login(web, admin):
    u = make_user(admin, "inativo@teste.com")
    c = new_client(web)
    assert login(c, "inativo@teste.com", "senha-forte-123").status_code == 200
    admin.patch(f"/api/users/{u['id']}", json={"active": False})
    assert c.get("/api/auth/me").status_code == 401
    assert login(c, "inativo@teste.com", "senha-forte-123").status_code == 401
    admin.patch(f"/api/users/{u['id']}", json={"active": True})
    assert login(c, "inativo@teste.com", "senha-forte-123").status_code == 200


def test_ultimo_admin_protegido(web, admin):
    me = admin.get("/api/auth/me").json()
    assert admin.delete(f"/api/users/{me['id']}").status_code == 409  # não exclui a si mesmo
    assert admin.patch(f"/api/users/{me['id']}", json={"role": "user"}).status_code == 409
    assert admin.patch(f"/api/users/{me['id']}", json={"active": False}).status_code == 409


def test_trocar_senha(web, admin):
    make_user(admin, "troca@teste.com")
    c, outro = new_client(web), new_client(web)
    login(c, "troca@teste.com", "senha-forte-123")
    login(outro, "troca@teste.com", "senha-forte-123")
    assert c.post("/api/auth/password", json={"current": "errada", "new": "nova-senha-456"}).status_code == 403
    assert c.post("/api/auth/password", json={"current": "senha-forte-123", "new": "curta"}).status_code == 422
    assert c.post("/api/auth/password", json={"current": "senha-forte-123", "new": "nova-senha-456"}).status_code == 200
    assert c.get("/api/auth/me").status_code == 200  # a sessão atual continua
    assert outro.get("/api/auth/me").status_code == 401  # as demais caem
    assert login(new_client(web), "troca@teste.com", "nova-senha-456").status_code == 200


def test_limite_de_tentativas(web):
    c = new_client(web)
    for _ in range(5):
        assert login(c, "ninguem@teste.com", "x").status_code == 401
    assert login(c, "ninguem@teste.com", "x").status_code == 429


def test_livro_pertence_a_um_usuario(web, admin):
    import json

    d = web.DATA / "books" / ("a" * 32)
    d.mkdir(parents=True, exist_ok=True)
    (d / "meta.json").write_text(json.dumps({"id": "a" * 32, "title": "X", "pages": 1, "created": 1, "chapters": [], "language": "pt"}))
    (d / "chapters.json").write_text("[]")
    from audiopdf.web import auth
    u = make_user(admin, "dono@teste.com")
    auth.register_book("a" * 32, u["id"])
    dono, outro = new_client(web), new_client(web)
    login(dono, "dono@teste.com", "senha-forte-123")
    make_user(admin, "intruso@teste.com")
    login(outro, "intruso@teste.com", "senha-forte-123")
    assert [b["id"] for b in dono.get("/api/books").json()] == ["a" * 32]
    assert outro.get("/api/books").json() == []
    assert dono.get(f"/api/books/{'a' * 32}").status_code == 200
    assert outro.get(f"/api/books/{'a' * 32}").status_code == 404  # nem confirma que existe
    assert outro.delete(f"/api/books/{'a' * 32}").status_code == 404
    assert any(b["id"] == "a" * 32 for b in admin.get("/api/books").json())  # admin vê tudo
    assert admin.delete(f"/api/users/{u['id']}").status_code == 200  # livros passam para quem excluiu
    assert admin.get(f"/api/books/{'a' * 32}").status_code == 200
    assert admin.delete(f"/api/books/{'a' * 32}").status_code == 200


def test_migration_sobe_e_desce(tmp_path):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect

    from audiopdf import db

    eng = db.configure(f"sqlite:///{tmp_path / 'm.db'}")
    db.migrate()
    assert {"users", "sessions", "books"} <= set(inspect(eng).get_table_names())
    cfg = Config()
    cfg.set_main_option("script_location", str(__import__("pathlib").Path(db.__file__).parent / "migrations"))
    cfg.attributes["engine"] = eng
    command.downgrade(cfg, "base")
    assert "users" not in inspect(eng).get_table_names()
    db.configure()  # volta ao banco dos testes


def test_banco_fora_do_ar_responde_503_claro(web, monkeypatch):
    from audiopdf import db
    from audiopdf.web import auth

    def boom():
        raise RuntimeError("senha=segredo")
    monkeypatch.setattr(db, "init", boom)
    monkeypatch.setattr(auth, "_booted", False)
    r = new_client(web).get("/api/books")
    assert r.status_code == 503 and "RuntimeError" in r.json()["detail"] and "segredo" not in r.text


def test_503_explica_senha_do_postgres(web, monkeypatch):
    from audiopdf import db
    from audiopdf.web import auth

    def boom():
        raise RuntimeError('FATAL:  password authentication failed for user "audiopdf" host=db pw=segredo')
    monkeypatch.setattr(db, "init", boom)
    monkeypatch.setattr(auth, "_booted", False)
    r = new_client(web).get("/api/books")
    assert "senha do Postgres" in r.json()["detail"] and "segredo" not in r.text and "audiopdf" not in r.text


def test_audiopdf_db_sqlite_ignora_database_url(monkeypatch):
    from audiopdf import db

    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://x:y@db:5432/z")
    assert db.default_url().startswith("postgresql")
    monkeypatch.setenv("AUDIOPDF_DB", "sqlite")
    assert db.default_url().startswith("sqlite:///") and db.default_url().endswith("audiopdf.db")
