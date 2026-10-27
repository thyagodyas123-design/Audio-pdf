import os
import tempfile

# antes de importar o app: dados isolados e sem aquecer o modelo real
os.environ["AUDIOPDF_DATA"] = tempfile.mkdtemp(prefix="audiopdf-test-")
os.environ["AUDIOPDF_NO_WARMUP"] = "1"
os.environ["ADMIN_EMAIL"] = "admin@teste.com"
os.environ["ADMIN_PASSWORD"] = "senha-do-admin-1"
os.environ.pop("DATABASE_URL", None)  # SQLite dentro do diretório de dados de teste
