import os
from cryptography.fernet import Fernet

# Carga la clave desde una variable de entorno.
# Es CRÍTICO que esta clave sea la misma en el servidor y en el cliente.
ENCRYPTION_KEY = os.getenv("TEMPOFTP_ENCRYPTION_KEY")

if not ENCRYPTION_KEY:
    # En un entorno real, esto debería detener la aplicación.
    # Para desarrollo, podemos generar una si no existe.
    print("ADVERTENCIA: TEMPOFTP_ENCRYPTION_KEY no está configurada. Usando una clave generada automáticamente.")
    ENCRYPTION_KEY = Fernet.generate_key().decode()

cipher_suite = Fernet(ENCRYPTION_KEY.encode())

def cifrar(texto: str) -> str:
    """Cifra un texto y lo devuelve como una cadena."""
    texto_cifrado_bytes = cipher_suite.encrypt(texto.encode())
    return texto_cifrado_bytes.decode()

def descifrar(texto_cifrado: str) -> str:
    """Descifra un texto y lo devuelve como una cadena."""
    texto_descifrado_bytes = cipher_suite.decrypt(texto_cifrado.encode())
    return texto_descifrado_bytes.decode()