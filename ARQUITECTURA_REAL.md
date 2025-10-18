# Arquitectura y flujo para caso real de tempoftp

Este documento describe los pasos y componentes necesarios para implementar y probar el sistema tempoftp en un entorno real, con disco, rsync y pure-ftp integrados.

## 1. Arquitectura general

- **Backend FastAPI**: expone la API y gestiona el flujo de solicitudes.
- **Disco real**: almacenamiento de los datos transferidos.
- **rsync**: herramienta para copiar datos entre servidores de forma eficiente.
- **pure-ftp + MySQL**: gestión de usuarios FTP y credenciales en la base de datos real.
- **Base de datos SQLite**: registro de estados y metadatos de las solicitudes temporales.
- **Proceso asíncrono**: la copia de datos se ejecuta en segundo plano para no bloquear la API.

## 2. Flujo recomendado

1. **Recepción de solicitud**
   - El usuario envía una solicitud vía API (POST /tmpftp).
   - Se valida y registra la solicitud en SQLite con estado 'recibido'.

2. **Preparación y verificación**
   - Se prepara el entorno (creación de directorio, permisos).
   - Se verifica el espacio disponible.
   - Estado pasa a 'preparando'.

3. **Copia de datos (asíncrona)**
   - Se lanza un proceso en segundo plano (por ejemplo, usando Celery, FastAPI BackgroundTasks o threading) que ejecuta rsync.
   - El endpoint responde inmediatamente, indicando que la solicitud está en proceso.
   - El estado se actualiza progresivamente: 'traslado', 'listo', 'error'.

4. **Creación de usuario FTP**
   - Al finalizar la copia, se crea el usuario en la base de datos MySQL de pure-ftp.
   - Se almacena el usuario y la contraseña cifrada en SQLite.
   - Estado pasa a 'listo'.

5. **Consulta de estado**
   - El usuario puede consultar el estado y credenciales vía GET /tmpftp/{id}.

6. **Eliminación automática**
   - Se programa la eliminación del usuario y los datos tras la vigencia indicada (cron o tarea programada).

## 3. Componentes y dependencias

- Python 3.8+
- FastAPI
- Celery o BackgroundTasks (para asincronía)
- rsync instalado en ambos servidores
- pure-ftpd y MySQL configurados
- SQLite para estados temporales

## 4. Checklist para pruebas en entorno real

### 4.1 Paquetes del sistema

- rsync, openssh-client
- pure-ftpd con soporte MySQL (pure-ftpd-mysql)
- MySQL/MariaDB (o acceso a uno existente)
- Python 3.11+ y pip

### 4.2 Usuarios, permisos y directorios

- Usuario/grupo para FTP coherente con pure-ftpd
   - El código usa Uid/Gid=2001 y chown a `pureftpd:pureftpd` por defecto.
   - Asegura que existan UID/GID 2001, o ajusta el código/variables si tu instalación usa otros.
- Directorio destino: `/data`
   - Crear y asignar propiedad a `pureftpd:pureftpd`.

### 4.3 Base de datos (Pure-FTPd + MySQL)

- BD y usuario con permisos para INSERT en tabla de usuarios.
- Tabla mínima compatible:

   ```sql
   CREATE TABLE users (
      User VARCHAR(64) PRIMARY KEY,
      Password VARCHAR(64) NOT NULL,
      Uid INT NOT NULL,
      Gid INT NOT NULL,
      Dir VARCHAR(255) NOT NULL,
      Status TINYINT NOT NULL DEFAULT 1
   );
   ```

- Asegúrate que la configuración de pure-ftpd (mysql.conf) mapea a estas columnas.

### 4.4 SSH/rsync hacia el origen

- La verificación de tamaño remoto (du -sb) y rsync usan usuario fijo `lanotadm`.
- Si necesitas otro usuario, exporta `RSYNC_SSH_USER` en el entorno del servicio.
- Configurar autenticación por llave para:
   - `ssh lanotadm@host "du -sb /ruta"`
   - `rsync -av lanotadm@host:/ruta /data/usuario/id`

### 4.5 Variables de entorno

