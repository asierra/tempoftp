# Flujo tempoftp

Sistema para crear cuentas temporales de usuario para descargar datos vía FTP usando FastApi, MySQL y Pure-FTPd con usuarios virtuales.

1. **Recepción de solicitud**
   - El usuario envía una solicitud vía API (POST /tmpftp) con los datos `usuario`, `id` de la solicitud, `ruta` y opcionalmente `vigencia`.
   - De no recibirse vigencia, se establece como 5.
   - Se establece el estado como `recibido`.
   - Se valida y registra la solicitud en SQLite con el estado.

2. **Preparación y verificación**
   - Se prepara el entorno (creación de directorio, permisos).
   - Si la ruta no es local, se verifica el espacio disponible.
   - Estado pasa a `preparando` o en caso de que la ruta local no exista, `error`.

3. **Copia de datos (asíncrona)**
   - Si la ruta no es local, se lanza un proceso en segundo plano que ejecuta rsync desde el servidor de almacenamiento.
   - Dependiendo de los resultados del rsync asíncrono, el estado se actualiza progresivamente: `trasladando`, `error`, `trasladado`.

4. **Creación de usuario FTP**
   - Al finalizar la copia o verificada la ruta local, se crea el usuario en la base de datos MySQL de pure-ftp con la contraseña cifrada usando argon2.
   - Se almacena el usuario y la contraseña cifrada en SQLite.
   - Estado pasa a `ready`.

5. **Consulta de estado**
   - El usuario puede consultar el estado y credenciales vía GET /tmpftp/{id}.

6. **Eliminación automática**
   - Se programa la eliminación del usuario y los datos tras la vigencia indicada (cron o tarea programada).
