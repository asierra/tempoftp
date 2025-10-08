import os
import random
import string
import subprocess
import hashlib
import time

class GestorFTP:
    def __init__(self):
        self.requests = {}

    def generate_username(self, email):
        prefix = "ftp_"
        user_part = email.split("@")[0]
        random_word = ''.join(random.choices(string.ascii_lowercase, k=4))
        return f"{prefix}{user_part}_{random_word}"

    def generate_password(self):
        # Genera una contraseña aleatoria
        return ''.join(random.choices(string.ascii_letters + string.digits, k=12))

    def create_usertmp(self, id, email, ruta, vigencia):
        # 1. Generar credenciales y establecer estado inicial
        username = self.generate_username(email)
        password = self.generate_password()
        # El hash SHA512 es compatible con pure-ftpd si se configura correctamente
        password_hash = hashlib.sha512(password.encode()).hexdigest()

        self.requests[id] = {"status": "recibido", "mensaje": "Solicitud en cola."}

        # --- INICIO DE LA SIMULACIÓN DE PROCESO EN SEGUNDO PLANO ---
        
        # 2. Crear carpeta y verificar espacio
        self.requests[id].update({"status": "preparando", "mensaje": "Creando entorno y verificando espacio."})
        base_dir = f"/data/{id}"
        print(f"SIMULACRO: Creando directorio {base_dir}")
        # Lógica real: os.makedirs(base_dir, exist_ok=True)
        # Lógica real: subprocess.run(["chown", "pureftpd:pureftpd", base_dir])

        # 3. Simular la comprobación de espacio y la copia con rsync
        print(f"SIMULACRO: Verificando espacio para copiar desde {ruta}")
        # Lógica real: usar `rsync --dry-run -n` o `ssh user@host 'du -sh /path'` para obtener tamaño
        espacio_suficiente = random.choice([True, True, False]) # Simula que a veces no hay espacio
        if not espacio_suficiente:
            error_msg = "Espacio insuficiente"
            self.requests[id].update({"status": "error", "mensaje": error_msg})
            # En la implementación real, lanzaríamos una excepción aquí
            raise Exception(error_msg)

        self.requests[id].update({"status": "traslado", "mensaje": f"Copiando datos desde {ruta} a {base_dir}."})
        print(f"SIMULACRO: Ejecutando rsync -av {ruta} {base_dir}")
        time.sleep(2) # Simula el tiempo de copia
        print("SIMULACRO: Copia finalizada.")

        # 4. Crear usuario en la BD y actualizar estado a "listo"
        print(f"SIMULACRO: Creando usuario {username} en la base de datos MySQL de pure-ftpd.")
        # Lógica real: Conectar a MySQL y ejecutar:
        # INSERT INTO users (User, Password, Uid, Gid, Dir, ...) VALUES (%s, %s, ...);
        
        mensaje_listo = f"Listo, tiene {vigencia} días para hacer la descarga. Usuario: {username}, Contraseña: {password}"
        self.requests[id].update({"status": "listo para descarga", "mensaje": mensaje_listo})
        
        # 5. Programar la eliminación con cron
        print(f"SIMULACRO: Programando cron para eliminar al usuario {username} y la carpeta {base_dir} en {vigencia} días.")
        # Lógica real: usar una librería como `python-crontab`
        # from crontab import CronTab
        # cron = CronTab(user='root')
        # job = cron.new(command=f'/usr/bin/python3 /path/to/cleanup_script.py --id {id}')
        # job.setall(datetime.now() + timedelta(days=vigencia))
        # cron.write()

    def get_status(self, id):
        # Consulta el estado de la solicitud desde nuestro almacén en memoria
        return self.requests.get(id)