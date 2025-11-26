# Guía de Despliegue en Producción - TempoFTP

Este documento describe los pasos para desplegar la aplicación `TempoFTP` y sus dependencias en un servidor de producción. La guía está orientada a un sistema **Rocky Linux** (o derivados de RHEL como CentOS/AlmaLinux).

## Arquitectura

El sistema consta de tres componentes principales:
1.  **API TempoFTP**: Una aplicación FastAPI que gestiona las solicitudes, la lógica de negocio y la comunicación con la base de datos.
2.  **Servidor Pure-FTPd**: El servidor FTP que gestiona las conexiones de los usuarios. Se configura para autenticar contra una base de datos MySQL/MariaDB.
3.  **Base de Datos MariaDB/MySQL**: Almacena las credenciales y metadatos de los usuarios FTP.

---

## 1. Prerrequisitos del Servidor

Asegúrate de que el sistema esté actualizado e instala los paquetes necesarios.

```bash
# Actualizar el sistema
sudo dnf update -y

# Instalar repositorios EPEL (necesario para pure-ftpd)
sudo dnf install epel-release -y

# Instalar software requerido
sudo dnf install -y python3.11 python3.11-devel python3.11-pip mariadb-server pure-ftpd rsync git
```

---

## 2. Configuración de la Base de Datos (MariaDB)

1.  **Iniciar y habilitar MariaDB:**

    ```bash
    sudo systemctl enable --now mariadb
    ```

2.  **Asegurar la instalación:**
    Ejecuta el script de seguridad para establecer la contraseña de root y eliminar configuraciones inseguras.

    ```bash
    sudo mysql_secure_installation
    ```

3.  **Crear la base de datos y el usuario FTP:**
    Conéctate a MariaDB como root y ejecuta los siguientes comandos SQL. Reemplaza `tu_contraseña_segura_para_ftpuser` con una contraseña robusta.

    ```sql
    -- Conéctate con: sudo mysql -u root -p

    CREATE DATABASE ftpdb;

    CREATE USER 'ftpuser'@'localhost' IDENTIFIED BY 'tu_contraseña_segura_para_ftpuser';

    GRANT SELECT, INSERT ON ftpdb.* TO 'ftpuser'@'localhost';

    FLUSH PRIVILEGES;

    USE ftpdb;

    CREATE TABLE users (
      User VARCHAR(64) NOT NULL PRIMARY KEY,
      Password VARCHAR(255) NOT NULL,
      Uid INT NOT NULL,
      Gid INT NOT NULL,
      Dir VARCHAR(255) NOT NULL,
      Status ENUM('0', '1') NOT NULL DEFAULT '1',
      QuotaFiles INT DEFAULT 500,
      QuotaSize INT DEFAULT 100,
      ULBandwidth INT DEFAULT 100,
      DLBandwidth INT DEFAULT 100,
      Ipaddress VARCHAR(15) DEFAULT '*',
      Comment TEXT,
      LastModified TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    );

    -- Crear un índice en la columna User para optimizar búsquedas
    CREATE INDEX idx_user ON users (User);

    QUIT;
    ```

---

## 3. Configuración del Servidor Pure-FTPd

1.  **Crear directorios de configuración y certificados:**

    ```bash
    sudo mkdir -p /etc/pure-ftpd/
    sudo mkdir -p /etc/ssl/private/pure-ftpd
    ```

