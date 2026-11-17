"""Generación de reportes descargables."""
import io

import pandas as pd
from openpyxl.utils import get_column_letter


def _formatear_hoja(ws, df: pd.DataFrame) -> None:
    ws.freeze_panes = "A2"
    if len(df.columns):
        ws.auto_filter.ref = ws.dimensions
    for i, col in enumerate(df.columns, start=1):
        muestra = df[col].astype(str).head(500)
        largo = max([len(str(col))] + [len(v) for v in muestra]) if len(muestra) else len(str(col))
        ws.column_dimensions[get_column_letter(i)].width = min(max(largo + 2, 10), 60)


def a_excel(df: pd.DataFrame, hoja: str) -> bytes:
    return excel_consolidado({hoja: df})


def excel_consolidado(hojas: dict) -> bytes:
    """Un único .xlsx con una hoja por entrada {nombre_hoja: DataFrame}.

    Las hojas vacías o None se omiten (salvo que todas lo sean).
    """
    validas = {k: v for k, v in hojas.items() if v is not None and not v.empty} or \
              {k: v for k, v in hojas.items() if v is not None} or \
              {"Sin datos": pd.DataFrame({"Mensaje": ["No hay datos para exportar"]})}
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        for nombre, df in validas.items():
            hoja = nombre[:31]
            df.to_excel(w, index=False, sheet_name=hoja)
            _formatear_hoja(w.sheets[hoja], df)
    return out.getvalue()
