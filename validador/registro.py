"""Registro de consultas en Google Sheets (hoja 'Registro')."""
import datetime

import pandas as pd

HOJA_REGISTRO = "Registro"


def crear_registro(correo, id_cliente, errores: dict) -> dict:
    return {
        "Fecha": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Correo_Consultor": correo,
        "ID_Cliente": id_cliente,
        "Err_Ingredientes": errores["ingr"],
        "Err_Extras": errores["extra"],
        "Err_Detalles": errores["det"],
        "Err_Headers": errores["head"],
        "Total_Errores": sum(errores.values()),
    }


def guardar_registros(conn, registros: list) -> None:
    """Agrega filas a la hoja de registro (lee la hoja y la reescribe completa)."""
    try:
        existente = conn.read(worksheet=HOJA_REGISTRO)
    except Exception:
        existente = pd.DataFrame()
    nuevo = pd.DataFrame(registros)
    actualizado = pd.concat([existente, nuevo], ignore_index=True) if not existente.empty else nuevo
    conn.update(worksheet=HOJA_REGISTRO, data=actualizado)
