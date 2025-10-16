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

## Documentación de la API

### Endpoints principales

#### 1. Estado del servicio
**GET /**
Respuesta:
```json
{
    "status": "active"
}
```

#### 2. Salud del servicio
**GET /health**
Respuesta:
```json
{
    "status": "ok",
    "space": "20TB",
    "ftpd": "up",
    "database": "ok"
}
```

#### 3. Crear solicitud FTP temporal
**POST /tmpftp**
Cuerpo (JSON):
```json
{
    "usuario": "test.user@example.com",
    "id": "proyecto_test_1",
    "ruta": "10.0.0.1:/data/source",
    "vigencia": 5
}
```
Respuesta exitosa:
```json
{
    "id": "proyecto_test_1",
    "status": "recibido"
}
```


#### 4. Consultar estado de solicitud
**GET /tmpftp/{id}**
Respuesta (ejemplo exitoso):
```json
{
    "status": "listo",
    "ftpuser": "ftp_testuser_xxxx",
    "password": "Abc123xyz...",  // Contraseña cifrada
    "vigencia": 5,
    "mensaje": "Listo, tiene 5 días para hacer la descarga."
}
```

### Ejemplos de errores

**Solicitud no encontrada:**
```json
{
    "detail": "No encontrado"
}
```

**Error por espacio insuficiente:**
```json
{
    "detail": {
        "id": "proyecto_test_2",
        "status": "error",
        "mensaje": "Espacio insuficiente"
    }
}
```

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
200 {'status': 'listo', 'usuario': 'ftp_test.user_abcd', 'password': 'cleartextpassword123', 'mensaje': 'Listo, tiene 5 días para hacer la descarga.', 'vigencia': 5}
```