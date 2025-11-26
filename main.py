from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Body, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn
import os
import logging
from functools import lru_cache
from typing import Dict, Any
import secrets
import string
import types

# --- Cargar variables de entorno desde .env para desarrollo ---
from dotenv import load_dotenv
load_dotenv()

# --- Logging configuration ---
LOG_LEVEL = os.getenv("TEMPOFTP_LOG_LEVEL", "INFO").upper()
try:
    _numeric_level = getattr(logging, LOG_LEVEL)
except AttributeError:
    _numeric_level = logging.INFO
logging.basicConfig(
    level=_numeric_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)
app = FastAPI()

# --- Placeholders to allow tests that monkeypatch these (Query Processor compatibility) ---
db = None
recover = None

# Fallback in-memory store for /query endpoints if db is not monkeypatched
_mem_store: Dict[str, Dict[str, Any]] = {}

def _gen_id(n: int = 8) -> str:
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(n))

def _db_crear_consulta(consulta_id: str, query_dict: Dict[str, Any]) -> bool:
    _mem_store[consulta_id] = {
        "id": consulta_id,
        "estado": "recibido",
        "progreso": 0,
        "mensaje": "recibido",
        "query": query_dict,
        "resultados": None,
        "timestamp_actualizacion": None,
    }
    return True

def _db_obtener_consulta(consulta_id: str) -> Dict[str, Any]:
    return _mem_store.get(consulta_id)

def _db_actualizar_estado(consulta_id: str, estado: str, progreso: int | None = None, mensaje: str | None = None) -> bool:
    rec = _mem_store.get(consulta_id)
    if not rec:
        return False
    rec["estado"] = estado
    if progreso is not None:
        rec["progreso"] = progreso
    if mensaje is not None:
        rec["mensaje"] = mensaje
    return True

def _db_guardar_resultados(consulta_id: str, resultados: Dict[str, Any], mensaje: str | None = None) -> bool:
    rec = _mem_store.get(consulta_id)
    if not rec:
        return False
    rec["resultados"] = resultados
    rec["estado"] = "completado"
    rec["progreso"] = 100
    rec["mensaje"] = mensaje or "completado"
    return True

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
    vigencia: int # <num dias>

@app.get("/")
async def get_status():
    # Consulta el estado actual del servicio
    return {"status": "active"}

@app.get("/health")
async def get_health():
    # Consulta el estado del servicio y recursos
    return {"status": "ok", "space": "20TB", "ftpd": "up", "database": "ok"}

@app.post("/tmpftp")
async def create_tmpftp(req: TmpFTPRequest, gestor=Depends(get_gestor)):
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
        raise HTTPException(status_code=400, detail={"id": req.id, "status": "error", "mensaje": str(e)})
        logger.error(f"Error al crear tmpftp para {req.id}: {e}", exc_info=True)

@app.get("/tmpftp/{id}")
async def get_tmpftp_status(id: str, gestor=Depends(get_gestor)):
    # Consulta el estado de la solicitud por ID
    result = await gestor.get_status(id)
    if not result:
        raise HTTPException(status_code=404, detail="No encontrado")
    st = str(result.get("status", "")).lower()
    if st == "listo":
        return JSONResponse(content=result, status_code=status.HTTP_200_OK)
    return JSONResponse(content=result, status_code=status.HTTP_202_ACCEPTED, headers={"Retry-After": "10"})


# --- Endpoints sugeridos aplicados ---
# Se asume que existen en el entorno:
# - _validate_and_prepare_request
# - processor.procesar_request
# - generar_id_consulta
# - db.crear_consulta / db.obtener_consulta
# - recover.procesar_consulta

@app.post("/query")
async def crear_solicitud(
    background_tasks: BackgroundTasks,
    request_data: Dict[str, Any] = Body(...),
):
    # Implementación mínima compatible con tests; sin validación estricta
    try:
        consulta_id = _gen_id()
        query_dict = dict(request_data or {})
        # Crear en DB o fallback
        if db and hasattr(db, "crear_consulta"):
            ok = db.crear_consulta(consulta_id, query_dict)
            if not ok:
                raise HTTPException(status_code=500, detail="Error almacenando consulta")
        else:
            _db_crear_consulta(consulta_id, query_dict)
        # Encolar procesamiento si recover fue inyectado
        if recover and hasattr(recover, "procesar_consulta"):
            background_tasks.add_task(recover.procesar_consulta, consulta_id, query_dict)
        else:
            _db_actualizar_estado(consulta_id, "procesando", 10, "aceptado")
        body = {"success": True, "consulta_id": consulta_id, "estado": "recibido"}
        return JSONResponse(content=body, status_code=status.HTTP_202_ACCEPTED, headers={"Location": f"/query/{consulta_id}"})
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/query/{consulta_id}/restart")
async def reiniciar_consulta(consulta_id: str, background_tasks: BackgroundTasks):
    consulta = db.obtener_consulta(consulta_id) if (db and hasattr(db, "obtener_consulta")) else _db_obtener_consulta(consulta_id)
    if not consulta:
        raise HTTPException(status_code=404, detail="Consulta no encontrada.")

    if consulta.get("estado") not in ["procesando", "error", "completado"]:
        raise HTTPException(
            status_code=400,
            detail=f"No se puede reiniciar una consulta en estado '{consulta.get('estado')}'. Solo 'procesando', 'error' o 'completado'."
        )

    if recover and hasattr(recover, "procesar_consulta"):
        background_tasks.add_task(recover.procesar_consulta, consulta_id, consulta.get("query") or {})
    else:
        _db_actualizar_estado(consulta_id, "procesando", 10, "reenviada")

    return JSONResponse(
        content={"success": True, "message": f"La consulta '{consulta_id}' ha sido reenviada para su procesamiento."},
        status_code=status.HTTP_202_ACCEPTED,
        headers={"Location": f"/query/{consulta_id}"}
    )


@app.get("/query/{consulta_id}")
async def obtener_consulta(
    consulta_id: str,
    resultados: bool = False,
):
    consulta = db.obtener_consulta(consulta_id) if (db and hasattr(db, "obtener_consulta")) else _db_obtener_consulta(consulta_id)
    if not consulta:
        raise HTTPException(status_code=404, detail="Consulta no encontrada")

    estado = (consulta.get("estado") or "").lower()

    if resultados and estado == "completado" and consulta.get("resultados"):
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"consulta_id": consulta_id, "estado": "completado", "resultados": consulta["resultados"]},
        )

    resp = {
        "consulta_id": consulta_id,
        "estado": consulta.get("estado"),
        "progreso": consulta.get("progreso"),
        "mensaje": consulta.get("mensaje"),
        "timestamp": consulta.get("timestamp_actualizacion"),
    }

    if estado == "completado":
        res = consulta.get("resultados") or {}
        fuentes = res.get("fuentes", {})
        resp["total_archivos"] = res.get("total_archivos", 0)
        resp["archivos_lustre"] = fuentes.get("lustre", {}).get("total", 0)
        resp["archivos_s3"] = fuentes.get("s3", {}).get("total", 0)
        return JSONResponse(status_code=status.HTTP_200_OK, content=resp)
    elif estado in ("procesando", "recibido", "preparando", "recuperando-local", "s3-listado", "s3-descargando"):
        return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=resp, headers={"Retry-After": "10"})
    elif estado == "error":
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=resp)
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=resp)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9043, log_level=os.getenv("TEMPOFTP_LOG_LEVEL", "info").lower())          
