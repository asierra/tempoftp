import os
import sys
import argparse
import httpx
import json
from cifrado import descifrar

API_URL = "http://0.0.0.0:9043"

class APIClient:
    def __init__(self, api_url=API_URL):
        self.api_url = api_url
        self.client = httpx.Client()

    def get_status(self):
        r = self.client.get(f"{self.api_url}/")
        print(r.status_code, r.json())

    def get_health(self):
        r = self.client.get(f"{self.api_url}/health")
        print(r.status_code, r.json())

    def create_tmpftp(self, usuario=None, id=None, ruta=None, vigencia=None, json_payload=None):
        if json_payload:
            payload = json_payload
        else:
            payload = {"usuario": usuario, "id": id, "ruta": ruta, "vigencia": vigencia}
        r = self.client.post(f"{self.api_url}/tmpftp", json=payload)
        print(r.status_code, r.json())

    def get_tmpftp_status(self, id):
        r = self.client.get(f"{self.api_url}/tmpftp/{id}")
        data = r.json()
        if r.status_code == 200 and data.get("status") == "listo":
            try:
                data["password"] = descifrar(data["password"])
            except Exception:
                data["password"] = "ERROR: No se pudo descifrar la contraseña. Verifique la ENCRYPTION_KEY."
        
        print(r.status_code, data)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CLI para simular solicitudes a tempoftp API")
    parser.add_argument("--status", action="store_true", help="Consultar estado del servicio")
    parser.add_argument("--health", action="store_true", help="Consultar salud del servicio")
    parser.add_argument("--create", nargs=4, metavar=("usuario", "id", "ruta", "vigencia"), help="Crear solicitud tmpftp")
    parser.add_argument("--json", metavar="archivo", help="Crear solicitud tmpftp usando archivo JSON")
    parser.add_argument("--get", metavar="id", help="Consultar estado de solicitud por id")
    args = parser.parse_args()

    client = APIClient()

    if args.status:
        client.get_status()
    elif args.health:
        client.get_health()
    elif args.json:
        with open(args.json, "r") as f:
            json_payload = json.load(f)
        client.create_tmpftp(json_payload=json_payload)
    elif args.create:
        usuario, id, ruta, vigencia = args.create
        client.create_tmpftp(usuario, id, ruta, int(vigencia))
    elif args.get:
        client.get_tmpftp_status(args.get)
    else:
        parser.print_help()
