import os
os.environ["TEMPOFTP_SIMULACRO"] = "1"
os.environ["TEMPOFTP_RATE_LIMIT_POST"] = "1000/hour"  # sin restricción en tests

# cifrado.py ahora aborta si falta TEMPOFTP_ENCRYPTION_KEY (P0-2) — hay que
# fijarla ANTES de cualquier import que cargue ese módulo, directa o
# transitivamente (main -> ... -> gestorftp/gestorftpsim -> cifrado).
from cryptography.fernet import Fernet
os.environ.setdefault("TEMPOFTP_ENCRYPTION_KEY", Fernet.generate_key().decode())

import asyncio
import pytest
from fastapi.testclient import TestClient
from main import app, get_gestor
from cifrado import descifrar
from gestorftp import GestorFTP
from gestorftpsim import GestorFTPsim

@pytest.fixture
def client():
    """Crea una instancia de TestClient para cada prueba, asegurando el aislamiento."""
    # Reinicia la base de datos del gestor antes de cada prueba para evitar fugas de estado.
    # Limpiamos la cache para asegurar que cada test obtenga una instancia fresca del gestor.
    get_gestor.cache_clear()
    # Obtenemos la instancia que se usará en este entorno de test.
    gestor_actual = get_gestor()
    if hasattr(gestor_actual, '_reiniciar_db_para_test'):
        gestor_actual._reiniciar_db_para_test()
    with TestClient(app) as c:
        yield c

def test_lifespan_valida_encryption_key_al_arrancar(monkeypatch):
    """P0-2: el lifespan debe invocar validate_encryption_key() al arrancar,
    para fallar rápido si falta TEMPOFTP_ENCRYPTION_KEY en vez de recién en el
    primer request real que instancie un gestor (ver test_cifrado.py para el
    comportamiento de la validación en sí)."""
    import main as main_module
    calls = []
    monkeypatch.setattr(main_module, "validate_encryption_key", lambda: calls.append(1))
    with TestClient(main_module.app):
        pass
    assert calls == [1]

def test_get_status(client):
    """Prueba que el endpoint de estado base funciona correctamente."""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"status": "active"}

