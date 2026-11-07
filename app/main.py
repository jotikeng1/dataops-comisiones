#!/usr/bin/env python3
"""
Pipeline DataOps de comisiones - Python 3.11
--------------------------------------------
Basado en el main.py visto en clase, adaptado a los requerimientos del proyecto:

1. Determina el periodo (AAAAMM)        → argumento --periodo, variable PERIODO o mes actual
2. Lee el CSV desde el Data Lake        → raw/comisiones/ComisionEmpleados_V1_<periodo>.csv
3. Normaliza y valida el CSV            → tolera cambios de encabezado (ej. "ID Empleado")
4. Lee rrhh.empleado desde PostgreSQL
5. Join CSV + BD por empleado_id
6. Calcula salario_total = salario + comisión
7. Escribe la tabla consolidada en Parquet (y Excel) en la zona curated del Lake
8. (Opcional) Envía el Excel por correo, como en el ejercicio de clase

Modo verificación (quality gate del CI/CD):
    python main.py --verificar --periodo 202610
    Lee el Parquet ya generado y comprueba las reglas de calidad.
"""

import argparse
import io
import json
import os
import smtplib
import sys
from datetime import date
from email import encoders
from email.header import Header
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import pandas as pd

import etl
from storage import Lake


# ───────────────────────── 1. Configuración ───────────────────────── #
# config.json guarda solo valores NO secretos. Las contraseñas llegan por
# variables de entorno (en Jenkins, desde el almacén de credenciales).
def load_config(path=None) -> dict:
    path = Path(path) if path else Path(__file__).with_name("config.json")
    if not path.exists():
        raise FileNotFoundError(f"Config file {path} no encontrado.")
    return json.loads(path.read_text(encoding="utf-8"))


CFG = load_config(os.getenv("CONFIG_FILE"))
AMBIENTE = os.getenv("AMBIENTE", "dev")


def db_config() -> dict:
    db = CFG["db"]
    password = os.getenv("PG_PASSWORD")
    if not password:
        raise EnvironmentError("Falta la variable de entorno PG_PASSWORD.")
    return {
        "host": os.getenv("PG_HOST", db["host"]),
        "port": int(os.getenv("PG_PORT", db["port"])),
        "dbname": os.getenv("PG_DB", db["dbname"]),
        "user": os.getenv("PG_USER", db["user"]),
        "password": password,
    }


def rutas(periodo: str) -> dict:
    base_out = f"curated/comisiones/periodo={periodo}"
    return {
        "csv": f"raw/comisiones/ComisionEmpleados_V1_{periodo}.csv",
        "parquet": f"{base_out}/comisiones_{periodo}.parquet",
        "excel": f"{base_out}/comisiones_{periodo}.xlsx",
        "resumen": f"{base_out}/_resumen.json",
    }


# ───────────────────────── 2. Extracción BD ───────────────────────── #
def leer_empleados_bd() -> pd.DataFrame:
    import psycopg2
    query = """
        SELECT empleado_id, tip_documento, num_documento, nom_empleado,
               ape_empleado, cod_cargo, cod_departamento,
               mnt_salario, mnt_tope_comision
        FROM rrhh.empleado;
    """
    with psycopg2.connect(**db_config()) as conn, conn.cursor() as cur:
        cur.execute(query)
        return pd.DataFrame(cur.fetchall(), columns=[c[0] for c in cur.description])