2.  **Generar un certificado TLS autofirmado:**
    Para producción, se recomienda usar un certificado emitido por una CA (ej. Let's Encrypt).

    ```bash
    sudo openssl req -x509 -nodes -days 730 -newkey rsa:2048 \
      -keyout /etc/ssl/private/pure-ftpd/pure-ftpd.pem \
      -out /etc/ssl/private/pure-ftpd/pure-ftpd.pem \
      -subj "/CN=ftp.tudominio.com"
    
    # Asegurar permisos
    sudo chmod 600 /etc/ssl/private/pure-ftpd/pure-ftpd.pem
    ```

3.  **Configurar Pure-FTPd:**
    Copia los archivos `pure-ftpd.conf.small` y `pureftpd-mysql.conf` del repositorio al servidor.

    *   **`/etc/pure-ftpd/pure-ftpd.conf`**: Usa el contenido de `pure-ftpd.conf.small` que ya validamos.

    *   **`/etc/pure-ftpd/pureftpd-mysql.conf`**: **¡IMPORTANTE!** No guardes la contraseña de la base de datos directamente aquí.

        a.  Crea un archivo de credenciales separado y seguro:
            ```bash
            sudo touch /etc/pure-ftpd/mysql-credentials.conf
            sudo sh -c "echo 'MYSQLPassword   tu_contraseña_segura_para_ftpuser' > /etc/pure-ftpd/mysql-credentials.conf"
            sudo chown root:root /etc/pure-ftpd/mysql-credentials.conf
            sudo chmod 600 /etc/pure-ftpd/mysql-credentials.conf
            ```

        b.  Tu archivo `/etc/pure-ftpd/pureftpd-mysql.conf` debe lucir así (sin la línea `MYSQLPassword`):
            ```ini
            MYSQLSocket     /var/lib/mysql/mysql.sock
            MYSQLUser       ftpuser
            MYSQLDatabase   ftpdb
            MYSQLCrypt      crypt
            MYSQLGetPW      SELECT Password FROM users WHERE User="\\L" AND status="1"
            MYSQLGetUID     SELECT Uid FROM users WHERE User="\\L" AND status="1"
            MYSQLGetGID     SELECT Gid FROM users WHERE User="\\L" AND status="1"
            MYSQLGetDir     SELECT Dir FROM users WHERE User="\\L" AND status="1"
            
            # Incluir el archivo de credenciales al final
            Include         /etc/pure-ftpd/mysql-credentials.conf
            ```

4.  **Configurar Firewall (`firewalld`):**

    ```bash
    sudo firewall-cmd --add-service=ftp --permanent
    sudo firewall-cmd --add-port=30000-30009/tcp --permanent
    sudo firewall-cmd --reload
    ```

5.  **Configurar SELinux:**
    Permite que FTPd acceda a los directorios home y a la red.

    ```bash
    sudo setsebool -P ftpd_full_access on
    ```

6.  **Iniciar y habilitar Pure-FTPd:**

    ```bash
    sudo systemctl enable --now pure-ftpd
    ```

---

## 4. Despliegue de la API TempoFTP

1.  **Clonar el repositorio y crear directorios:**

    ```bash
    sudo mkdir -p /opt/tempoftp
    sudo chown $USER:$USER /opt/tempoftp
    git clone <URL_DEL_REPOSITORIO> /opt/tempoftp
    cd /opt/tempoftp
    
    # Crear el directorio de datos para los usuarios FTP
    sudo mkdir /data
    # El propietario debe ser el usuario que ejecuta rsync/chown en el script
    sudo chown lanotadm:lanotadm /data 
    ```

2.  **Crear entorno virtual e instalar dependencias:**

    ```bash
    python3.11 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt 
    # Asumiendo que tienes un requirements.txt con fastapi, uvicorn, aiomysql, passlib, cryptography, etc.
    ```

3.  **Configurar Variables de Entorno:**
    Antes de crear el archivo `.env`, es crucial generar una clave de cifrado segura. Esta clave es utilizada por la API para proteger las contraseñas de los usuarios.

    a.  **Generar la clave:**
        Ejecuta el siguiente comando en tu terminal (con el entorno virtual activado):
        ```bash
        python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
        ```

    b.  **Crear el archivo `.env`:**
        Crea el archivo `/opt/tempoftp/.env` y pega la clave generada. **Este archivo debe ser protegido y no debe subirse al repositorio.**

    ```ini
    # /opt/tempoftp/.env

    # --- Configuración General ---
    TEMPOFTP_LOG_LEVEL=INFO

    # --- Clave de Cifrado (¡CRÍTICO!) ---
    TEMPOFTP_ENCRYPTION_KEY="tu_clave_de_cifrado_generada"

    # --- Conexión a DB de Pure-FTPd ---
    FTP_DB_HOST=localhost
    FTP_DB_PORT=3306
    FTP_DB_USER=ftpuser
    FTP_DB_PASS="tu_contraseña_segura_para_ftpuser"
    FTP_DB_NAME=ftpdb

    # --- Configuración de Usuario FTP ---
    FTP_PASSWORD_FORMAT=crypt
    FTP_CRYPT_SCHEME=sha512_crypt # Debe coincidir con lo que soporta Pure-FTPd
    FTP_UID=2001
    FTP_GID=2001

    # --- Configuración de Transferencia de Datos ---
    RSYNC_SSH_USER=lanotadm
    DATA_OWNER_USER=lanotadm
    DATA_OWNER_GROUP=lanotadm
    # SKIP_CHOWN=0 # Poner en 1 si el usuario que corre la API no tiene permisos de chown
    ```

4.  **Crear Servicio `systemd` para la API:**
    Crea el archivo `/etc/systemd/system/tempoftp.service`.

    ```ini
    [Unit]
    Description=TempoFTP API Service
    After=network.target mariadb.service pure-ftpd.service

    [Service]
    User=lanotadm # Usuario que correrá el servicio (debe tener acceso a /opt/tempoftp)
    Group=lanotadm
    WorkingDirectory=/opt/tempoftp
    EnvironmentFile=/opt/tempoftp/.env
    ExecStart=/opt/tempoftp/venv/bin/uvicorn main:app --host 0.0.0.0 --port 9043
    Restart=always

    [Install]
    WantedBy=multi-user.target
    ```

5.  **Iniciar y habilitar el servicio de la API:**

    ```bash
    sudo systemctl daemon-reload
    sudo systemctl enable --now tempoftp.service
    ```

---

## 5. Verificación Final

1.  **Verificar estado de los servicios:**
    ```bash
    sudo systemctl status tempoftp.service
    sudo systemctl status pure-ftpd.service
    ```

2.  **Revisar logs:**
    ```bash
    sudo journalctl -u tempoftp.service -f
    sudo journalctl -u pure-ftpd.service -f
    ```

3.  **Realizar una solicitud de prueba:**
    Usa `curl` o cualquier cliente HTTP para enviar una solicitud al endpoint `/tmpftp` y verifica que el flujo completo funcione.

    ```bash
    curl -X POST http://localhost:9043/tmpftp -H "Content-Type: application/json" -d '{
        "usuario": "test.deploy@example.com",
        "id": "deploy_test_01",
        "ruta": "localhost:/tmp/test_data",
        "vigencia": 1
    }'
    ```

¡Tu servicio `TempoFTP` debería estar ahora en funcionamiento!