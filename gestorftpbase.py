import string
import secrets
import random

class GestorFTPBase:
    """
    Clase base con la lógica común para generar credenciales.
    """
    def generate_username(self, email: str) -> str:
        """Genera un nombre de usuario determinista a partir de un email.
        Regla: ftp_<parte_izq_de_@>_<primer_label_del_dominio>
        Ej: danae@zaln.unam.mx -> ftp_danae_zaln
        """
        prefix = "ftp_"
        try:
            local, domain = email.split("@", 1)
        except ValueError:
            local, domain = email, ""

        local = (local or "").strip().lower()
        first_label = (domain or "").split(".", 1)[0].strip().lower() if domain else ""

        # Normaliza a [a-z0-9_], sustituyendo separadores comunes por '_'
        import re
        def norm(s: str) -> str:
            s = s.replace(".", "_").replace("-", "_").replace("+", "_")
            s = re.sub(r"[^a-z0-9_]", "_", s)
            s = re.sub(r"_+", "_", s).strip("_")
            return s or "x"

        user_part = norm(local)
        domain_part = norm(first_label) if first_label else "x"

        return f"{prefix}{user_part}_{domain_part}"

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
            estado = solicitud["estado"]
            info = solicitud["info"]
            # Si el estado es 'listo' extrae ftpuser y password
            if estado == "listo":
                return {
                    "status": "listo",
                    "ftpuser": info.get("usuario"),
                    "password": info.get("password"),
                    "vigencia": info.get("vigencia"),
                    "mensaje": info.get("mensaje", "")
                }
            else:
                return {
                    "status": estado,
                    "mensaje": info.get("mensaje", "")
                }
        return None