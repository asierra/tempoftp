import os
import random
import string
import subprocess
import hashlib

class GestorFTP:
    def generate_username(self, email):
        prefix = "ftp_"
        user_part = email.split("@")[0]
        random_word = ''.join(random.choices(string.ascii_lowercase, k=4))
        return f"{prefix}{user_part}_{random_word}"

    def generate_password_hash(self, password):
        return hashlib.sha512(password.encode()).hexdigest()

    def create_usertmp(self, id, email, ruta, vigencia):
        username = self.generate_username(email)
        password = ''.join(random.choices(string.ascii_letters + string.digits, k=12))
        password_hash = self.generate_password_hash(password)

        status = "preparando"
        base_dir = f"/data/{id}"
        try:
            os.makedirs(base_dir, exist_ok=True)
            # Establecer permisos para pure-ftpd (requiere integración con sistema)
            # subprocess.run(["chown", "pureftpd:pureftpd", base_dir])

            # Confirmar espacio usando 'rsync --dry-run' u otro método
            # Aquí simulado: espacio_suficiente = True
            espacio_suficiente = True
            if not espacio_suficiente:
                return {"id": id, "status": "error", "mensaje": "Espacio insuficiente"}
            
            # Copiar datos con rsync
            # subprocess.run(["rsync", "-av", ruta, base_dir])
            status = "traslado"

            # Crear usuario FTP en MySQL (usar aiomysql en producción)
            # Simulado aquí
            status = "ready"
            mensaje = f"Listo, tiene {vigencia} días para hacer la descarga."
            
            # Programar crontab para eliminar usuario y carpeta tras la vigencia (simulado)
            return {"id": id, "status": status, "mensaje": mensaje, "username": username, "password": password}
        except Exception as e:
            return {"id": id, "status": "error", "mensaje": str(e)}

    def get_status(self, id):
        # Consultar estado en la base SQLite (simulado)
        # Retornar estado de ejemplo
        return {"id": id, "status": "preparando", "mensaje": "En proceso"}
