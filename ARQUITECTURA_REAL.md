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

## 4. Recomendaciones para pruebas en entorno real

- Realiza pruebas con archivos pequeños antes de transferencias grandes.
- Verifica permisos de escritura en el disco destino.
- Asegúrate de que rsync y pure-ftpd funcionen correctamente desde la línea de comandos.
- Revisa los logs y estados en la base de datos para detectar errores.
- Considera agregar notificaciones o webhooks para informar al usuario cuando la transferencia esté lista.

## 5. Ejemplo de flujo asíncrono (pseudocódigo)

```python
from fastapi import BackgroundTasks

@app.post("/tmpftp")
async def create_tmpftp(req: TmpFTPRequest, background_tasks: BackgroundTasks):
    gestorftp.registrar_solicitud(req)
    background_tasks.add_task(gestorftp.procesar_solicitud, req)
    return {"id": req.id, "status": "recibido"}
```

## 6. Documentación adicional

- Detalla los endpoints y formatos de respuesta en el README principal.
- Documenta los posibles estados y errores esperados.
- Explica cómo configurar pure-ftpd y MySQL para integración.

---

Este documento puede ampliarse con ejemplos de configuración, scripts de automatización y recomendaciones de seguridad según avances en el entorno real.