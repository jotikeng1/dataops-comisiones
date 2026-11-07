"""
Transformaciones del pipeline de comisiones.
--------------------------------------------
Todas las funciones de este módulo son "puras": reciben DataFrames y
devuelven DataFrames, sin leer ni escribir archivos ni bases de datos.
Así se pueden probar con pytest en la etapa de CI sin depender de Azure
ni de PostgreSQL.
"""

import unicodedata
from datetime import datetime

import pandas as pd

# Nombres "canónicos" que el resto del pipeline espera
COLUMNAS_REQUERIDAS_CSV = ["empleado_id", "comision"]
COLUMNAS_REQUERIDAS_BD = ["empleado_id", "mnt_salario"]

# Variantes conocidas de nombres de columna en el CSV → nombre canónico
ALIAS_COLUMNAS = {
    "empleado_id": "empleado_id",
    "id_empleado": "empleado_id",
    "id empleado": "empleado_id",
    "comision": "comision",
    "nombre y apellido": "nombre_apellido_csv",
}

# Orden de columnas de la tabla consolidada
COLUMNAS_SALIDA = [
    "periodo", "empleado_id", "tip_documento", "num_documento",
    "nom_empleado", "ape_empleado", "cod_cargo", "cod_departamento",
    "mnt_salario", "comision", "salario_total", "mnt_tope_comision",
    "nombre_apellido_csv", "ambiente", "fecha_proceso",
]


def _clave(nombre: str) -> str:
    """Quita BOM, espacios, mayúsculas y tildes: ' ID Empleado' → 'id empleado'."""
    s = str(nombre).replace("\ufeff", "").strip().lower()
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def normalizar_columnas(df: pd.DataFrame) -> pd.DataFrame:
    """Lleva los encabezados del CSV a nombres estándar (tolera cambios de esquema)."""
    renombres = {}
    for col in df.columns:
        clave = _clave(col)
        renombres[col] = ALIAS_COLUMNAS.get(clave, clave.replace(" ", "_"))
    return df.rename(columns=renombres)


def validar_csv(df: pd.DataFrame) -> None:
    """Reglas de calidad del archivo de comisiones. Lanza ValueError si algo falla."""
    faltantes = [c for c in COLUMNAS_REQUERIDAS_CSV if c not in df.columns]
    if faltantes:
        raise ValueError(
            f"El CSV no tiene las columnas requeridas {faltantes}. "
            f"Columnas recibidas: {list(df.columns)}"
        )
    if df.empty:
        raise ValueError("El CSV de comisiones está vacío.")
    if df["empleado_id"].isna().any():
        raise ValueError("Hay filas sin empleado_id.")
    duplicados = df.loc[df["empleado_id"].duplicated(), "empleado_id"].tolist()
    if duplicados:
        raise ValueError(f"empleado_id duplicados en el CSV: {duplicados}")
    comision = pd.to_numeric(df["comision"], errors="coerce")
    if comision.isna().any():
        raise ValueError("Hay comisiones vacías o no numéricas.")
    if (comision < 0).any():
        raise ValueError("Hay comisiones negativas.")


def preparar_csv(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza, valida y tipa el CSV."""
    df = normalizar_columnas(df)
    validar_csv(df)
    df = df.copy()
    df["empleado_id"] = df["empleado_id"].astype(int)
    df["comision"] = pd.to_numeric(df["comision"]).astype(float)
    return df


def unir(csv_df: pd.DataFrame, db_df: pd.DataFrame):
    """
    Join interno CSV + BD por empleado_id (igual que el profe).
    Devuelve (tabla_unida, ids_del_csv_que_no_existen_en_bd).
    """
    faltantes = [c for c in COLUMNAS_REQUERIDAS_BD if c not in db_df.columns]
    if faltantes:
        raise ValueError(f"La tabla rrhh.empleado no trae las columnas {faltantes}")

    db_df = db_df.copy()
    db_df["empleado_id"] = db_df["empleado_id"].astype(int)

    unido = csv_df.merge(db_df, on="empleado_id", how="inner")
    sin_match = sorted(set(csv_df["empleado_id"]) - set(db_df["empleado_id"]))
    return unido, sin_match


def calcular_salario_total(df: pd.DataFrame) -> pd.DataFrame:
    """Regla de negocio del enunciado: salario_total = salario + comisión."""
    df = df.copy()
    for col in ["mnt_salario", "comision", "mnt_tope_comision"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(float)
    df["salario_total"] = (df["mnt_salario"] + df["comision"]).round(2)
    return df


def construir_salida(df: pd.DataFrame, periodo: str, ambiente: str) -> pd.DataFrame:
    """Añade metadatos de trazabilidad y ordena las columnas."""
    df = df.copy()
    df["periodo"] = str(periodo)
    df["ambiente"] = ambiente
    df["fecha_proceso"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    columnas = [c for c in COLUMNAS_SALIDA if c in df.columns]
    return df[columnas].sort_values("empleado_id").reset_index(drop=True)


def verificar_salida(df: pd.DataFrame) -> list:
    """Chequeos de calidad sobre el Parquet ya generado. Devuelve lista de errores."""
    errores = []
    if df.empty:
        errores.append("La tabla consolidada no tiene filas.")
        return errores
    for col in ["empleado_id", "mnt_salario", "comision", "salario_total", "periodo"]:
        if col not in df.columns:
            errores.append(f"Falta la columna {col}.")
    if errores:
        return errores
    if df["empleado_id"].duplicated().any():
        errores.append("empleado_id duplicados en la salida.")
    if df[["mnt_salario", "comision", "salario_total"]].isna().any().any():
        errores.append("Hay montos nulos en la salida.")
    esperado = (df["mnt_salario"] + df["comision"]).round(2)
    if not (esperado - df["salario_total"]).abs().lt(0.01).all():
        errores.append("salario_total no cuadra con mnt_salario + comision.")
    return errores
