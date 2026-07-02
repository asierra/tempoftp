import os
from cryptography.fernet import Fernet

# Carga la clave desde una variable de entorno.
# Es CRÍTICO que esta clave sea la misma en el servidor y en cualquier cliente
# (p.ej. historic_query) que necesite descifrar contraseñas FTP. Por eso, si
# falta, abortamos en vez de generar una clave efímera: con más de un worker
# (ver P0-1) cada proceso generaría una clave distinta —una contraseña cifrada
# por un worker quedaría indescifrable para otro— y entre reinicios la clave
# cambiaría, dejando indescifrables para siempre todas las contraseñas ya
# cifradas y persistidas en SQLite.
ENCRYPTION_KEY = os.getenv("TEMPOFTP_ENCRYPTION_KEY")

if not ENCRYPTION_KEY:
    raise RuntimeError(
        "TEMPOFTP_ENCRYPTION_KEY no está configurada. Es obligatoria y debe ser "
        "la misma en el servidor y en cualquier cliente que descifre contraseñas "
        "FTP. Generar una con: "
        "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
    )

cipher_suite = Fernet(ENCRYPTION_KEY.encode())

def cifrar(texto: str) -> str:
    """Cifra un texto y lo devuelve como una cadena."""
    texto_cifrado_bytes = cipher_suite.encrypt(texto.encode())
    return texto_cifrado_bytes.decode()

def descifrar(texto_cifrado: str) -> str:
    """Descifra un texto y lo devuelve como una cadena."""
    texto_descifrado_bytes = cipher_suite.decrypt(texto_cifrado.encode())
    return texto_descifrado_bytes.decode()