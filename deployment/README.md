# Guía de Despliegue - TempoFTP

Este documento describe cómo desplegar la aplicación **TempoFTP** en un servidor de producción basado en **Rocky Linux** (o derivados RHEL 8/9 como AlmaLinux/CentOS Stream).

Se detallan dos estrategias de despliegue para la API:
1.  **Simple Uvicorn**: Ejecución directa mediante un servicio Systemd (puerto 9043).
2.  **Nginx + Uvicorn**: Nginx como proxy inverso (puerto 80/443) redirigiendo a Uvicorn local.

---

## 1. Prerrequisitos del Servidor

Asegúrate de que el sistema esté actualizado e instala los paquetes necesarios.

```bash
# Actualizar sistema
sudo dnf update -y

# Instalar repositorios EPEL (necesario para pure-ftpd)
sudo dnf install epel-release -y

# Instalar dependencias: Python, MariaDB, Pure-FTPd, Rsync, Git, Nginx y utilidades SELinux
sudo dnf install -y python3.11 python3.11-devel python3.11-pip mariadb-server pure-ftpd rsync git nginx policycoreutils-python-utils
```

---

## 2. Configuración de Base de Datos (MariaDB)

1.  **Iniciar servicio:**
    ```bash
    sudo systemctl enable --now mariadb
    sudo mysql_secure_installation
    ```

2.  **Crear base de datos y usuario:**
    Conéctate a MySQL (`sudo mysql -u root -p`) y ejecuta:

    ```sql
    CREATE DATABASE ftpdb;
    
    -- Reemplaza 'tu_contraseña_segura_db' por una real
    CREATE USER 'ftpuser'@'localhost' IDENTIFIED BY 'tu_contraseña_segura_db';
    
    GRANT SELECT, INSERT, UPDATE ON ftpdb.* TO 'ftpuser'@'localhost';
    FLUSH PRIVILEGES;

    USE ftpdb;
    
    -- Tabla de usuarios compatible con Pure-FTPd
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
    
    CREATE INDEX idx_user ON users (User);
    QUIT;
    ```

---

## 3. Instalación de la API TempoFTP

1.  **Clonar repositorio y preparar directorios:**
    ```bash
    sudo mkdir -p /opt/tempoftp
    # Asumiendo que el usuario de servicio será 'lanotadm'
    sudo chown lanotadm:lanotadm /opt/tempoftp
    
    # Clonar (ejecutar como lanotadm o cambiar dueño después)
    git clone <URL_DEL_REPOSITORIO> /opt/tempoftp
    cd /opt/tempoftp
    ```

2.  **Entorno Virtual:**
    ```bash
    python3.11 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    ```

3.  **Archivo `.env`:**
    Crea `/opt/tempoftp/.env` con la configuración (ver `Deployment.md` para referencia completa de variables).

---

## 4. Opción A: Despliegue Simple (Uvicorn Systemd)

Esta opción expone la API directamente en el puerto 9043. Útil para redes internas o pruebas rápidas.

1.  **Crear servicio `/etc/systemd/system/tempoftp.service`:**

    ```ini
    [Unit]
    Description=TempoFTP API Service
    After=network.target mariadb.service pure-ftpd.service

    [Service]
    User=lanotadm
    Group=lanotadm
    WorkingDirectory=/opt/tempoftp
    EnvironmentFile=/opt/tempoftp/.env
    # Escucha en 0.0.0.0 para acceso externo directo
    ExecStart=/opt/tempoftp/venv/bin/uvicorn main:app --host 0.0.0.0 --port 9043
    Restart=always

    [Install]
    WantedBy=multi-user.target
    ```

2.  **Habilitar servicio y Firewall:**
    ```bash
    sudo systemctl daemon-reload
    sudo systemctl enable --now tempoftp
    sudo firewall-cmd --add-port=9043/tcp --permanent
    sudo firewall-cmd --reload
    ```

---

## 5. Opción B: Despliegue con Nginx (Proxy Inverso)

Esta opción es más robusta y estándar para producción. Nginx maneja las peticiones en el puerto 80 (o 443) y las pasa a Uvicorn localmente.

1.  **Ajustar servicio Systemd:**
    Modifica `/etc/systemd/system/tempoftp.service` para que Uvicorn escuche solo en `127.0.0.1`.

    ```ini
    # ... dentro de [Service] ...
    ExecStart=/opt/tempoftp/venv/bin/uvicorn main:app --host 127.0.0.1 --port 9043
    ```
    Reinicia el servicio: `sudo systemctl daemon-reload && sudo systemctl restart tempoftp`.

2.  **Configurar Nginx:**
    Crea el archivo `/etc/nginx/conf.d/tempoftp.conf`:

    ```nginx
    server {
        listen 80;
        server_name ftp.tudominio.com; # O la IP del servidor

        location / {
            proxy_pass http://127.0.0.1:9043;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
    }
    ```

3.  **Configurar SELinux:**
    Es **crucial** permitir que Nginx inicie conexiones de red hacia Uvicorn.

    ```bash
    sudo setsebool -P httpd_can_network_connect 1
    ```

4.  **Iniciar Nginx y Firewall:**
    ```bash
    sudo systemctl enable --now nginx
    sudo firewall-cmd --add-service=http --permanent
    # Si usas HTTPS: sudo firewall-cmd --add-service=https --permanent
    
    # Cierra el puerto 9043 si estaba abierto previamente
    sudo firewall-cmd --remove-port=9043/tcp --permanent
    sudo firewall-cmd --reload
    ```

---

## 6. Verificación Final

1.  **Revisar estado de servicios:**
    ```bash
    sudo systemctl status tempoftp nginx
    ```

2.  **Probar endpoint de salud:**
    - Si usas Nginx: `curl http://localhost/health`
    - Si usas Uvicorn directo: `curl http://localhost:9043/health`