# ───────────────────────── 3. Correo (de la clase) ───────────────────────── #
def send_mail(to: str, subj: str, html: str, nombre_adjunto: str, adjunto: bytes) -> None:
    smtp_cfg = CFG["smtp"]
    msg = MIMEMultipart()
    msg["From"], msg["To"] = smtp_cfg["sender_email"], to
    msg["Subject"] = str(Header(subj, "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    part = MIMEBase("application", "octet-stream")
    part.set_payload(adjunto)
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f'attachment; filename="{nombre_adjunto}"')
    msg.attach(part)

    with smtplib.SMTP(smtp_cfg["server"], smtp_cfg["port"], timeout=30) as smtp:
        if smtp_cfg.get("use_tls") or smtp_cfg.get("port") == 587:
            smtp.starttls()
        if smtp_cfg.get("user") and os.getenv("SMTP_PASSWORD"):
            smtp.login(smtp_cfg["user"], os.getenv("SMTP_PASSWORD"))
        smtp.send_message(msg)


# ───────────────────────── 4. Pipeline ───────────────────────── #
def ejecutar(periodo: str) -> int:
    print(f"> Ambiente: {AMBIENTE} | Periodo: {periodo}")
    lake = Lake.desde_entorno(CFG.get("lake", {}))
    r = rutas(periodo)

    # 4.1 Si no hay CSV para el periodo, terminar sin error (igual que en clase)
    if not lake.existe(r["csv"]):
        print(f"> No hay comisiones para {periodo} en {lake.describir(r['csv'])}. Fin.")
        return 0

    # 4.2 Leer y validar CSV (utf-8-sig elimina el BOM si viene)
    print(f"> Leyendo CSV: {lake.describir(r['csv'])}")
    csv_raw = pd.read_csv(io.BytesIO(lake.leer(r["csv"])), sep=";", encoding="utf-8-sig")
    csv_df = etl.preparar_csv(csv_raw)
    print(f"  Filas CSV válidas: {len(csv_df)}")

    # 4.3 Leer empleados desde PostgreSQL
    print("> Leyendo rrhh.empleado desde PostgreSQL")
    db_df = leer_empleados_bd()
    print(f"  Filas BD: {len(db_df)}")

    # 4.4 Join + cálculo
    unido, sin_match = etl.unir(csv_df, db_df)
    if sin_match:
        print(f"  ADVERTENCIA: empleado_id del CSV sin registro en BD: {sin_match}")
    salida = etl.construir_salida(etl.calcular_salario_total(unido), periodo, AMBIENTE)
    print(f"  Filas consolidadas: {len(salida)}")

    # 4.5 Escribir Parquet y Excel en la zona curated del lake
    buf_pq = io.BytesIO()
    salida.to_parquet(buf_pq, index=False, engine="pyarrow")
    lake.escribir(r["parquet"], buf_pq.getvalue())
    print(f"> Parquet escrito: {lake.describir(r['parquet'])}")

    buf_xl = io.BytesIO()
    salida.to_excel(buf_xl, index=False, engine="openpyxl")
    lake.escribir(r["excel"], buf_xl.getvalue())
    print(f"> Excel escrito:   {lake.describir(r['excel'])}")

    resumen = {
        "periodo": periodo,
        "ambiente": AMBIENTE,
        "filas_csv": int(len(csv_df)),
        "filas_bd": int(len(db_df)),
        "filas_salida": int(len(salida)),
        "ids_sin_match": [int(i) for i in sin_match],
        "suma_salario_total": round(float(salida["salario_total"].sum()), 2),
    }
    lake.escribir(r["resumen"], json.dumps(resumen, indent=2, ensure_ascii=False).encode())
    print("> Resumen:", json.dumps(resumen, ensure_ascii=False))

    # 4.6 Correo opcional: un fallo de SMTP no rompe el pipeline de datos
    if os.getenv("SMTP_ENABLED", "false").lower() == "true":
        rep = CFG["report"]
        try:
            send_mail(rep["to"], f"{rep['subject']} [{AMBIENTE.upper()}] {periodo}",
                      rep["body_html"], f"comisiones_{periodo}.xlsx", buf_xl.getvalue())
            print(f"> Correo enviado a {rep['to']}")
        except Exception as exc:  # noqa: BLE001
            print(f"  ADVERTENCIA: no se pudo enviar el correo: {exc}")

    print("> Proceso finalizado correctamente.")
    return 0


def verificar(periodo: str) -> int:
    lake = Lake.desde_entorno(CFG.get("lake", {}))
    r = rutas(periodo)
    print(f"> Verificando {lake.describir(r['parquet'])}")
    if not lake.existe(r["parquet"]):
        print("  ERROR: no existe el Parquet de salida.")
        return 1
    df = pd.read_parquet(io.BytesIO(lake.leer(r["parquet"])))
    errores = etl.verificar_salida(df)
    if errores:
        for e in errores:
            print(f"  ERROR: {e}")
        return 1
    print(f"  OK: {len(df)} filas, salario_total cuadra, sin duplicados ni nulos.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Pipeline de comisiones")
    parser.add_argument("--periodo", default=os.getenv("PERIODO") or date.today().strftime("%Y%m"))
    parser.add_argument("--verificar", action="store_true", help="Quality gate sobre la salida")
    args = parser.parse_args()
    try:
        return verificar(args.periodo) if args.verificar else ejecutar(args.periodo)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
