# tempoftp

Sistema para crear cuentas temporales de usuario para descargar datos por FTP.

## Descripción

Este servicio, construido con FastAPI, permite la creación de cuentas temporales para descargar datos vía FTP, gestionando el acceso y almacenamiento mediante interacción con Pure-FTPd y bases de datos MySQL y SQLite.

## Características

- Endpoints para estado del servicio, salud y gestión de cuentas FTP temporales.
- Integración con Pure-FTPd y base MySQL.
- Manejo de solicitudes, almacenamiento temporal y eliminación automática por vigencia.
- Uso de SQLite para registro de solicitudes.