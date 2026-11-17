"""Reglas de validación de unidades para maestros y recetas.

Cada fila validada lleva tres columnas estructuradas:
- Severidad:     OK / ERROR / INFO   (INFO = stock control off, no cuenta como error)
- Codigo_Error:  código estable para filtrar y agrupar (ver CODIGOS)
- Mensaje legible (columna 'Detalle del Error' en maestros, 'Estado_Validacion' en recetas)
"""
from dataclasses import dataclass

import pandas as pd

from .lectura import clean_unit, normalizar_id

# Unidades permitidas como Medida Base (ub) en los maestros
VALID_UB_MASTERS = ["UN", "KG", "L"]

# Unidades de receta aceptadas para cada Medida Base del maestro
ALLOWED_UNITS = {
    "KG": ["KG", "G", "GR", "GRAMO", "GRAMOS", "KILOGRAMO", "KILOGRAMOS",
           "OZ", "ONZA", "ONZAS"],
    "L": ["L", "ML", "MILILITRO", "MILILITROS", "LITRO", "LITROS",
          "FL OZ", "FLOZ", "FL. OZ", "FL.OZ", "ONZA FLUIDA", "ONZAS FLUIDAS",
          "CC", "C.C.", "CM3"],
    "UN": ["UN", "UND", "UNIDAD", "UNIDADES"],
    # Nota: estas tres no pasan la validación de maestros (VALID_UB_MASTERS),
    # solo aplican al cruce de recetas. Pendiente de decidir si se mantienen.
    "PK": ["PK", "PAQUETE", "PAQUETES"],
    "BOX": ["BOX", "CAJA", "CAJAS"],
    "TARRO": ["TARRO", "TARROS"],
}

COLUMNAS_MAESTRO = ["pl", "np", "ub", "conv.0.umed", "conv.0.umedb"]

OK, ERROR, INFO = "OK", "ERROR", "INFO"

CODIGOS = {
    "UB_INVALIDA": "Medida Base del maestro no es UN, KG o L",
    "UB_DISTINTA_CONV_DEFINIR": "Medida Base ≠ Conv. a Definir (conv.0.umed)",
    "UB_DISTINTA_CONV_BASE": "Medida Base ≠ Conv. Base (conv.0.umedb)",
    "CONV_DISTINTAS": "Conv. a Definir ≠ Conv. Base",
    "UNIDAD_INCOMPATIBLE": "Unidad en receta/header no compatible con la Medida Base del maestro",
    "ITEM_INEXISTENTE": "Ítem de receta no existe en ningún maestro",
    "ITEM_INACTIVO": "Ítem con stock control off (wact = 0)",
    "RECETA_INACTIVA": "Receta/subreceta con stock control off (wact = 0)",
}

_PARES_COMPATIBLES = {(ub, um) for ub, ums in ALLOWED_UNITS.items() for um in ums}


def is_unit_compatible(ub_master, um_recipe) -> bool:
    ub, um = clean_unit(ub_master), clean_unit(um_recipe)
    return ub == um or (ub, um) in _PARES_COMPATIBLES


# ------------------------------------------------------------------
# Maestros (Ingredientes / Extras)
# ------------------------------------------------------------------
def columnas_faltantes(df: pd.DataFrame) -> list:
    return [c for c in COLUMNAS_MAESTRO if c not in df.columns]


def _errores_maestro(ub, c1, c2) -> list:
    """-> lista de (codigo, mensaje)"""
    errs = []
    if ub not in VALID_UB_MASTERS:
        errs.append(("UB_INVALIDA", f"Medida Base ('{ub}') es inválida (solo se permite 'UN', 'kg' o 'L')"))
    if ub != c1:
        errs.append(("UB_DISTINTA_CONV_DEFINIR", f"Medida Base ('{ub}') ≠ Conv. a Definir ('{c1}')"))
    if ub != c2:
        errs.append(("UB_DISTINTA_CONV_BASE", f"Medida Base ('{ub}') ≠ Conv. Base ('{c2}')"))
    if c1 != c2 and ub == c1:
        errs.append(("CONV_DISTINTAS", f"Conv. a Definir ('{c1}') ≠ Conv. Base ('{c2}')"))
    return errs


