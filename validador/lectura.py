"""Lectura y normalización de archivos exportados desde Toteat."""
import io
import re

import pandas as pd

VALORES_NULOS = {"", "NAN", "NONE", "NULL", "NAT", "<NA>"}
SEPARADORES = ["\t", ";", "|", ","]
_ENTERO_CON_DECIMAL = re.compile(r"^-?\d+\.0+$")


def normalizar_id(val) -> str:
    """Convierte un ID a texto comparable: '12345.0' -> '12345', ' 0123 ' -> '0123'."""
    if val is None or (not isinstance(val, str) and pd.isna(val)):
        return ""
    s = str(val).strip()
    if s.upper() in VALORES_NULOS:
        return ""
    if _ENTERO_CON_DECIMAL.match(s):
        s = s.split(".")[0]
    return s


def clean_unit(val) -> str:
    """Unidad en mayúsculas, sin espacios extremos y con espacios internos colapsados."""
    if val is None or (not isinstance(val, str) and pd.isna(val)):
        return ""
    s = " ".join(str(val).split()).upper()
    return "" if s in VALORES_NULOS else s


def _decodificar(contenido: bytes) -> str:
    try:
        return contenido.decode("utf-8-sig")
    except UnicodeDecodeError:
        return contenido.decode("latin-1", errors="ignore")


def _leer_csv_texto(texto: str, header="infer") -> pd.DataFrame:
    """Prueba separadores comunes; todo se lee como texto para no alterar IDs."""
    for sep in SEPARADORES:
        try:
            df = pd.read_csv(io.StringIO(texto), sep=sep, dtype=str, header=header)
            if len(df.columns) > 1:
                return df
        except Exception:
            pass
    return pd.read_csv(io.StringIO(texto), sep=None, engine="python", dtype=str, header=header)


def leer_texto(contenido: bytes, nombre: str) -> pd.DataFrame:
    """Lee DETALLE_RECETAS / HEADERS_RECETAS (.txt/.csv/.tsv)."""
    try:
        return _leer_csv_texto(_decodificar(contenido))
    except Exception as e:
        raise ValueError(f"Error al leer {nombre}: {e}") from e


def leer_maestro(contenido: bytes, nombre: str):
    """Lee un maestro (Ingredientes o Extras) en .xlsx/.xls/.csv.

    Detecta la fila de cabecera (la que contiene 'pl' o 'ub' dentro de las 10
    primeras), descarta filas vacías o de etiquetas y separa los ítems inactivos
    (wact = 0 / FALSE / FALSO).

    Devuelve (activos, inactivos).
    """
    if nombre.lower().endswith(".csv"):
        crudo = _leer_csv_texto(_decodificar(contenido), header=None)
    else:
        crudo = pd.read_excel(io.BytesIO(contenido), header=None, dtype=str)

    fila_cabecera = 0
    for i, fila in crudo.head(10).iterrows():
        valores = [str(v).strip() for v in fila.values]
        if "pl" in valores or "ub" in valores:
            fila_cabecera = i
            break

    df = crudo.iloc[fila_cabecera + 1:].copy()
    df.columns = [str(c).strip() for c in crudo.iloc[fila_cabecera].values]
    df = df.reset_index(drop=True)

    if "pl" not in df.columns:
        raise ValueError(f"{nombre}: no se encontró la columna 'pl'")

    df["pl"] = df["pl"].map(normalizar_id)
    df = df[
        (df["pl"] != "")
        & (~df["pl"].str.contains("ID Producto", case=False, na=False))
        & (df["pl"] != "pl")
    ].copy()

    col_wact = next((c for c in df.columns if c.lower() == "wact"), None)
    if col_wact is None:
        return df, pd.DataFrame(columns=df.columns)

    wact = df[col_wact].astype(str).str.strip().str.upper()
    inactivo = wact.isin(["0", "0.0", "FALSO", "FALSE"])
    return df[~inactivo].copy(), df[inactivo].copy()


def find_best_col(opciones, columnas, default_none=False):
    """Primera columna cuyo nombre contiene alguna de las opciones (en orden de prioridad)."""
    for opt in opciones:
        for c in columnas:
            if opt.lower() in str(c).lower():
                return c
    return "(Ninguna)" if default_none else (columnas[0] if columnas else "")
