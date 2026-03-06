from fastapi import FastAPI, HTTPException, Depends, Body, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn
import os
import logging
import uuid
import shutil
from contextlib import asynccontextmanager
from contextvars import ContextVar
from functools import lru_cache
from typing import Optional
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# --- Cargar variables de entorno desde .env para desarrollo ---
from dotenv import load_dotenv
load_dotenv()

# --- Correlation ID context var ---
_request_id_var: ContextVar[str] = ContextVar('request_id', default='-')

class CorrelationIDFilter(logging.Filter):
    def filter(self, record):
        record.request_id = _request_id_var.get('-')
        return True

# --- Logging configuration ---
LOG_LEVEL = os.getenv("TEMPOFTP_LOG_LEVEL", "INFO").upper()
try:
    _numeric_level = getattr(logging, LOG_LEVEL)
except AttributeError:
    _numeric_level = logging.INFO
logging.basicConfig(
    level=_numeric_level,
    format="%(asctime)s - %(name)s - %(levelname)s - [%(request_id)s] %(message)s",
)
for _handler in logging.root.handlers:
    _handler.addFilter(CorrelationIDFilter())

logger = logging.getLogger(__name__)


def validate_pureftpd_config():
    """Verifica que MYSQLCrypt en pureftpd-mysql.conf coincida con el algoritmo usado en código."""
    conf_path = os.getenv('PUREFTPD_MYSQL_CONF', '/etc/pure-ftpd/db/mysql.conf')
    if not os.path.exists(conf_path):
        logger.info(f"Archivo Pure-FTPd no encontrado ({conf_path}), omitiendo validación")
        return
    try:
        with open(conf_path) as f:
            for line in f:
                if line.strip().startswith('MYSQLCrypt'):
                    configured = line.split()[-1].lower()
                    if configured != 'argon2':
                        raise RuntimeError(
                            f"MYSQLCrypt={configured} pero el código usa argon2. "
                            f"Actualizar _hash_password() o pureftpd-mysql.conf"
                        )
    except PermissionError:
        logger.warning(f"Sin permiso de lectura sobre {conf_path}, omitiendo validación")
        return
    logger.info("Configuración Pure-FTPd validada")


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_pureftpd_config()
    yield


