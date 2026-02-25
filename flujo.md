# Flujo tempoftp

Sistema para crear cuentas temporales de usuario para descargar datos vía FTP usando FastApi, MySQL y Pure-FTPd con usuarios virtuales.

1. **Recepción de solicitud**
   - El usuario envía una solicitud vía API (POST /tmpftp) con los datos `usuario`, `id` de la solicitud, `ruta` y opcionalmente `vigencia`.
   - De no recibirse vigencia, se establece como 5.
   - Se establece el estado como `recibido`.
   - Se valida y registra la solicitud en SQLite con el estado.

2. **Preparación y verificación**
   - Se prepara el entorno (creación de directorio, permisos).
   - Se determina si la ruta origen es local o remota.
   - Si es remota, se verifica el espacio disponible en disco.
   - Estado pasa a `preparando`.

3. **Procesamiento de datos (Copia o Enlace)**
   - **Ruta remota**: Se lanza un proceso en segundo plano que ejecuta rsync desde el servidor de almacenamiento. El estado pasa a `traslado` durante la copia.
   - **Ruta local**: Se crea un enlace simbólico en la carpeta del usuario apuntando a los datos locales.
   - En caso de error, el estado pasa a `error`.

4. **Gestión de usuario FTP**
   - Al finalizar la copia o el enlace, se verifica si el usuario ya existe en la base de datos MySQL.
   - Si el usuario **ya existe**, se actualiza su contraseña (no se crea un nuevo registro).
   - Si el usuario **no existe**, se crea el registro en la base de datos con la contraseña cifrada.
   - Se almacena el usuario y la contraseña cifrada en SQLite.
   - Estado pasa a `listo`.

5. **Consulta de estado**
   - El usuario puede consultar el estado y credenciales vía GET /tmpftp/{id}.

6. **Eliminación automática**
   - Se programa la eliminación del usuario y los datos tras la vigencia indicada (cron o tarea programada).
