"""
Pruebas automáticas del pipeline (etapa CI en Jenkins).
No usan Azure ni PostgreSQL: la BD se simula con un DataFrame.
"""
import io
from pathlib import Path

import pandas as pd
import pytest

import etl

DATA = Path(__file__).resolve().parent / "data"
CSV_REAL = next(Path(__file__).resolve().parents[1].glob("data/ComisionEmpleados_V1_*.csv"), None)


@pytest.fixture
def bd_simulada():
    return pd.DataFrame({
        "empleado_id": [1, 2, 3],
        "nom_empleado": ["Ana", "Carlos", "Sofía"],
        "mnt_salario": [1800.0, 2500.5, 2200.75],
        "mnt_tope_comision": [0, 300, 0],
    })


def test_normaliza_encabezados_estandar():
    df = pd.DataFrame(columns=["empleado_id", "Nombre y Apellido", "Comisión"])
    assert list(etl.normalizar_columnas(df).columns) == ["empleado_id", "nombre_apellido_csv", "comision"]


def test_tolera_esquema_alterado_con_bom():
    # Archivo entregado con encabezado "ID Empleado" y BOM UTF-8
    raw = pd.read_csv(DATA / "ComisionEmpleados_esquema_alterado.csv", sep=";", encoding="utf-8")
    assert "empleado_id" not in raw.columns          # el join del código original fallaría
    df = etl.preparar_csv(raw)
    assert "empleado_id" in df.columns and len(df) > 0


def test_rechaza_csv_sin_columna_comision():
    df = pd.DataFrame({"empleado_id": [1], "otra": [5]})
    with pytest.raises(ValueError, match="columnas requeridas"):
        etl.preparar_csv(df)


def test_rechaza_ids_duplicados():
    df = pd.DataFrame({"empleado_id": [1, 1], "Comisión": [10, 20]})
    with pytest.raises(ValueError, match="duplicados"):
        etl.preparar_csv(df)


def test_rechaza_comision_negativa_o_texto():
    with pytest.raises(ValueError):
        etl.preparar_csv(pd.DataFrame({"empleado_id": [1], "Comisión": [-5]}))
    with pytest.raises(ValueError):
        etl.preparar_csv(pd.DataFrame({"empleado_id": [1], "Comisión": ["abc"]}))


def test_join_por_empleado_id_y_reporta_faltantes(bd_simulada):
    csv = etl.preparar_csv(pd.DataFrame({"empleado_id": [1, 2, 99], "Comisión": [100, 200, 300]}))
    unido, sin_match = etl.unir(csv, bd_simulada)
    assert sorted(unido["empleado_id"]) == [1, 2]
    assert sin_match == [99]


def test_salario_total_es_salario_mas_comision(bd_simulada):
    csv = etl.preparar_csv(pd.DataFrame({"empleado_id": [2], "Comisión": [8250]}))
    unido, _ = etl.unir(csv, bd_simulada)
    salida = etl.calcular_salario_total(unido)
    assert salida.loc[0, "salario_total"] == pytest.approx(2500.5 + 8250)


def test_salida_consolidada_y_parquet(bd_simulada):
    csv = etl.preparar_csv(pd.DataFrame({"empleado_id": [1, 2, 3], "Comisión": [9000, 8250, 10500]}))
    unido, _ = etl.unir(csv, bd_simulada)
    salida = etl.construir_salida(etl.calcular_salario_total(unido), "202610", "dev")
    assert set(salida["periodo"]) == {"202610"}
    # Ida y vuelta en Parquet sin pérdida
    buf = io.BytesIO()
    salida.to_parquet(buf, index=False)
    leido = pd.read_parquet(io.BytesIO(buf.getvalue()))
    assert etl.verificar_salida(leido) == []


def test_quality_gate_detecta_error():
    malo = pd.DataFrame({"periodo": ["202610"], "empleado_id": [1], "mnt_salario": [100.0],
                         "comision": [50.0], "salario_total": [999.0]})
    assert any("no cuadra" in e for e in etl.verificar_salida(malo))


@pytest.mark.skipif(CSV_REAL is None, reason="sin CSV en data/")
def test_csv_real_del_periodo_es_valido():
    df = etl.preparar_csv(pd.read_csv(CSV_REAL, sep=";", encoding="utf-8-sig"))
    assert len(df) > 0