- `TEMPOFTP_SIMULACRO=0`
- `FTP_DB_HOST, FTP_DB_PORT, FTP_DB_USER, FTP_DB_PASS, FTP_DB_NAME`
- Opcional: `RSYNC_SSH_USER` para reemplazar `lanotadm`.

### 4.6 Ejecución de la API

- Instalar dependencias Python: `pip install -r requirements.txt`
- Ejecutar con un solo worker para evitar duplicación de tareas en background:
   - `uvicorn main:app --host 0.0.0.0 --port 9043 --workers 1`

## 5. Prueba de humo

1. POST `/tmpftp` con body:

    ```json
    {
       "usuario": "alguien@dominio",
       "id": "proyecto_real_1",
       "ruta": "lanotadm@host:/ruta/origen",
       "vigencia": 3
    }
    ```

    Respuesta esperada: `{ "id": "proyecto_real_1", "status": "recibido" }`.

2. GET `/tmpftp/proyecto_real_1` cada 3–5 s.
    - Estados: `recibido` → `preparando` → `traslado` → `listo` (o `error`).

3. Verificar acceso FTP
    - Usuario: `usuario` del JSON de estado.
    - Password: cifrada en JSON (la real quedó en MySQL).
    - Homedir: `/data/{usuario}` con datos en subcarpeta `{id}`.

## 6. Notas y problemas comunes

- Coherencia de UID/GID y propietario; si pure-ftpd usa otros valores, ajusta el INSERT y el chown.
- Permisos: el proceso de la API debe poder hacer chown en `/data`.
- Firewall: abrir puerto 9043 para la API y el rango pasivo de FTP.
- Concurrencia: usar `--workers 1` mientras las tareas corren en el event loop.
- Logs y diagnóstico: considerar logs por solicitud en el directorio de la solicitud.

## 6.1 Despliegue con systemd

1. Copiar el repositorio a `/opt/tempoftp` (o ajustar `WorkingDirectory` en el servicio).
2. Copiar el servicio y configurar variables:

   - Servicio:
     - `deploy/tempoftp.service` → `/etc/systemd/system/tempoftp.service`
   - Variables de entorno (elige según distro):
     - `deploy/tempoftp.env.example` → `/etc/default/tempoftp` (Debian/Ubuntu)
     - o `deploy/tempoftp.env.example` → `/etc/sysconfig/tempoftp` (RHEL/CentOS)

3. Recargar systemd y habilitar servicio:

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable tempoftp
   sudo systemctl start tempoftp
   sudo systemctl status tempoftp --no-pager
   ```

4. Logs del servicio:

   ```bash
   journalctl -u tempoftp -f -n 200
   ```

## 7. Ejemplo de flujo asíncrono (pseudocódigo)

```python
from fastapi import BackgroundTasks

@app.post("/tmpftp")
async def create_tmpftp(req: TmpFTPRequest, background_tasks: BackgroundTasks):
    gestorftp.registrar_solicitud(req)
    background_tasks.add_task(gestorftp.procesar_solicitud, req)
    return {"id": req.id, "status": "recibido"}
```

## 8. Documentación adicional

- Detalla los endpoints y formatos de respuesta en el README principal.
- Documenta los posibles estados y errores esperados.
- Explica cómo configurar pure-ftpd y MySQL para integración.

## Cambios recientes y advertencias

- **Flujo idempotente de usuario FTP:** Si el usuario ya existe en la base de datos de pure-ftp, la API devuelve el hash cifrado de la contraseña existente. No se genera ni sobreescribe el password.
- **Validación estricta de ruta remota:** El campo `ruta` debe ser del tipo `host:/ruta` o `usuario@host:/ruta`. Otros formatos serán rechazados.
- **Pruebas y ejemplos:** Asegúrate de que todos los tests y ejemplos usen rutas válidas.
- **No recuperación de password en claro:** Si el usuario ya existe, solo se puede obtener el hash cifrado, nunca el password original.

---

Este documento puede ampliarse con ejemplos de configuración, scripts de automatización y recomendaciones de seguridad según avances en el entorno real.