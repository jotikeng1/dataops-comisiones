"""
Acceso al Data Lake.
--------------------
- modo "azure": lee/escribe en el contenedor del Storage Account (ADLS Gen2 / Blob)
  usando la cadena de conexión de la variable AZURE_STORAGE_CONNECTION_STRING.
- modo "local": usa una carpeta (por defecto /lake) que imita la misma estructura.
  Sirve para probar en tu PC sin gastar crédito de Azure.

Estructura de carpetas (zonas del lake):
    raw/comisiones/ComisionEmpleados_V1_<periodo>.csv          ← entrada
    curated/comisiones/periodo=<periodo>/comisiones_<periodo>.parquet  ← salida
"""

import os
from pathlib import Path


class Lake:
    def __init__(self, modo: str, contenedor: str = "lake",
                 conn_str: str = None, base_dir: str = "/lake"):
        self.modo = modo
        self.contenedor = contenedor
        if modo == "azure":
            if not conn_str:
                raise ValueError("Falta AZURE_STORAGE_CONNECTION_STRING para el modo azure.")
            from azure.storage.blob import BlobServiceClient
            servicio = BlobServiceClient.from_connection_string(conn_str)
            self._cliente = servicio.get_container_client(contenedor)
            self._cuenta = servicio.account_name
        elif modo == "local":
            self._base = Path(base_dir)
        else:
            raise ValueError(f"STORAGE_MODE desconocido: {modo}")

    @classmethod
    def desde_entorno(cls, cfg_lake: dict) -> "Lake":
        return cls(
            modo=os.getenv("STORAGE_MODE", cfg_lake.get("modo", "azure")),
            contenedor=os.getenv("LAKE_CONTAINER", cfg_lake.get("contenedor", "lake")),
            conn_str=os.getenv("AZURE_STORAGE_CONNECTION_STRING"),
            base_dir=os.getenv("LOCAL_LAKE_DIR", cfg_lake.get("local_dir", "/lake")),
        )

    def describir(self, ruta: str) -> str:
        if self.modo == "azure":
            return f"abfss://{self.contenedor}@{self._cuenta}.dfs.core.windows.net/{ruta}"
        return str(self._base / ruta)

    def existe(self, ruta: str) -> bool:
        if self.modo == "azure":
            return self._cliente.get_blob_client(ruta).exists()
        return (self._base / ruta).exists()

    def leer(self, ruta: str) -> bytes:
        if self.modo == "azure":
            return self._cliente.download_blob(ruta).readall()
        return (self._base / ruta).read_bytes()

    def escribir(self, ruta: str, datos: bytes) -> None:
        if self.modo == "azure":
            self._cliente.upload_blob(ruta, datos, overwrite=True)
        else:
            destino = self._base / ruta
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(datos)
