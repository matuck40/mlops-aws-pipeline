import shutil
import subprocess

import pytest

# Pacotes que a camada AWSSDKPandas já traz (e suas dependências diretas).
NA_CAMADA = [
    "pandas", "pyarrow", "numpy", "requests", "boto3", "botocore", "s3transfer",
    "jmespath", "python-dateutil", "six", "urllib3", "certifi", "charset-normalizer",
]  # fmt: skip


def test_requirements_em_dia(tmp_path, pytestconfig):
    if shutil.which("uv") is None:
        pytest.skip("uv não está no PATH")
    saida = tmp_path / "requirements.txt"
    comando = ["uv", "export", "--no-dev", "--no-hashes", "--no-emit-project", "--frozen", "--no-header"]
    for pacote in NA_CAMADA:
        comando += ["--no-emit-package", pacote]
    comando += ["-o", str(saida)]
    subprocess.run(comando, check=True, cwd=pytestconfig.rootpath, capture_output=True)

    atual = (pytestconfig.rootpath / "src" / "requirements.txt").read_text()
    assert saida.read_text() == atual, "src/requirements.txt desatualizado; veja o README"
