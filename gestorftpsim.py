import os
import random
import string
import subprocess
import hashlib
import time
import sqlite3

class GestorFTP:
    def __init__(self, gestorftpdb):
        self.db = gestorftpdb
        self.requests = {}

    # Elimina la gestión directa de la base de datos, usa gestorftpdb

    def generate_username(self, email):        
        prefix = "ftp_"
        user_part = email.split("@")[0]
        random_word = ''.join(random.choices(string.ascii_lowercase, k=4))
        return f"{prefix}{user_part}_{random_word}"

    def generate_password(self):
        # Genera una contraseña aleatoria
        return ''.join(random.choices(string.ascii_letters + string.digits, k=12))

    def create_usertmp(self, id, email, ruta, vigencia):
        username = self.generate_username(email)
        password = self.generate_password()
        password_hash = hashlib.sha512(password.encode()).hexdigest()
        info = {
            "usuario": username,
            "password": password,
            "password_hash": password_hash,
            "ruta": ruta,
            "vigencia": vigencia
        }
        self.db.crear_solicitud(id, email, ruta, "recibido", info)
        # Simulación de proceso
        self.db.actualizar_estado(id, "preparando", info)
        print(f"SIMULACRO: Verificando espacio para copiar desde {ruta}")
        espacio_suficiente = random.choice([True, True, False])
        if not espacio_suficiente:
            error_msg = "Espacio insuficiente"
            self.db.actualizar_estado(id, "error", {**info, "mensaje": error_msg})
            raise Exception(error_msg)
        self.db.actualizar_estado(id, "traslado", {**info, "mensaje": f"Copiando datos desde {ruta} a destino."})
        print(f"SIMULACRO: Ejecutando rsync -av {ruta} destino")
        time.sleep(2)
        print("SIMULACRO: Copia finalizada.")
        mensaje_listo = f"Listo, tiene {vigencia} días para hacer la descarga. Usuario: {username}, Contraseña: {password}"
        self.db.actualizar_estado(id, "listo para descarga", {**info, "mensaje": mensaje_listo})
        print(f"SIMULACRO: Programando cron para eliminar al usuario {username} y la carpeta en {vigencia} días.")
        # Simulación de cron
        return
    def get_status(self, id):
        solicitud = self.db.obtener_solicitud(id)
        if solicitud:
            return {"status": solicitud["estado"], "mensaje": solicitud["info"].get("mensaje", "")}
        else:
            return None