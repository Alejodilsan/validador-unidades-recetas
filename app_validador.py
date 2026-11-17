import datetime

import pandas as pd
import streamlit as st
from streamlit_gsheets import GSheetsConnection

from validador.lectura import find_best_col, leer_maestro, leer_texto
from validador.registro import crear_registro, guardar_registros
from validador.reglas import (
    ERROR,
    INFO,
    causa_raiz,
    columnas_faltantes,
    construir_maestros,
    mapa_nombres_headers,
    resumen_por_codigo,
    validar_detalle,
    validar_headers,
    validar_maestro,
)
from validador.reporte import a_excel, excel_consolidado

# Configuración de la página
st.set_page_config(
    page_title="Validador Integral: Ingredientes, Extras & Recetas",
    page_icon="🍲",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================
# 1. PANEL DE REGISTRO (BARRA LATERAL)
# ==========================================
st.sidebar.title("📊 Registro de Uso")
st.sidebar.write("Por favor, ingresa los datos para habilitar el validador:")

correo = st.sidebar.text_input("Tu Correo Electrónico", placeholder="ejemplo@toteat.com")
id_toteat = st.sidebar.text_input("ID del Cliente (Toteat)", placeholder="Ej. 12345")

# Validaciones de los campos
datos_validos = True

if id_toteat:
    if not id_toteat.isdigit():
        st.sidebar.error("⚠️ El ID Toteat debe contener SOLO números (sin espacios, comas ni letras).")
        datos_validos = False

if not correo or not id_toteat:
    datos_validos = False

# Bloquear la app si los datos no están listos o son incorrectos
if not datos_validos:
    st.sidebar.warning("👈 ⚠️ Completa los datos para habilitar la herramienta.")
    st.title("🍲 Validador de Unidades: Ingredientes, Extras y Recetas")
    st.warning("⚠️ Debes completar tu correo y el ID del cliente en el panel lateral izquierdo para poder utilizar la herramienta y registrar la consulta.")
    st.stop()  # Detiene la ejecución aquí hasta que se llenen los datos

st.sidebar.success("✅ Datos registrados. ¡Puedes usar la herramienta!")
st.sidebar.divider()


# ==========================================
# 2. APLICACIÓN PRINCIPAL
# ==========================================
st.title("🍲 Validador de Unidades: Ingredientes, Extras y Recetas")
st.info(f"🕵️‍♂️ **Consultor:** {correo} | 🏢 **Cliente ID:** {id_toteat}")

st.markdown("""
Esta herramienta valida la consistencia de **Unidades de Medida** en todo tu sistema:
1. **Base de Ingredientes:** Revisa que `ub` sea estrictamente **`UN`**, **`kg`** o **`L`**, y que coincida con `conv.0.umed` y `conv.0.umedb`. Excluye inactivos (`wact = "0"`).
2. **Base de Extras:** Revisa que `ub` sea estrictamente **`UN`**, **`kg`** o **`L`**, y que coincida con `conv.0.umed` y `conv.0.umedb`. Excluye inactivos (`wact = "0"`).
3. **Detalle de Recetas (`DETALLE_RECETAS.txt`):** Revisa que los componentes usen unidades compatibles con la `Medida Base (ub)` de su maestro (`KG` ↔ `G`, `L` ↔ `ML`, `UN`).
   - Muestra el **Nombre de la Receta / Producto Padre** e identifica explícitamente ítems con **`wact = "0"`** (Stock Control OFF) como información, sin considerarlos errores.
4. **Encabezado de Recetas (`HEADERS_RECETAS.txt`):** Revisa que los rendimientos y producciones estén alineados mostrando el **Nombre de la Receta**.
""")

# Sidebar para cargar archivos
st.sidebar.header("📁 Cargar Archivos del Sistema")

file_ingr = st.sidebar.file_uploader("1. Base de Ingredientes (.xlsx, .csv)", type=["xlsx", "xls", "csv"], key="ingr")
file_extra = st.sidebar.file_uploader("2. Base de Extras (.xlsx, .csv)", type=["xlsx", "xls", "csv"], key="extra")
file_det = st.sidebar.file_uploader("3. DETALLE_RECETAS (.txt, .csv)", type=["txt", "csv", "tsv"], key="det")
file_head = st.sidebar.file_uploader("4. HEADERS_RECETAS (.txt, .csv)", type=["txt", "csv", "tsv"], key="head")


# --- Lectura con caché: los archivos solo se procesan cuando cambia su contenido ---
@st.cache_data(show_spinner=False)
def _maestro_cacheado(contenido: bytes, nombre: str):
    return leer_maestro(contenido, nombre)


@st.cache_data(show_spinner=False)
def _texto_cacheado(contenido: bytes, nombre: str):
    return leer_texto(contenido, nombre)


def cargar_maestro(uploaded_file, label_name):
    if uploaded_file is None:
        return None, None
    try:
        return _maestro_cacheado(uploaded_file.getvalue(), uploaded_file.name)
    except Exception as e:
        st.sidebar.error(f"Error al leer {label_name}: {e}")
        return None, None


def cargar_texto(uploaded_file):
    if uploaded_file is None:
        return None
    try:
        return _texto_cacheado(uploaded_file.getvalue(), uploaded_file.name)
    except Exception as e:
        st.error(str(e))
        return None


df_ingr_master, df_ingr_inactive = cargar_maestro(file_ingr, "Base de Ingredientes")
df_extra_master, df_extra_inactive = cargar_maestro(file_extra, "Base de Extras")
df_det_raw = cargar_texto(file_det)
df_head_raw = cargar_texto(file_head)

hay_maestros = df_ingr_master is not None or df_extra_master is not None
maestros = construir_maestros(df_ingr_master, df_extra_master, df_ingr_inactive, df_extra_inactive)

# Contadores de errores para las métricas
errores = {"ingr": 0, "extra": 0, "det": 0, "head": 0}
# Tablas validadas completas (para el resumen por código) y hojas del reporte consolidado
validados = {}
hojas_reporte = {}
ids_con_error_maestro = set()

tab1, tab2, tab3, tab4 = st.tabs([
    "🥗 1. Base Ingredientes",
    "➕ 2. Base Extras",
    "📋 3. DETALLE_RECETAS",
    "📜 4. HEADERS_RECETAS"
])


def mostrar_maestro(df, clave, etiqueta, etiqueta_plural, nombre_archivo, col_id, msg_cargar, msg_faltan):
    """Tabs 1 y 2: validación interna de un maestro."""
    if df is None:
        st.warning(msg_cargar)
        return
    faltan = columnas_faltantes(df)
    if faltan:
        st.error(f"{msg_faltan}: {', '.join(faltan)}")
        return

    validado = validar_maestro(df)
    err = validado[validado["Severidad"] == ERROR]
    n_err = len(err)
    errores[clave] = n_err
    validados[f"Maestro {etiqueta_plural}"] = validado
    ids_con_error_maestro.update(err["pl"])

    m1, m2, m3 = st.columns(3)
    m1.metric(f"Total {etiqueta_plural} Activos", len(validado))
    m2.metric(f"{etiqueta_plural} OK", len(validado) - n_err)
    m3.metric(f"{etiqueta_plural} CON Error", n_err, delta="-Requieren acción" if n_err > 0 else "OK", delta_color="inverse")

    if n_err > 0:
        st.error(f"¡Se encontraron {n_err} {etiqueta}(s) desalineados o con unidades no permitidas!")
        t_show = err[["pl", "np", "ub", "conv.0.umed", "conv.0.umedb", "Codigo_Error", "Detalle del Error"]].copy()
        t_show.columns = [col_id, "Nombre", "Medida Base (ub)", "Conv. a Definir (BA)", "Conv. Base (BB)", "Código Error", "¿Qué está mal?"]
        hojas_reporte[f"Errores_{nombre_archivo}"] = t_show
        st.dataframe(t_show, use_container_width=True, hide_index=True)
        st.download_button(f"📥 Descargar Reporte Errores {etiqueta_plural}",
                           a_excel(t_show, f"Errores_{nombre_archivo}"), f"Errores_{nombre_archivo}.xlsx")
    else:
        st.success(f"🎉 Todas las unidades de los {etiqueta_plural.lower()} activos son válidas y consistentes.")


# --- TAB 1: BASE INGREDIENTES ---
with tab1:
    st.header("Validación Interna del Maestro de Ingredientes (Activos)")
    mostrar_maestro(df_ingr_master, "ingr", "ingrediente", "Ingredientes", "Ingredientes", "ID Producto",
                    "⚠️ Carga el archivo **1. Base de Ingredientes** en el panel lateral.",
                    "Faltan columnas necesarias en el maestro")

# --- TAB 2: BASE EXTRAS ---
with tab2:
    st.header("Validación Interna del Maestro de Extras (Activos)")
    mostrar_maestro(df_extra_master, "extra", "extra", "Extras", "Extras", "ID Extra",
                    "⚠️ Carga el archivo **2. Base de Extras** en el panel lateral.",
                    "Faltan columnas necesarias en el maestro de extras")

# --- TAB 3: DETALLE RECETAS ---
with tab3:
    st.header("Validación DETALLE_RECETAS vs Maestros")
    if file_det is None:
        st.warning("⚠️ Carga el archivo **3. DETALLE_RECETAS (.txt)** en el panel lateral.")
    elif df_det_raw is not None and not hay_maestros:
        st.warning("⚠️ Carga al menos la **1. Base de Ingredientes** o la **2. Base de Extras** para habilitar el cruce.")
    elif df_det_raw is not None:
        st.subheader("Mapeo de Columnas de Recetas")
        cols_det = list(df_det_raw.columns)
        SIN_NOMBRE_DET = "(Ninguna / Buscar en Headers / Maestro)"

        c_rec, c_nom_rec, c_ing, c_um = st.columns(4)
        with c_rec:
            col_id_rec = st.selectbox("Columna ID Receta:", cols_det, index=cols_det.index(find_best_col(['receta', 'recipe', 'id_receta', 'padre', 'pl_receta', 'pl_padre'], cols_det)))
        with c_nom_rec:
            best_nom_rec = find_best_col(['nombre_receta', 'nombre_padre', 'nombre_producto', 'np_receta', 'receta_nombre', 'producto_padre', 'nombre', 'producto'], cols_det, default_none=True)
            opts_nom_rec = [SIN_NOMBRE_DET] + cols_det
            idx_nom_rec = opts_nom_rec.index(best_nom_rec) if best_nom_rec in opts_nom_rec else 0
            col_nom_rec = st.selectbox("Columna Nombre Receta (Opcional):", opts_nom_rec, index=idx_nom_rec)
        with c_ing:
            col_id_ingr = st.selectbox("Columna ID Ítem (Ingrediente/Extra):", cols_det, index=cols_det.index(find_best_col(['ingrediente', 'extra', 'pl', 'codigo', 'componente', 'item'], cols_det)))
        with c_um:
            col_um_det = st.selectbox("Columna Unidad Medida:", cols_det, index=cols_det.index(find_best_col(['unidad', 'umed', 'um', 'ub', 'medida'], cols_det)))

        df_det = validar_detalle(
            df_det_raw, col_id_rec, col_id_ingr, col_um_det, maestros,
            col_nom_rec=None if col_nom_rec == SIN_NOMBRE_DET else col_nom_rec,
            nombres_headers=mapa_nombres_headers(df_head_raw),
        )

        # Errores reales por un lado, información (inactivos) por otro
        err_det = df_det[df_det['Severidad'] == ERROR]
        info_det = df_det[df_det['Severidad'] == INFO]
        num_err_det = len(err_det)
        errores["det"] = num_err_det
        validados["DETALLE_RECETAS"] = df_det

        r1, r2, r3, r4 = st.columns(4)
        r1.metric("Total Líneas en Recetas", len(df_det))
        r2.metric("Líneas Correctas", len(df_det) - num_err_det - len(info_det))
        r3.metric("Líneas con Discrepancia", num_err_det, delta="-Requieren acción" if num_err_det > 0 else "OK", delta_color="inverse")
        r4.metric("Líneas Inactivas", len(info_det), delta="Info wact=0", delta_color="off")

        cols_to_show = [col_id_rec, 'Nombre_Receta_Padre', col_id_ingr, 'Tipo_Item', 'Nombre_Item_Maestro', col_um_det, 'Medida_Base_Maestro', 'Codigo_Error', 'Estado_Validacion']
        nombres_det = ['ID Receta', 'Nombre Receta / Producto Padre', 'ID Ítem', 'Tipo Ítem', 'Nombre Ítem (Maestro)', 'Unidad en Receta', 'Unidad Base (Maestro)', 'Código Error', 'Diagnóstico del Error']

        if num_err_det > 0:
            st.error(f"¡Se detectaron {num_err_det} línea(s) de recetas con inconsistencias (ERRORES)!")

            # --- Causa raíz: un ítem mal configurado genera errores en muchas recetas ---
            df_causa = causa_raiz(df_det, ids_con_error_maestro)
            hojas_reporte["Causa_Raiz_Detalle"] = df_causa
            st.subheader("🎯 Causa raíz: ítems que originan los errores")
            top = df_causa.head(10)["Líneas con error"].sum()
            st.caption(
                f"**{len(df_causa)}** ítem(s) explican los {num_err_det} errores. "
                f"Corregir los {min(10, len(df_causa))} primeros resuelve **{top}** línea(s) "
                f"({top / num_err_det:.0%})."
            )
            st.dataframe(df_causa, use_container_width=True, hide_index=True)

            st.subheader("📄 Detalle línea por línea")
            t_det_show = err_det[cols_to_show].copy()
            t_det_show.columns = nombres_det
            hojas_reporte["Errores_Detalle_Recetas"] = t_det_show
            st.dataframe(t_det_show, use_container_width=True, hide_index=True)
            st.download_button("📥 Descargar Reporte Errores DETALLE_RECETAS",
                               a_excel(t_det_show, 'Errores_Detalle_Recetas'), "Errores_Detalle_Recetas.xlsx")
        else:
            st.success("🎉 Todas las unidades usadas en las recetas son válidas y compatibles con la Medida Base (ub).")

        if len(info_det) > 0:
            t_info_det = info_det[cols_to_show].copy()
            t_info_det.columns = nombres_det
            hojas_reporte["Info_Inactivos_Detalle"] = t_info_det
            st.warning(f"⚠️ Nota Informativa: Hay {len(info_det)} línea(s) referenciando a ingredientes/extras inactivos (wact = 0).")
            with st.expander("Ver lista de ítems inactivos usados en recetas"):
                st.dataframe(t_info_det, use_container_width=True, hide_index=True)

# --- TAB 4: HEADERS RECETAS ---
with tab4:
    st.header("Validación HEADERS_RECETAS vs Maestros")
    if file_head is None:
        st.warning("⚠️ Carga el archivo **4. HEADERS_RECETAS (.txt)** en el panel lateral.")
    elif df_head_raw is not None and not hay_maestros:
        st.warning("⚠️ Carga al menos la **1. Base de Ingredientes** o la **2. Base de Extras** para habilitar la validación.")
    elif df_head_raw is not None:
        st.subheader("Mapeo de Columnas de Encabezados")
        cols_head = list(df_head_raw.columns)
        SIN_NOMBRE_HEAD = "(Ninguna / Buscar en Maestro)"

        ch1, ch2, ch3 = st.columns(3)
        with ch1:
            col_id_rec_h = st.selectbox("Columna ID Receta / Subreceta:", cols_head, index=cols_head.index(find_best_col(['receta', 'pl', 'id', 'codigo'], cols_head)))
        with ch2:
            best_nom_h = find_best_col(['nombre', 'np', 'descripcion', 'producto', 'receta'], [c for c in cols_head if c != col_id_rec_h], default_none=True)
            opts_nom_h = [SIN_NOMBRE_HEAD] + cols_head
            idx_nom_h = opts_nom_h.index(best_nom_h) if best_nom_h in opts_nom_h else 0
            col_nom_rec_h = st.selectbox("Columna Nombre Receta (Opcional):", opts_nom_h, index=idx_nom_h)
        with ch3:
            col_um_head = st.selectbox("Columna Unidad Medida Rendimiento:", cols_head, index=cols_head.index(find_best_col(['unidad', 'umed', 'um', 'ub', 'medida', 'rendimiento'], cols_head)))

        df_head = validar_headers(
            df_head_raw, col_id_rec_h, col_um_head, maestros,
            col_nom_rec=None if col_nom_rec_h == SIN_NOMBRE_HEAD else col_nom_rec_h,
        )

        err_head = df_head[df_head['Severidad'] == ERROR]
        info_head = df_head[df_head['Severidad'] == INFO]
        num_err_head = len(err_head)
        errores["head"] = num_err_head
        validados["HEADERS_RECETAS"] = df_head

        h1, h2, h3, h4 = st.columns(4)
        h1.metric("Total Encabezados", len(df_head))
        h2.metric("Encabezados Correctos", len(df_head) - num_err_head - len(info_head))
        h3.metric("Encabezados con Error", num_err_head, delta="-Requieren acción" if num_err_head > 0 else "OK", delta_color="inverse")
        h4.metric("Encabezados Inactivos", len(info_head), delta="Info wact=0", delta_color="off")

        cols_head_show = [col_id_rec_h, 'Nombre_Receta_Header', col_um_head, 'Codigo_Error', 'Estado_Validacion']
        nombres_head = ['ID Receta', 'Nombre Receta / Producto', 'Unidad en Header', 'Código Error', 'Diagnóstico del Error']

        if num_err_head > 0:
            st.error(f"¡Se detectaron {num_err_head} encabezado(s) de recetas con unidades inconsistentes!")
            t_head_show = err_head[cols_head_show].copy()
            t_head_show.columns = nombres_head
            hojas_reporte["Errores_Headers"] = t_head_show
            st.dataframe(t_head_show, use_container_width=True, hide_index=True)
            st.download_button("📥 Descargar Reporte Errores HEADERS_RECETAS",
                               a_excel(t_head_show, 'Errores_Headers'), "Errores_Headers_Recetas.xlsx")
        else:
            st.success("🎉 Todos los encabezados de recetas/subrecetas tienen unidades válidas.")

        if len(info_head) > 0:
            t_info_head = info_head[cols_head_show].copy()
            t_info_head.columns = nombres_head
            hojas_reporte["Info_Inactivos_Headers"] = t_info_head
            st.warning(f"⚠️ Nota Informativa: Hay {len(info_head)} encabezado(s) inactivo(s) (wact = 0).")
            with st.expander("Ver lista de encabezados inactivos"):
                st.dataframe(t_info_head, use_container_width=True, hide_index=True)


# ==========================================
# 3. GUARDADO AUTOMÁTICO DE MÉTRICAS
# ==========================================
st.divider()
st.subheader("📊 Resumen del Diagnóstico")

total_errores = sum(errores.values())

st.markdown(f"**Resumen de la validación para el Cliente ID:** `{id_toteat}`")
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Errores Ingredientes", errores["ingr"])
c2.metric("Errores Extras", errores["extra"])
c3.metric("Errores Detalles Receta", errores["det"])
c4.metric("Errores Headers Receta", errores["head"])
c5.metric("TOTAL ERRORES REALES", total_errores)

# --- Resumen por tipo de error + reporte consolidado ---
df_por_codigo = resumen_por_codigo(validados)
if not df_por_codigo.empty:
    st.markdown("**Errores e información por tipo:**")
    st.dataframe(df_por_codigo, use_container_width=True, hide_index=True)

if validados:
    ahora = datetime.datetime.now()
    df_resumen = pd.DataFrame([
        ("Cliente ID", id_toteat),
        ("Consultor", correo),
        ("Fecha", ahora.strftime("%Y-%m-%d %H:%M:%S")),
        ("Errores Ingredientes", errores["ingr"]),
        ("Errores Extras", errores["extra"]),
        ("Errores Detalles Receta", errores["det"]),
        ("Errores Headers Receta", errores["head"]),
        ("TOTAL ERRORES REALES", total_errores),
    ], columns=["Concepto", "Valor"]).astype({"Valor": str})
    reporte = excel_consolidado({
        "Resumen": df_resumen,
        "Errores_por_Tipo": df_por_codigo,
        **hojas_reporte,
    })
    st.download_button(
        "📥 Descargar Reporte Consolidado (todas las hojas)",
        reporte,
        f"Reporte_Validacion_{id_toteat}_{ahora:%Y%m%d}.xlsx",
        type="primary",
    )

# --- LÓGICA DE GUARDADO AUTOMÁTICO ---
archivos = [file_ingr, file_extra, file_det, file_head]

if any(f is not None for f in archivos):
    estado_actual = "_".join([id_toteat, str(total_errores)] + [f.name if f else '' for f in archivos])

    if 'ultimo_estado_guardado' not in st.session_state:
        st.session_state.ultimo_estado_guardado = ""

    if st.session_state.ultimo_estado_guardado != estado_actual:
        with st.spinner("Registrando consulta automáticamente..."):
            try:
                conn = st.connection("gsheets", type=GSheetsConnection)
                guardar_registros(conn, [crear_registro(correo, id_toteat, errores)])
                st.session_state.ultimo_estado_guardado = estado_actual
            except Exception as e:
                st.error(f"❌ Error al guardar en Sheets: {repr(e)}")
                st.info("💡 Revisa que la pestaña se llame 'Registro' y que el correo tenga acceso de Editor.")

        if st.session_state.ultimo_estado_guardado == estado_actual:
            st.success("✅ Diagnóstico registrado automáticamente en las métricas.")
else:
    st.info("Sube al menos un archivo para iniciar la validación y registrar el diagnóstico.")
