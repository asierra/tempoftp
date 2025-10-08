import string
import secrets
import random

class GestorFTPBase:
    """
    Clase base con la lógica común para generar credenciales.
    """
    def generate_username(self, email: str) -> str:
        """Genera un nombre de usuario único a partir de un email."""
        prefix = "ftp_"
        user_part = email.split("@")[0].replace(".", "_")
        random_word = ''.join(random.choices(string.ascii_lowercase, k=4))
        return f"{prefix}{user_part}_{random_word}"

    def generate_password(self, length: int = 12) -> str:
        """Genera una contraseña aleatoria y segura."""
        alphabet = string.ascii_letters + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(length))

    def _verificar_solicitud_duplicada(self, id: str):
        """Verifica si ya existe una solicitud y lanza una excepción si es así."""
        # Este método asume que `self.db` está disponible en la clase hija.
        solicitud_existente = self.db.obtener_solicitud(id)
        if solicitud_existente:
            mensaje = f"Ya existe una solicitud en proceso con el ID '{id}'. Estado actual: {solicitud_existente['estado']}"
            raise Exception(mensaje)

    def _reiniciar_db_para_test(self):
        """Método específico para pruebas para garantizar un estado limpio."""
        # Asume que la clase hija tiene un constructor que puede ser llamado de nuevo.
        self.__init__()

    async def get_status(self, id: str):
        """Obtiene el estado de una solicitud desde la base de datos."""
        solicitud = self.db.obtener_solicitud(id)
        if solicitud:
            if solicitud["estado"] == "listo":
                return {"status": "listo", **solicitud["info"]}
            else:
                return {"status": solicitud["estado"], "mensaje": solicitud["info"].get("mensaje", "")}
        return None