limiter = Limiter(key_func=get_remote_address)
app = FastAPI(lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    request_id = request.headers.get('X-Request-ID', str(uuid.uuid4()))
    token = _request_id_var.set(request_id)
    try:
        response = await call_next(request)
        response.headers['X-Request-ID'] = request_id
        return response
    finally:
        _request_id_var.reset(token)

@lru_cache()
def get_gestor():
    """
    Función de dependencia que instancia el gestor apropiado (real o simulado)
    basado en variables de entorno. Si TEMPOFTP_SIMULACRO está definido,
    respeta su valor (0/1, true/false). Si no, en contexto de pytest usa el
    simulador por defecto.
    """
    sim_env = os.getenv("TEMPOFTP_SIMULACRO")
    if sim_env is not None:
        val = str(sim_env).strip().lower()
        use_sim = val in ("1", "true", "yes", "on")
    else:
        use_sim = bool(os.getenv("PYTEST_CURRENT_TEST"))

    if use_sim:
        from gestorftpsim import GestorFTPsim
        return GestorFTPsim()
    from gestorftp import GestorFTP
    return GestorFTP()


class TmpFTPRequest(BaseModel):
    usuario: str # <direccion email>
    id: str # <string>
    ruta: str # <IP:path>
    vigencia: int = 10 # <num dias>

class BloqueoRequest(BaseModel):
    razon: Optional[str] = None
    descargas: Optional[int] = None

@app.get("/")
async def get_status():
    # Consulta el estado actual del servicio
    return {"status": "active"}

@app.get("/health")
async def get_health():
    data_path = os.getenv('TEMPOFTP_DATA_PATH', '/data')
    try:
        usage = shutil.disk_usage(data_path)
        disk_info = {
            "space_free_gb": round(usage.free / (1024**3), 2),
            "space_total_gb": round(usage.total / (1024**3), 2),
            "space_used_pct": round(usage.used / usage.total * 100, 1),
        }
    except (FileNotFoundError, PermissionError) as e:
        logger.warning(f"No se pudo leer espacio en disco ({data_path}): {e}")
        disk_info = {"space_error": "unavailable"}
    return {"status": "ok", **disk_info, "ftpd": "up", "database": "ok"}

_RATE_LIMIT_POST = os.getenv("TEMPOFTP_RATE_LIMIT_POST", "10/hour")


@app.post("/tmpftp")
@limiter.limit(_RATE_LIMIT_POST)
async def create_tmpftp(request: Request, req: TmpFTPRequest, gestor=Depends(get_gestor)):
    try:
        # El gestor puede devolver un dict con estado inmediato (ej. sim fuerza "ok").
        result = await gestor.create_usertmp(req.id, req.usuario, req.ruta, req.vigencia)
        # Caso 1: el propio create_usertmp devuelve listo
        if isinstance(result, dict) and str(result.get("status", "")).lower() == "listo":
            body = {
                "id": req.id,
                "status": "listo",
                "ftpuser": result.get("ftpuser"),
                "password": result.get("password"),  # cifrada
                "vigencia": result.get("vigencia", req.vigencia),
                "mensaje": result.get("mensaje", "Listo, acceso creado"),
            }
            return JSONResponse(content=body, status_code=status.HTTP_200_OK)
        # Caso 2: consultar estado inmediatamente por si quedó listo (simulador)
        try:
            status_now = await gestor.get_status(req.id)
        except Exception:
            status_now = None
        if isinstance(status_now, dict) and str(status_now.get("status", "")).lower() == "listo":
            body = {
                "id": req.id,
                "status": "listo",
                "ftpuser": status_now.get("ftpuser"),
                "password": status_now.get("password"),
                "vigencia": status_now.get("vigencia", req.vigencia),
                "mensaje": status_now.get("mensaje", "Listo, acceso creado"),
            }
            return JSONResponse(content=body, status_code=status.HTTP_200_OK)
        # Caso 3: pendiente/procesando
        return JSONResponse(
            content={
                "id": req.id,
                "status": "procesando",
                "detail": "La solicitud ha sido aceptada y está en proceso.",
            },
            status_code=status.HTTP_202_ACCEPTED,
            headers={"Location": f"/tmpftp/{req.id}", "Retry-After": "10"}
        )
    except Exception as e:
        logger.error(f"Error al crear tmpftp para {req.id}: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail={"id": req.id, "status": "error", "mensaje": str(e)})

@app.get("/tmpftp/{id}")
async def get_tmpftp_status(id: str, gestor=Depends(get_gestor)):
    # Consulta el estado de la solicitud por ID
    result = await gestor.get_status(id)
    if not result:
        raise HTTPException(status_code=404, detail="No encontrado")
    st = str(result.get("status", "")).lower()
    if st == "listo":
        # Enriquecer respuesta con estadísticas de descarga (si existen)
        ftp_user = result.get("ftpuser") or result.get("usuario") # fallback por si el campo varía
        if ftp_user:
            stats = await gestor.obtener_estadisticas_descargas(ftp_user, consulta_id=id)
            # Mezclar stats en la respuesta principal o bajo una clave 'descargas'
            result["descargas"] = stats
        return JSONResponse(content=result, status_code=status.HTTP_200_OK)
    elif st == "error":
        return JSONResponse(content=result, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    return JSONResponse(content=result, status_code=status.HTTP_202_ACCEPTED, headers={"Retry-After": "10"})

@app.delete("/tmpftp/{id}")
async def delete_tmpftp_request(id: str, gestor=Depends(get_gestor)):
    """Elimina una solicitud específica y sus datos asociados."""
    try:
        result = await gestor.delete_request(id)
        if result.get("status") == "not_found":
            raise HTTPException(status_code=404, detail="Solicitud no encontrada")
        return JSONResponse(content=result, status_code=status.HTTP_200_OK)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error eliminando solicitud {id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/tmpftp/user/{user}")
async def delete_ftp_user(user: str, gestor=Depends(get_gestor)):
    """Elimina un usuario FTP virtual y todo su directorio home."""
    try:
        result = await gestor.delete_ftp_user(user)
        if result.get("status") == "not_found":
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        return JSONResponse(content=result, status_code=status.HTTP_200_OK)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error eliminando usuario {user}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/tmpftp/{id}/bloquear")
async def bloquear_tmpftp(id: str, req: BloqueoRequest = Body(default=BloqueoRequest()), gestor=Depends(get_gestor)):
    """Bloquea el usuario FTP de una solicitud sin eliminarlo (Status=0 en MySQL)."""
    try:
        result = await gestor.bloquear_solicitud(id, razon=req.razon, descargas=req.descargas)
        st = result.get("status")
        if st == "not_found":
            raise HTTPException(status_code=404, detail="Solicitud no encontrada")
        if st == "error":
            raise HTTPException(status_code=400, detail=result.get("mensaje"))
        return JSONResponse(content=result, status_code=status.HTTP_200_OK)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error bloqueando solicitud {id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/tmpftp/{id}/desbloquear")
async def desbloquear_tmpftp(id: str, gestor=Depends(get_gestor)):
    """Reactiva el usuario FTP de una solicitud bloqueada (Status=1 en MySQL)."""
    try:
        result = await gestor.desbloquear_solicitud(id)
        st = result.get("status")
        if st == "not_found":
            raise HTTPException(status_code=404, detail="Solicitud no encontrada")
        if st == "error":
            raise HTTPException(status_code=400, detail=result.get("mensaje"))
        return JSONResponse(content=result, status_code=status.HTTP_200_OK)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error desbloqueando solicitud {id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9043, log_level=os.getenv("TEMPOFTP_LOG_LEVEL", "info").lower())          