def test_get_health(client):
    """Prueba que el endpoint de salud devuelve la estructura esperada."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    # El endpoint puede reportar espacio real o 'space_error' si /data no existe en este entorno
    has_disk_info = "space_free_gb" in data or "space_error" in data
    assert has_disk_info, f"Respuesta inesperada de /health: {data}"
    assert "ftpd" in data
    assert "database" in data

def test_get_tmpftp_status_not_found(client):
    """Prueba que se devuelve un 404 para un ID que no existe."""
    response = client.get("/tmpftp/id_inexistente")
    assert response.status_code == 404
    assert response.json()["detail"] == "No encontrado"

def test_create_and_get_status_success(client, monkeypatch):
    """Prueba el flujo completo: crear una solicitud y verificar su estado final."""
    # Forzar éxito determinista
    monkeypatch.setenv("TEMPOFTP_SIM_FORCE", "ok")

    request_data = {
        "usuario": "test.user@example.com",
        "id": "proyecto_test_1",
        "ruta": "10.0.0.1:/data/source",
        "vigencia": 5
    }

    # 1. Enviar la solicitud de creación
    post_response = client.post("/tmpftp", json=request_data)
    assert post_response.status_code == 200
    assert post_response.json()["id"] == "proyecto_test_1"

    # 2. Verificar el estado final (la simulación es síncrona)
    get_response = client.get("/tmpftp/proyecto_test_1")
    assert get_response.status_code == 200
    data = get_response.json()
    assert data["status"] == "listo"
    assert "ftpuser" in data
    assert "password" in data
    assert descifrar(data["password"]) # Verificamos que se pueda descifrar

    # limpiar
    monkeypatch.delenv("TEMPOFTP_SIM_FORCE", raising=False)

def test_create_fails_due_to_space(client, monkeypatch):
    """Prueba que la creación falla si no hay espacio suficiente."""
    # Forzar fallo determinista en simulador
    monkeypatch.setenv("TEMPOFTP_SIM_FORCE", "fail")

    request_data = {"usuario": "fail.user@example.com", "id": "proyecto_test_2", "ruta": "10.0.0.1:/data/source", "vigencia": 1}
    response = client.post("/tmpftp", json=request_data)
    assert response.status_code == 400
    assert response.json()["detail"] == {'id': 'proyecto_test_2', 'status': 'error', 'mensaje':  'Espacio insuficiente'}

    # limpiar
    monkeypatch.delenv("TEMPOFTP_SIM_FORCE", raising=False)

def test_create_duplicate_id_fails(client, monkeypatch):
    """Prueba que no se puede crear una solicitud con un ID duplicado."""
    monkeypatch.setenv("TEMPOFTP_SIM_FORCE", "ok")

    request_data = {
        "usuario": "duplicate.user@example.com",
        "id": "proyecto_duplicado",
        "ruta": "10.0.0.1:/data/source",
        "vigencia": 1
    }

    # 1. Primera solicitud (debería ser exitosa)
    response1 = client.post("/tmpftp", json=request_data)
    assert response1.status_code == 200

    # 2. Segunda solicitud con el mismo ID (debería fallar)
    response2 = client.post("/tmpftp", json=request_data)
    assert response2.status_code == 400
    assert "Ya existe una solicitud en proceso con el ID 'proyecto_duplicado'" in response2.json()["detail"]["mensaje"]

    # limpiar
    monkeypatch.delenv("TEMPOFTP_SIM_FORCE", raising=False)


def test_sim_force_ok(client, monkeypatch):
    """Forzar éxito con TEMPOFTP_SIM_FORCE=ok"""
    monkeypatch.setenv("TEMPOFTP_SIM_FORCE", "ok")
    request_data = {"usuario": "force.ok@example.com", "id": "force_ok_1", "ruta": "host:/src", "vigencia": 2}
    r = client.post("/tmpftp", json=request_data)
    assert r.status_code == 200
    st = client.get("/tmpftp/force_ok_1").json()
    assert st["status"] == "listo"
    # limpiar
    monkeypatch.delenv("TEMPOFTP_SIM_FORCE", raising=False)


def test_sim_force_fail(client, monkeypatch):
    """Forzar falla con TEMPOFTP_SIM_FORCE=fail"""
    monkeypatch.setenv("TEMPOFTP_SIM_FORCE", "fail")
    request_data = {"usuario": "force.fail@example.com", "id": "force_fail_1", "ruta": "host:/src", "vigencia": 2}
    r = client.post("/tmpftp", json=request_data)
    assert r.status_code == 400
    body = r.json()
    assert body["detail"]["status"] == "error"
    assert body["detail"]["mensaje"] == "Espacio insuficiente"
    monkeypatch.delenv("TEMPOFTP_SIM_FORCE", raising=False)


def test_sim_sizes_ok(client, monkeypatch):
    """Controlar por tamaños: remoto < libre => ok"""
    monkeypatch.delenv("TEMPOFTP_SIM_FORCE", raising=False)
    monkeypatch.setenv("TEMPOFTP_SIM_REMOTE_SIZE_BYTES", "1000")
    monkeypatch.setenv("TEMPOFTP_SIM_DATA_FREE_BYTES", "2000")
    request_data = {"usuario": "sizes.ok@example.com", "id": "sizes_ok_1", "ruta": "host:/src", "vigencia": 2}
    r = client.post("/tmpftp", json=request_data)
    assert r.status_code == 200
    st = client.get("/tmpftp/sizes_ok_1").json()
    assert st["status"] == "listo"
    # limpiar
    monkeypatch.delenv("TEMPOFTP_SIM_REMOTE_SIZE_BYTES", raising=False)
    monkeypatch.delenv("TEMPOFTP_SIM_DATA_FREE_BYTES", raising=False)


def test_sim_sizes_fail(client, monkeypatch):
    """Controlar por tamaños: remoto > libre => fail"""
    monkeypatch.delenv("TEMPOFTP_SIM_FORCE", raising=False)
    monkeypatch.setenv("TEMPOFTP_SIM_REMOTE_SIZE_BYTES", "2000000")
    monkeypatch.setenv("TEMPOFTP_SIM_DATA_FREE_BYTES", "1000000")
    request_data = {"usuario": "sizes.fail@example.com", "id": "sizes_fail_1", "ruta": "host:/src", "vigencia": 2}
    r = client.post("/tmpftp", json=request_data)
    assert r.status_code == 400
    body = r.json()
    assert body["detail"]["status"] == "error"
    assert body["detail"]["mensaje"] == "Espacio insuficiente"
    monkeypatch.delenv("TEMPOFTP_SIM_REMOTE_SIZE_BYTES", raising=False)
    monkeypatch.delenv("TEMPOFTP_SIM_DATA_FREE_BYTES", raising=False)

def test_delete_request_lifecycle(client, monkeypatch):
    """Prueba el ciclo de vida: crear, verificar y eliminar una solicitud."""
    monkeypatch.setenv("TEMPOFTP_SIM_FORCE", "ok")
    
    req_id = "del_test_1"
    request_data = {
        "usuario": "del.user@example.com",
        "id": req_id,
        "ruta": "host:/data",
        "vigencia": 1
    }

    # 1. Crear
    r = client.post("/tmpftp", json=request_data)
    assert r.status_code == 200

    # 2. Verificar que existe
    r = client.get(f"/tmpftp/{req_id}")
    assert r.status_code == 200

    # 3. Eliminar
    r = client.delete(f"/tmpftp/{req_id}")
    assert r.status_code == 200
    assert r.json()["status"] == "deleted"

    # 4. Verificar que ya no existe
    r = client.get(f"/tmpftp/{req_id}")
    assert r.status_code == 404

    monkeypatch.delenv("TEMPOFTP_SIM_FORCE", raising=False)

def test_delete_request_not_found(client):
    """Prueba borrar una solicitud inexistente."""
    r = client.delete("/tmpftp/id_no_existe_123")
    assert r.status_code == 404

def test_delete_user_success(client):
    """Prueba borrar un usuario FTP (simulado)."""
    # El simulador siempre devuelve éxito por defecto
    r = client.delete("/tmpftp/user/ftp_usuario_test")
    assert r.status_code == 200
    assert r.json()["status"] == "deleted"

def test_delete_user_not_found(client, monkeypatch):
    """Prueba borrar un usuario inexistente (simulando respuesta not_found del gestor)."""

    # Monkeypatching el método en la clase para que devuelva not_found
    async def mock_delete_not_found(self, user):
        return {"status": "not_found", "mensaje": "Usuario no encontrado"}

    monkeypatch.setattr(GestorFTPsim, "delete_ftp_user", mock_delete_not_found)

    r = client.delete("/tmpftp/user/usuario_fantasma")
    assert r.status_code == 404
    assert r.json()["detail"] == "Usuario no encontrado"


# ---------------------------------------------------------------------------
# P1-2 + preservación de created_at: limpieza por vencimiento de solicitudes
# ---------------------------------------------------------------------------

def _mk_db():
    from tmpftpdb import TMPFTPdb
    return TMPFTPdb(db_path=':memory:')


def test_obtener_expiradas_incluye_bloqueadas():
    """P1-2: una solicitud 'bloqueado' vencida debe ser elegible para limpieza,
    igual que una 'listo' vencida; una bloqueada aún vigente NO."""
    from datetime import datetime, timezone, timedelta
    db = _mk_db()
    now = datetime.now(timezone.utc)
    vencida = (now - timedelta(days=10)).isoformat()   # created hace 10d, vigencia 5 → vencida
    vigente = (now - timedelta(days=1)).isoformat()    # created hace 1d, vigencia 5 → vigente

    db.crear_solicitud("q_listo", "u@x.com", "h:/p", "listo",
                       {"usuario": "ftp_u_x", "vigencia": 5, "created_at": vencida})
    db.crear_solicitud("q_blk_vencida", "u@x.com", "h:/p", "bloqueado",
                       {"usuario": "ftp_u_x", "vigencia": 5, "created_at": vencida})
    db.crear_solicitud("q_blk_vigente", "u@x.com", "h:/p", "bloqueado",
                       {"usuario": "ftp_u_x", "vigencia": 5, "created_at": vigente})

    ids = {e["id"] for e in db.obtener_expiradas(now)}
    assert "q_listo" in ids
    assert "q_blk_vencida" in ids      # <-- corrección P1-2
    assert "q_blk_vigente" not in ids


def test_bloqueada_cuenta_como_activa_dentro_de_vigencia():
    """Una solicitud 'bloqueado' sigue contando como activa (no terminal), de modo
    que el usuario MySQL no se borra mientras siga reactivable dentro de vigencia."""
    db = _mk_db()
    db.crear_solicitud("q_blk", "u@x.com", "h:/p", "bloqueado",
                       {"usuario": "ftp_u_x", "vigencia": 5})
    activas = db.obtener_activas_por_usuario("ftp_u_x")
    assert any(a["id"] == "q_blk" for a in activas)


def test_listo_conserva_created_at(client, monkeypatch):
    """Regresión: al pasar a 'listo' la info debe conservar created_at, sin el cual
    eliminar_expiradas() nunca podría limpiar la solicitud."""
    monkeypatch.setenv("TEMPOFTP_SIM_FORCE", "ok")
    r = client.post("/tmpftp", json={
        "usuario": "a@b.com", "id": "p_cat", "ruta": "10.0.0.1:/data/s", "vigencia": 5,
    })
    assert r.status_code == 200
    gestor = get_gestor()
    sol = gestor.db.obtener_solicitud("p_cat")
    assert sol["estado"] == "listo"
    assert "created_at" in sol["info"] and sol["info"]["created_at"]
    monkeypatch.delenv("TEMPOFTP_SIM_FORCE", raising=False)


# --- GET /tmpftp: inventario para reconciliación (ago-2026) ---
#
# Antes sólo se podía preguntar por id, así que una cuenta que su dueño ya no
# reclamara era indetectable. En tahan había seis así, más once accesos de enero
# abiertos siete meses porque les faltaba created_at y eliminar_expiradas() no
# podía verlos.

def test_listado_vacio(client):
    r = client.get("/tmpftp")
    assert r.status_code == 200
    assert r.json() == {"total": 0, "sin_created_at": 0, "solicitudes": []}


def _crear(client, monkeypatch, id_, usuario="user@example.com"):
    """El simulador necesita TEMPOFTP_SIM_FORCE=ok para un resultado determinista;
    el campo del modelo es `usuario`, aunque en la base la columna sea `email`."""
    monkeypatch.setenv("TEMPOFTP_SIM_FORCE", "ok")
    r = client.post("/tmpftp", json={
        "usuario": usuario, "id": id_, "ruta": "10.0.0.1:/datos/x", "vigencia": 5,
    })
    assert r.status_code == 200, r.text
    return r


def test_listado_incluye_lo_creado(client, monkeypatch):
    _crear(client, monkeypatch, "LIST0001")
    data = client.get("/tmpftp").json()
    assert data["total"] == 1
    fila = data["solicitudes"][0]
    assert fila["id"] == "LIST0001"
    assert fila["email"] == "user@example.com"


def test_el_listado_nunca_devuelve_contrasenas(client, monkeypatch):
    """Enumerar accesos es una cosa; enumerar credenciales, otra."""
    _crear(client, monkeypatch, "LIST0002")
    data = client.get("/tmpftp").json()
    crudo = str(data)
    assert "password" not in crudo
    for fila in data["solicitudes"]:
        assert set(fila) == {"id", "email", "ruta", "estado", "created_at", "vigencia"}


def test_listado_filtra_por_estado(client, monkeypatch):
    _crear(client, monkeypatch, "LIST0003")
    todas = client.get("/tmpftp").json()["total"]
    assert todas == 1
    ninguna = client.get("/tmpftp", params={"estado": "expirado"}).json()
    assert ninguna["total"] == 0


def test_listado_respeta_el_limite(client, monkeypatch):
    for i in range(3):
        _crear(client, monkeypatch, f"LIMIT{i:03d}")
    assert client.get("/tmpftp", params={"limite": 2}).json()["total"] == 2


def test_listado_cuenta_las_que_no_pueden_vencer(client, monkeypatch):
    """El dato que motivó el endpoint: sin created_at la cuenta no caduca nunca."""
    _crear(client, monkeypatch, "LIST0004")
    gestor = get_gestor()
    sol = gestor.db.obtener_solicitud("LIST0004")
    info = dict(sol["info"])
    info.pop("created_at", None)
    gestor.db.actualizar_estado("LIST0004", sol["estado"], info)

    data = client.get("/tmpftp").json()
    assert data["sin_created_at"] == 1
    assert data["solicitudes"][0]["created_at"] is None
