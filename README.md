# tempoftp

Sistema para crear cuentas temporales de usuario para descargar datos vía FTP.

## Descripción

Este servicio, construido con FastAPI, expone una API para la creación de cuentas FTP temporales. Gestiona el ciclo de vida de las solicitudes, la creación de usuarios en Pure-FTPd (a través de una base de datos MySQL) y el registro de estados en una base de datos SQLite.

## Características

- Endpoints para estado del servicio, salud y gestión de cuentas FTP temporales.
- Arquitectura desacoplada con un gestor real (`GestorFTP`) y un simulador (`GestorFTPsim`).
- Integración con Pure-FTPd a través de una base de datos MySQL.
- Manejo de solicitudes, almacenamiento temporal y eliminación automática por vigencia.
- Uso de SQLite para registro de estados de cada solicitud.
- Generación de contraseñas criptográficamente seguras.
- Bloqueo y desbloqueo de usuarios FTP sin destruir la cuenta (campo `Status` en MySQL + registro de auditoría en SQLite).

## Documentación de la API

### Endpoints principales

#### 1. Estado del servicio
**GET /**

Consulta el estado actual del servicio para verificar que está activo.

**Respuesta:**
```json
{
    "status": "active"
}
```

---

#### 2. Salud del servicio
**GET /health**

Consulta el estado del servicio y los recursos disponibles (espacio en disco, estado del servidor FTPd y base de datos).

**Respuesta:**
```json
{
    "status": "ok",
    "space": "20TB",
    "ftpd": "up",
    "database": "ok"
}
```

---

#### 3. Crear solicitud FTP temporal
**POST /tmpftp**

Inicia la creación de una cuenta FTP temporal. Esta es una operación asíncrona. La API responde inmediatamente con un código `202 Accepted` para indicar que la solicitud ha sido aceptada y se está procesando en segundo plano. El cliente debe consultar el estado periódicamente usando el endpoint `GET /tmpftp/{id}`.

**Cuerpo (JSON):**
```json
{
    "usuario": "test.user@example.com",
    "id": "proyecto_test_1",
    "ruta": "10.0.0.1:/data/source",
    "vigencia": 10
}
```

**Parámetros:**
- `usuario`: Dirección de correo electrónico del usuario (string)
- `id`: Identificador único del proyecto/solicitud (string)
- `ruta`: Ruta remota en formato `host:/path` o `usuario@host:/path` (string)
- `vigencia`: Número de días de validez de la cuenta FTP (integer, default: 10)

**Respuesta exitosa (202 Accepted):**
```json
{
    "id": "proyecto_test_1",
    "status": "procesando",
    "detail": "La solicitud ha sido aceptada y está en proceso."
}
```

**Respuesta si está lista inmediatamente (200 OK):**
```json
{
    "id": "proyecto_test_1",
    "status": "listo",
    "ftpuser": "ftp_testuser_xxxx",
    "password": "Abc123xyz...",
    "vigencia": 5,
    "mensaje": "Listo, acceso creado"
}
```

**Respuesta de error (400 Bad Request):**
```json
{
    "detail": {
        "id": "proyecto_test_1",
        "status": "error",
        "mensaje": "Espacio insuficiente"
    }
}
```

---

#### 4. Consultar estado de solicitud FTP temporal
**GET /tmpftp/{id}**

Consulta el estado de una solicitud de cuenta FTP temporal. Retorna información sobre el progreso y, cuando está lista, las credenciales de acceso.

**Parámetros de ruta:**
- `id`: Identificador único de la solicitud (string)

**Respuesta (ejemplo pendiente - 202 Accepted):**
```json
{
    "status": "procesando",
    "mensaje": "Copiando datos..."
}
```

**Respuesta (ejemplo exitoso - 200 OK):**
```json
{
    "status": "listo",
    "ftpuser": "ftp_testuser_xxxx",
    "password": "Abc123xyz...",
    "vigencia": 10,
    "mensaje": "Listo, tiene 10 días para hacer la descarga.",
    "descargas": {
        "total_descargas": 1,
        "ultima_descarga": "26/Feb/2026:09:21:27 -0600"
    }
}
```

El campo `descargas` contiene:
- `total_descargas`: número de sesiones únicas de descarga (agrupadas por IP y día), contadas solo sobre los archivos de esta consulta.
- `ultima_descarga`: timestamp del último GET exitoso registrado en el log de Pure-FTPd.

**Respuesta de error (404 Not Found):**
```json
{
    "detail": "No encontrado"
}
```

---

#### 5. Eliminar solicitud FTP temporal
**DELETE /tmpftp/{id}**

Elimina una solicitud específica y sus datos asociados (base de datos SQLite y archivos).

**Parámetros de ruta:**
- `id`: Identificador único de la solicitud (string)

**Respuesta exitosa (200 OK):**
```json
{
    "status": "deleted",
    "id": "proyecto_test_1",
    "mensaje": "Solicitud eliminada exitosamente"
}
```

**Respuesta de error (404 Not Found):**
```json
{
    "detail": "Solicitud no encontrada"
}
```

**Respuesta de error (500 Internal Server Error):**
```json
{
    "detail": "Error al eliminar los archivos"
}
```

---

#### 6. Eliminar usuario FTP
**DELETE /tmpftp/user/{user}**

Elimina un usuario FTP virtual de la base de datos MySQL de Pure-FTPd y todo su directorio home asociado.

**Parámetros de ruta:**
- `user`: Nombre del usuario FTP (string)

**Respuesta exitosa (200 OK):**
```json
{
    "status": "deleted",
    "user": "ftp_testuser_xxxx",
    "mensaje": "Usuario FTP eliminado exitosamente"
}
```

**Respuesta de error (404 Not Found):**
```json
{
    "detail": "Usuario no encontrado"
}
```

**Respuesta de error (500 Internal Server Error):**
```json
{
    "detail": "Error al eliminar el directorio del usuario"
}
```

---

#### 7. Bloquear solicitud FTP
**POST /tmpftp/{id}/bloquear**

Bloquea el usuario FTP asociado a la solicitud sin eliminarlo. Pone `Status=0` en MySQL (impide login) y registra el bloqueo con razón y timestamp en SQLite. El directorio y los datos permanecen intactos para una posible reactivación futura.

**Parámetros de ruta:**
- `id`: Identificador único de la solicitud (string)

**Cuerpo (JSON, opcional):**
```json
{
    "razon": "exceso_descargas",
    "descargas": 5
}
```

**Campos opcionales:**
- `razon`: Motivo del bloqueo (string, default: `"no especificada"`)
- `descargas`: Número de descargas registradas al momento del bloqueo (integer)

**Respuesta exitosa (200 OK):**
```json
{
    "status": "bloqueado",
    "id": "proyecto_test_1",
    "usuario": "ftp_testuser_xxxx",
    "razon": "exceso_descargas",
    "en_mysql": true
}
```

El campo `en_mysql` indica si el usuario fue encontrado y actualizado en la base de datos de Pure-FTPd.

**Respuesta de error (404 Not Found):**
```json
{
    "detail": "Solicitud no encontrada"
}
```

**Respuesta de error (400 Bad Request):**
```json
{
    "detail": "La solicitud no tiene usuario FTP asociado"
}
```

---

#### 8. Desbloquear solicitud FTP
**POST /tmpftp/{id}/desbloquear**

Reactiva el usuario FTP de una solicitud previamente bloqueada. Pone `Status=1` en MySQL y restaura el estado `listo` en SQLite, eliminando los campos de auditoría de bloqueo.

**Parámetros de ruta:**
- `id`: Identificador único de la solicitud (string)

**Respuesta exitosa (200 OK):**
```json
{
    "status": "listo",
    "id": "proyecto_test_1",
    "usuario": "ftp_testuser_xxxx",
    "en_mysql": true
}
```

**Respuesta de error (404 Not Found):**
```json
{
    "detail": "Solicitud no encontrada"
}
```

**Respuesta de error (400 Bad Request):**
```json
{
    "detail": "La solicitud no está bloqueada (estado actual: 'listo')"
}
```

---

## Instalación

1.  Clona el repositorio.
2.  Crea y activa un entorno virtual:
    ```bash
    python -m venv .venv
    source .venv/bin/activate
    ```
3.  Instala las dependencias:
    ```bash
    pip install fastapi uvicorn cryptography aiomysql pytest httpx
    ```

## Configuración

El servicio se configura mediante variables de entorno.

### Variables de entorno (producción)
- TEMPOFTP_ENCRYPTION_KEY: clave Fernet para cifrar/descifrar contraseñas (obligatoria).
- RSYNC_SSH_USER: usuario SSH para du/rsync (default: lanotadm).
- FTP_DB_HOST, FTP_DB_PORT, FTP_DB_USER, FTP_DB_PASS, FTP_DB_NAME: conexión MySQL de Pure-FTPd.
- FTP_PASSWORD_FORMAT: 'md5' | 'cleartext' | 'crypt' (debe coincidir con MYSQLCrypt en pureftpd-mysql.conf).
- FTP_CRYPT_SCHEME: si FTP_PASSWORD_FORMAT='crypt', uno de 'sha512_crypt' | 'sha256_crypt' | 'md5_crypt' | 'des_crypt'.
- FTP_UID, FTP_GID: UID/GID del usuario FTP en Pure-FTPd (default 2001/2001).
- DATA_OWNER_USER, DATA_OWNER_GROUP: propietario/grupo para /data/<usuario> (default: RSYNC_SSH_USER o lanotadm).
- SKIP_CHOWN: '1' para omitir chown en /data (útil en contenedores sin permisos), default '0'.
- TEMPOFTP_LOG_LEVEL: nivel de logging de la app (DEBUG, INFO, WARNING, ERROR). Default: INFO.

### Variables de entorno (simulación)
- TEMPOFTP_SIMULACRO=1: usa gestor simulado (sin MySQL ni rsync real).
- TEMPOFTP_SIM_FORCE: 'ok'/'true'/'1' → fuerza éxito; 'fail'/'error'/'0' → fuerza error; otro → evalúa tamaños.
- TEMPOFTP_SIM_REMOTE_SIZE_BYTES: tamaño remoto simulado (bytes). Default: 100000000 (100 MB).
- TEMPOFTP_SIM_DATA_FREE_BYTES: espacio libre simulado (bytes). Default: 1000000000 (1 GB).

### Clave de Cifrado (`TEMPOFTP_ENCRYPTION_KEY`)

Esta variable es **crítica** para la seguridad. Contiene la clave secreta utilizada para cifrar y descifrar las contraseñas de los usuarios FTP. Debe ser la misma en el servidor y en cualquier cliente que necesite interpretar la contraseña.

1.  **Generar una clave segura**:
    ```bash
    pip install cryptography
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    ```

2.  **Configurar la variable de entorno**: Antes de ejecutar el servidor o el cliente, exporta la clave generada.
    ```bash
    export TEMPOFTP_ENCRYPTION_KEY="tu_clave_generada_aqui"
    ```

### Logging
Puedes ajustar la verbosidad de logs con TEMPOFTP_LOG_LEVEL.

Ejemplo:
```bash
export TEMPOFTP_LOG_LEVEL=DEBUG
uvicorn main:app --reload --port 9043
```

### Modo Simulación (`TEMPOFTP_SIMULACRO`)

Para desarrollo y pruebas locales, puedes ejecutar el servicio en modo simulación. En este modo, no se realizan operaciones reales en el sistema (como crear usuarios en MySQL o copiar archivos con `rsync`).

```bash
export TEMPOFTP_SIMULACRO=1
```

## Uso del Cliente (`apiclient.py`)

El cliente `apiclient.py` interactúa con la API. Cuando se consulta el estado de una solicitud y esta se encuentra en estado `"listo"`, la API devuelve la contraseña cifrada.

El cliente **descifra automáticamente la contraseña** si la variable de entorno `TEMPOFTP_ENCRYPTION_KEY` está configurada correctamente.

**Ejemplo de consulta de estado:**
```bash
# El cliente se encarga de descifrar el campo "password"
$ python apiclient.py --get proyecto_test_1
200 {'status': 'listo', 'usuario': 'ftp_test.user_abcd', 'password': 'cleartextpassword123', 'mensaje': 'Listo, tiene 10 días para hacer la descarga.', 'vigencia': 10}
```

## Cambios recientes importantes

- **Flujo idempotente de usuario FTP:** Si el usuario FTP ya existe en MySQL, se genera una nueva contraseña y se actualiza en MySQL. Si no existe, se crea el registro. En ambos casos la contraseña en claro nunca se almacena — solo el hash cifrado en SQLite.
- **Validación estricta de ruta remota:** El campo `ruta` debe ser del tipo `host:/ruta` o `usuario@host:/ruta`. Cualquier otro formato será rechazado por la API.
- **Ejemplos y tests:** Todos los ejemplos y pruebas deben usar rutas remotas válidas. Usar `...` como ruta ya no es aceptado.
- **Password siempre renovado:** En cada solicitud se genera una contraseña nueva. Si el usuario ya existe en MySQL, se actualiza su contraseña. El password en claro nunca se persiste — solo el hash cifrado retornado por la API.