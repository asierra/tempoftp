"""
P0-2: cifrado.py debe abortar (RuntimeError) si TEMPOFTP_ENCRYPTION_KEY no está
configurada, en vez de generar una clave Fernet efímera. Antes, cada worker (o
cada reinicio) generaba una clave distinta, dejando contraseñas ya cifradas
indescifrables entre workers/reinicios.

El chequeo ocurre en la importación del módulo (efecto de import), así que se
verifica en un subproceso limpio: reimportar cifrado en el proceso de test no
sirve, porque ya está cacheado en sys.modules con una clave válida (puesta por
test_main.py antes de que arrancara la colección de tests).
"""
import os
import subprocess
import sys

from cryptography.fernet import Fernet

_TEMPOFTP_DIR = os.path.dirname(os.path.abspath(__file__))


def _run_import_cifrado(env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", "import cifrado; print('IMPORT_OK')"],
        cwd=_TEMPOFTP_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_import_falla_sin_encryption_key():
    env = {k: v for k, v in os.environ.items() if k != "TEMPOFTP_ENCRYPTION_KEY"}
    result = _run_import_cifrado(env)
    assert result.returncode != 0
    assert "TEMPOFTP_ENCRYPTION_KEY no está configurada" in result.stderr
    assert "IMPORT_OK" not in result.stdout


def test_import_ok_con_encryption_key():
    env = dict(os.environ)
    env["TEMPOFTP_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
    result = _run_import_cifrado(env)
    assert result.returncode == 0
    assert "IMPORT_OK" in result.stdout