def validar_maestro(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega Severidad, Codigo_Error y 'Detalle del Error' ('' si la fila está OK)."""
    out = df.copy()
    ub = out["ub"].map(clean_unit)
    c1 = out["conv.0.umed"].map(clean_unit)
    c2 = out["conv.0.umedb"].map(clean_unit)
    res = [_errores_maestro(*t) for t in zip(ub, c1, c2)]
    out["Severidad"] = [ERROR if r else OK for r in res]
    out["Codigo_Error"] = [" | ".join(c for c, _ in r) for r in res]
    out["Detalle del Error"] = [" | ".join(m for _, m in r) for r in res]
    return out


# ------------------------------------------------------------------
# Índices de maestros para el cruce con recetas
# ------------------------------------------------------------------
@dataclass
class Maestros:
    """Diccionarios pl -> (np, ub_limpia) para cada maestro."""
    ingr: dict
    extra: dict
    ingr_inact: dict
    extra_inact: dict

    def nombre(self, pl):
        for mapa in (self.ingr, self.extra, self.ingr_inact, self.extra_inact):
            if pl in mapa:
                return mapa[pl][0]
        return None


def _indexar(df) -> dict:
    if df is None or df.empty or "pl" not in df.columns:
        return {}
    d = df.reindex(columns=["pl", "np", "ub"])
    # En caso de IDs duplicados prevalece la última fila (igual que antes)
    return {pl: (np_, clean_unit(ub)) for pl, np_, ub in zip(d["pl"], d["np"], d["ub"])}


def construir_maestros(ingr, extra, ingr_inact, extra_inact) -> Maestros:
    return Maestros(_indexar(ingr), _indexar(extra), _indexar(ingr_inact), _indexar(extra_inact))


def _texto(val):
    """Texto limpio o None si está vacío."""
    if val is None or (not isinstance(val, str) and pd.isna(val)):
        return None
    s = str(val).strip()
    return s or None


def mapa_nombres_headers(df_head: pd.DataFrame) -> dict:
    """ID receta -> nombre, detectando las columnas automáticamente en HEADERS_RECETAS."""
    from .lectura import find_best_col

    if df_head is None or df_head.empty:
        return {}
    cols = list(df_head.columns)
    c_id = find_best_col(["receta", "pl", "id", "codigo"], cols)
    c_nom = find_best_col(["nombre", "np", "descripcion", "producto", "receta"],
                          [c for c in cols if c != c_id], default_none=True)
    if not c_id or c_nom == "(Ninguna)":
        return {}
    mapa = {}
    for rid, nom in zip(df_head[c_id], df_head[c_nom]):
        nom = _texto(nom)
        if nom:
            mapa[normalizar_id(rid)] = nom
    return mapa


# ------------------------------------------------------------------
# DETALLE_RECETAS
# ------------------------------------------------------------------
def _estado_detalle(item, um, m: Maestros):
    """-> (Estado_Validacion, Tipo_Item, Nombre_Item_Maestro, Medida_Base_Maestro, Severidad, Codigo_Error)"""
    if item in m.ingr:
        np_, ub = m.ingr[item]
        if not is_unit_compatible(ub, um):
            return (f"ERROR: Unidad en Receta ('{um}') no es compatible con Medida Base Ingrediente ('{ub}')",
                    "Ingrediente", np_, ub, ERROR, "UNIDAD_INCOMPATIBLE")
        return "OK", "Ingrediente", np_, ub, OK, ""
    if item in m.extra:
        np_, ub = m.extra[item]
        if not is_unit_compatible(ub, um):
            return (f"ERROR: Unidad en Receta ('{um}') no es compatible con Medida Base Extra ('{ub}')",
                    "Extra", np_, ub, ERROR, "UNIDAD_INCOMPATIBLE")
        return "OK", "Extra", np_, ub, OK, ""
    if item in m.ingr_inact:
        np_, ub = m.ingr_inact[item]
        return ("INFO: Ítem con stock control off (wact = 0)", "Stock Control OFF (Ingrediente)",
                np_, ub, INFO, "ITEM_INACTIVO")
    if item in m.extra_inact:
        np_, ub = m.extra_inact[item]
        return ("INFO: Ítem con stock control off (wact = 0)", "Stock Control OFF (Extra)",
                np_, ub, INFO, "ITEM_INACTIVO")
    return ("ERROR: El ítem no existe ni en Maestro de Ingredientes ni en Extras", "Desconocido",
            "DESCONOCIDO", "N/A", ERROR, "ITEM_INEXISTENTE")


def validar_detalle(df_raw: pd.DataFrame, col_id_rec, col_id_item, col_um,
                    m: Maestros, col_nom_rec=None, nombres_headers=None) -> pd.DataFrame:
    """Cruza cada línea de receta con los maestros.

    Prioridad del nombre de receta: columna mapeada -> HEADERS -> maestros -> 'NO ESPECIFICADO'.
    Agrega además las columnas normalizadas id_rec_clean / id_item_clean / um_clean.
    """
    nombres_headers = nombres_headers or {}
    df = df_raw.copy()
    df["id_rec_clean"] = df[col_id_rec].map(normalizar_id)
    df["id_item_clean"] = df[col_id_item].map(normalizar_id)
    df["um_clean"] = df[col_um].map(clean_unit)
    nombres_col = df[col_nom_rec] if col_nom_rec else [None] * len(df)

    df["Nombre_Receta_Padre"] = [
        _texto(nom) or nombres_headers.get(rid) or _texto(m.nombre(rid)) or "NO ESPECIFICADO"
        for rid, nom in zip(df["id_rec_clean"], nombres_col)
    ]

    res = [_estado_detalle(i, u, m) for i, u in zip(df["id_item_clean"], df["um_clean"])]
    for k, col in enumerate(["Estado_Validacion", "Tipo_Item", "Nombre_Item_Maestro",
                             "Medida_Base_Maestro", "Severidad", "Codigo_Error"]):
        df[col] = [r[k] for r in res]
    return df


COLUMNAS_CAUSA_RAIZ = [
    "ID Ítem", "Nombre Ítem", "Tipo Ítem", "Medida Base (Maestro)", "Código Error",
    "Unidades usadas en recetas", "Líneas con error", "Líneas totales del ítem",
    "Recetas afectadas", "¿Error también en maestro?", "Acción sugerida",
]


def _accion_sugerida(codigo, err_maestro, lineas_err, lineas_tot):
    if codigo == "ITEM_INEXISTENTE":
        return "Crear el ítem en el maestro o corregir el ID en las recetas"
    if err_maestro:
        return "Corregir primero la Medida Base / conversiones en el maestro"
    if lineas_err == lineas_tot and lineas_tot > 1:
        return "Probable error en el maestro: ninguna receta usa una unidad compatible"
    return "Corregir la unidad en las recetas afectadas"


def causa_raiz(df_det: pd.DataFrame, ids_con_error_maestro=frozenset()) -> pd.DataFrame:
    """Agrupa los errores de DETALLE por ítem para priorizar qué corregir.

    Un solo ítem mal configurado suele generar errores en muchas recetas; esta tabla
    los muestra una vez, ordenados por cantidad de líneas afectadas.
    """
    err = df_det[df_det["Severidad"] == ERROR]
    if err.empty:
        return pd.DataFrame(columns=COLUMNAS_CAUSA_RAIZ)

    lineas_totales = df_det.groupby("id_item_clean").size()
    g = err.groupby("id_item_clean", sort=False).agg(
        nombre=("Nombre_Item_Maestro", "first"),
        tipo=("Tipo_Item", "first"),
        ub=("Medida_Base_Maestro", "first"),
        codigo=("Codigo_Error", "first"),
        unidades=("um_clean", lambda s: ", ".join(sorted(set(u or "(vacía)" for u in s)))),
        lineas=("Severidad", "size"),
        recetas=("id_rec_clean", "nunique"),
    ).reset_index()

    g["tot"] = g["id_item_clean"].map(lineas_totales)
    g["err_maestro"] = g["id_item_clean"].isin(set(ids_con_error_maestro))
    g["accion"] = [_accion_sugerida(c, e, l, t)
                   for c, e, l, t in zip(g["codigo"], g["err_maestro"], g["lineas"], g["tot"])]
    g["err_maestro"] = g["err_maestro"].map({True: "Sí", False: "No"})
    g = g.sort_values(["lineas", "recetas"], ascending=False)

    out = g[["id_item_clean", "nombre", "tipo", "ub", "codigo", "unidades", "lineas", "tot",
             "recetas", "err_maestro", "accion"]]
    out.columns = COLUMNAS_CAUSA_RAIZ
    return out.reset_index(drop=True)


# ------------------------------------------------------------------
# HEADERS_RECETAS
# ------------------------------------------------------------------
def _estado_header(rid, um, m: Maestros):
    """-> (Estado_Validacion, Severidad, Codigo_Error)"""
    if rid in m.ingr:
        ub = m.ingr[rid][1]
        if not is_unit_compatible(ub, um):
            return (f"ERROR: Unidad Header ('{um}') no es compatible con Medida Base Ingrediente ('{ub}')",
                    ERROR, "UNIDAD_INCOMPATIBLE")
        return "OK (Coincide con Maestro de Ingrediente/Subreceta)", OK, ""
    if rid in m.extra:
        ub = m.extra[rid][1]
        if not is_unit_compatible(ub, um):
            return (f"ERROR: Unidad Header ('{um}') no es compatible con Medida Base Extra ('{ub}')",
                    ERROR, "UNIDAD_INCOMPATIBLE")
        return "OK (Coincide con Maestro de Extra)", OK, ""
    if rid in m.ingr_inact or rid in m.extra_inact:
        return "INFO: Receta/Subreceta con stock control off (wact = 0)", INFO, "RECETA_INACTIVA"
    return "OK (Receta Final)", OK, ""


def validar_headers(df_raw: pd.DataFrame, col_id_rec, col_um, m: Maestros, col_nom_rec=None) -> pd.DataFrame:
    df = df_raw.copy()
    df["id_rec_clean"] = df[col_id_rec].map(normalizar_id)
    df["um_clean"] = df[col_um].map(clean_unit)
    nombres_col = df[col_nom_rec] if col_nom_rec else [None] * len(df)

    df["Nombre_Receta_Header"] = [
        _texto(nom) or _texto(m.nombre(rid)) or "NO ESPECIFICADO"
        for rid, nom in zip(df["id_rec_clean"], nombres_col)
    ]
    res = [_estado_header(r, u, m) for r, u in zip(df["id_rec_clean"], df["um_clean"])]
    df["Estado_Validacion"] = [r[0] for r in res]
    df["Severidad"] = [r[1] for r in res]
    df["Codigo_Error"] = [r[2] for r in res]
    return df


def resumen_por_codigo(tablas: dict) -> pd.DataFrame:
    """Cuenta filas por (Archivo, Severidad, Codigo_Error) sobre tablas ya validadas.

    En maestros una fila puede tener varios códigos; se cuenta cada código por separado.
    """
    filas = []
    for archivo, df in tablas.items():
        if df is None or df.empty or "Codigo_Error" not in df.columns:
            continue
        sub = df[df["Severidad"] != OK]
        for sev, codigos in zip(sub["Severidad"], sub["Codigo_Error"]):
            for cod in str(codigos).split(" | "):
                filas.append((archivo, sev, cod))
    if not filas:
        return pd.DataFrame(columns=["Archivo", "Severidad", "Código", "Descripción", "Cantidad"])
    r = pd.DataFrame(filas, columns=["Archivo", "Severidad", "Código"])
    r = r.groupby(["Archivo", "Severidad", "Código"], sort=False).size().reset_index(name="Cantidad")
    r.insert(3, "Descripción", r["Código"].map(CODIGOS))
    return r
