import os
import tempfile

# antes de importar o app: dados isolados e sem aquecer o modelo real
os.environ["AUDIOPDF_DATA"] = tempfile.mkdtemp(prefix="audiopdf-test-")
os.environ["AUDIOPDF_NO_WARMUP"] = "1"
