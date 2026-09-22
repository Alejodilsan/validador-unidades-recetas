import streamlit as st
import pandas as pd
import io

# Configuración de la página
st.set_page_config(
    page_title="Validador Integral: Ingredientes, Extras & Recetas", 
    page_icon="🍲", 
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🍲 Validador de Unidades: Ingredientes, Extras y Recetas")
st.markdown("""
Esta herramienta valida la consistencia de **Unidades de Medida** en todo tu sistema:
1. **Base de Ingredientes:** Revisa que `ub` sea estrictamente **`UN`**, **`kg`** o **`L`**, y que coincida con `conv.0.umed` y `conv.0.umedb`. Excluye inactivos (`wact = "0"`).
2. **Base de Extras:** Revisa que `ub` sea estrictamente **`UN`**, **`kg`** o **`L`**, y que coincida con `conv.0.umed` y `conv.0.umedb`. Excluye inactivos (`wact = "0"`).
3. **Detalle de Recetas (`DETALLE_RECETAS.txt`):** Revisa que los componentes usen unidades compatibles con la `Medida Base (ub)` de su maestro (`KG` ↔ `G`, `L` ↔ `ML`, `UN`).
   - Muestra el **Nombre de la Receta / Producto Padre** e identifica explícitamente ítems con **`wact = "0"`** (Stock Control OFF).
4. **Encabezado de Recetas (`HEADERS_RECETAS.txt`):** Revisa que los rendimientos y producciones estén alineados mostrando el **Nombre de la Receta**.
""")

# Sidebar para cargar archivos
st.sidebar.header("📁 Cargar Archivos del Sistema")

file_ingr = st.sidebar.file_uploader(
    "1. Base de Ingredientes (.xlsx, .csv)", 
    type=["xlsx", "xls", "csv"],
    key="ingr"
)

file_extra = st.sidebar.file_uploader(
    "2. Base de Extras (.xlsx, .csv)", 
    type=["xlsx", "xls", "csv"],
    key="extra"
)

file_det = st.sidebar.file_uploader(
    "3. DETALLE_RECETAS (.txt, .csv)", 
    type=["txt", "csv", "tsv"],
    key="det"
)

file_head = st.sidebar.file_uploader(
    "4. HEADERS_RECETAS (.txt, .csv)", 
    type=["txt", "csv", "tsv"],
    key="head"
)

def read_text_file(uploaded_file):
    if uploaded_file is None:
        return None
    content = uploaded_file.getvalue()
    try:
        text_str = content.decode('utf-8')
    except UnicodeDecodeError:
        text_str = content.decode('latin-1', errors='ignore')
        
    for sep in ['\t', ';', '|', ',']:
        try:
            df = pd.read_csv(io.StringIO(text_str), sep=sep)
            if len(df.columns) > 1:
                return df
        except Exception:
            pass
    try:
        return pd.read_csv(io.StringIO(text_str), sep=None, engine='python')
    except Exception as e:
        st.error(f"Error al leer {uploaded_file.name}: {e}")
        return None

def clean_unit(val):
    if pd.isna(val) or val is None:
        return ""
    val_str = str(val).strip().upper()
    if val_str in ['NAN', 'NONE', 'NULL']:
        return ""
    return val_str

# Reglas de unidades válidas para Medida Base (ub)
VALID_UB_MASTERS = ['UN', 'KG', 'L']

# Reglas de compatibilidad de unidades para recetas
ALLOWED_UNITS = {
    'KG': ['KG', 'G', 'GR', 'GRAMO', 'GRAMOS', 'KILOGRAMO', 'KILOGRAMOS'],
    'L': ['L', 'ML', 'MILILITRO', 'MILILITROS', 'LITRO', 'LITROS'],
    'UN': ['UN', 'UND', 'UNIDAD', 'UNIDADES'],
    'PK': ['PK', 'PAQUETE', 'PAQUETES'],
    'BOX': ['BOX', 'CAJA', 'CAJAS'],
    'TARRO': ['TARRO', 'TARROS']
}

def is_unit_compatible(ub_master, um_recipe):
    ub_m = clean_unit(ub_master)
    um_r = clean_unit(um_recipe)
    
    if ub_m == um_r:
        return True
        
    if ub_m in ALLOWED_UNITS and um_r in ALLOWED_UNITS[ub_m]:
        return True
        
    return False

def process_master_file(uploaded_file, label_name):
    if uploaded_file is None:
        return None, None
    try:
        if uploaded_file.name.endswith('.csv'):
            df_raw = pd.read_csv(uploaded_file)
        else:
            df_raw_tmp = pd.read_excel(uploaded_file, header=None)
            header_idx = 0
            for i, row in df_raw_tmp.head(10).iterrows():
                vals = [str(v).strip() for v in row.values]
                if 'pl' in vals or 'ub' in vals:
                    header_idx = i
                    break
            df_raw = pd.read_excel(uploaded_file, header=header_idx)
            
        df_master = df_raw[
            df_raw['pl'].notna() & 
            (df_raw['pl'].astype(str).str.strip() != '') &
            (~df_raw['pl'].astype(str).str.contains('ID Producto', case=False, na=False)) &
            (df_raw['pl'].astype(str).str.strip() != 'pl')
        ].copy()
        
        # Limpiar espacios en nombres de columnas
        df_master.columns = [str(c).strip() for c in df_master.columns]
        df_master['pl'] = df_master['pl'].astype(str).str.strip()
        
        # Identificar e separar ítems inactivos (donde la columna 'wact' es 0, FALSO o FALSE)
        wact_col = next((c for c in df_master.columns if c.lower() == 'wact'), None)
        df_inactive = pd.DataFrame()
        if wact_col:
            wact_clean = df_master[wact_col].astype(str).str.strip().str.upper()
            inactive_mask = wact_clean.isin(['0', '0.0', 'FALSO', 'FALSE'])
            df_inactive = df_master[inactive_mask].copy()
            df_master = df_master[~inactive_mask].copy()
            
        return df_master, df_inactive
    except Exception as e:
        st.sidebar.error(f"Error al leer {label_name}: {e}")
        return None, None

df_ingr_master, df_ingr_inactive = process_master_file(file_ingr, "Base de Ingredientes")
df_extra_master, df_extra_inactive = process_master_file(file_extra, "Base de Extras")

tab1, tab2, tab3, tab4 = st.tabs([
    "🥗 1. Base Ingredientes", 
    "➕ 2. Base Extras",
    "📋 3. DETALLE_RECETAS", 
    "📜 4. HEADERS_RECETAS"
])

# --- TAB 1: BASE INGREDIENTES ---
with tab1:
    st.header("Validación Interna del Maestro de Ingredientes (Activos)")
    if df_ingr_master is not None:
        required_cols = ['pl', 'np', 'ub', 'conv.0.umed', 'conv.0.umedb']
        missing = [c for c in required_cols if c not in df_ingr_master.columns]
        
        if missing:
            st.error(f"Faltan columnas necesarias en el maestro: {', '.join(missing)}")
        else:
            df_clean = df_ingr_master.copy()
            df_clean['ub_clean'] = df_clean['ub'].apply(clean_unit)
            df_clean['conv1_clean'] = df_clean['conv.0.umed'].apply(clean_unit)
            df_clean['conv2_clean'] = df_clean['conv.0.umedb'].apply(clean_unit)

            def get_ingr_error(row):
                ub, c1, c2 = row['ub_clean'], row['conv1_clean'], row['conv2_clean']
                diffs = []
                if ub not in VALID_UB_MASTERS:
                    diffs.append(f"Medida Base ('{ub}') es inválida (solo se permite 'UN', 'kg' o 'L')")
                if ub != c1: 
                    diffs.append(f"Medida Base ('{ub}') ≠ Conv. a Definir ('{c1}')")
                if ub != c2: 
                    diffs.append(f"Medida Base ('{ub}') ≠ Conv. Base ('{c2}')")
                if c1 != c2 and ub == c1: 
                    diffs.append(f"Conv. a Definir ('{c1}') ≠ Conv. Base ('{c2}')")
                return " | ".join(diffs)

            df_clean['Detalle del Error'] = df_clean.apply(get_ingr_error, axis=1)
            err_ingr = df_clean[df_clean['Detalle del Error'] != ""].copy()

            m1, m2, m3 = st.columns(3)
            m1.metric("Total Ingredientes Activos", len(df_clean))
            m2.metric("Ingredientes OK", len(df_clean) - len(err_ingr))
            m3.metric("Ingredientes CON Error", len(err_ingr), delta="-Requieren acción" if len(err_ingr)>0 else "OK", delta_color="inverse")

            if len(err_ingr) > 0:
                st.error(f"¡Se encontraron {len(err_ingr)} ingrediente(s) desalineados o con unidades no permitidas!")
                t_show = err_ingr[['pl', 'np', 'ub', 'conv.0.umed', 'conv.0.umedb', 'Detalle del Error']].copy()
                t_show.columns = ['ID Producto', 'Nombre', 'Medida Base (ub)', 'Conv. a Definir (BA)', 'Conv. Base (BB)', '¿Qué está mal?']
                st.dataframe(t_show, use_container_width=True)
                
                out = io.BytesIO()
                with pd.ExcelWriter(out, engine='openpyxl') as w:
                    t_show.to_excel(w, index=False, sheet_name='Errores_Ingredientes')
                st.download_button("📥 Descargar Reporte Errores Ingredientes", out.getvalue(), "Errores_Ingredientes.xlsx")
            else:
                st.success("🎉 Todas las unidades de los ingredientes activos son válidas y consistentes.")
    else:
        st.warning("⚠️ Carga el archivo **1. Base de Ingredientes** en el panel lateral.")

# --- TAB 2: BASE EXTRAS ---
with tab2:
    st.header("Validación Interna del Maestro de Extras (Activos)")
    if df_extra_master is not None:
        required_cols = ['pl', 'np', 'ub', 'conv.0.umed', 'conv.0.umedb']
        missing = [c for c in required_cols if c not in df_extra_master.columns]
        
        if missing:
            st.error(f"Faltan columnas necesarias en el maestro de extras: {', '.join(missing)}")
        else:
            df_clean_ex = df_extra_master.copy()
            df_clean_ex['ub_clean'] = df_clean_ex['ub'].apply(clean_unit)
            df_clean_ex['conv1_clean'] = df_clean_ex['conv.0.umed'].apply(clean_unit)
            df_clean_ex['conv2_clean'] = df_clean_ex['conv.0.umedb'].apply(clean_unit)

            def get_extra_error(row):
                ub, c1, c2 = row['ub_clean'], row['conv1_clean'], row['conv2_clean']
                diffs = []
                if ub not in VALID_UB_MASTERS:
                    diffs.append(f"Medida Base ('{ub}') es inválida (solo se permite 'UN', 'kg' o 'L')")
                if ub != c1: 
                    diffs.append(f"Medida Base ('{ub}') ≠ Conv. a Definir ('{c1}')")
                if ub != c2: 
                    diffs.append(f"Medida Base ('{ub}') ≠ Conv. Base ('{c2}')")
                if c1 != c2 and ub == c1: 
                    diffs.append(f"Conv. a Definir ('{c1}') ≠ Conv. Base ('{c2}')")
                return " | ".join(diffs)

            df_clean_ex['Detalle del Error'] = df_clean_ex.apply(get_extra_error, axis=1)
            err_extra = df_clean_ex[df_clean_ex['Detalle del Error'] != ""].copy()

            e1, e2, e3 = st.columns(3)
            e1.metric("Total Extras Activos", len(df_clean_ex))
            e2.metric("Extras OK", len(df_clean_ex) - len(err_extra))
            e3.metric("Extras CON Error", len(err_extra), delta="-Requieren acción" if len(err_extra)>0 else "OK", delta_color="inverse")

            if len(err_extra) > 0:
                st.error(f"¡Se encontraron {len(err_extra)} extra(s) desalineados o con unidades no permitidas!")
                t_ex_show = err_extra[['pl', 'np', 'ub', 'conv.0.umed', 'conv.0.umedb', 'Detalle del Error']].copy()
                t_ex_show.columns = ['ID Extra', 'Nombre', 'Medida Base (ub)', 'Conv. a Definir (BA)', 'Conv. Base (BB)', '¿Qué está mal?']
                st.dataframe(t_ex_show, use_container_width=True)
                
                out_ex = io.BytesIO()
                with pd.ExcelWriter(out_ex, engine='openpyxl') as w:
                    t_ex_show.to_excel(w, index=False, sheet_name='Errores_Extras')
                st.download_button("📥 Descargar Reporte Errores Extras", out_ex.getvalue(), "Errores_Extras.xlsx")
            else:
                st.success("🎉 Todas las unidades de los extras activos son válidas y consistentes.")
    else:
        st.warning("⚠️ Carga el archivo **2. Base de Extras** en el panel lateral.")

# --- TAB 3: DETALLE RECETAS ---
with tab3:
    st.header("Validación DETALLE_RECETAS vs Maestros")
    if file_det is not None:
        df_det_raw = read_text_file(file_det)
        
        if df_det_raw is not None and (df_ingr_master is not None or df_extra_master is not None):
            st.subheader("Mapeo de Columnas de Recetas")
            cols_det = list(df_det_raw.columns)
            
            def find_best_col(options, cols, default_none=False):
                for opt in options:
                    for c in cols:
                        if opt.lower() in str(c).lower():
                            return c
                return "(Ninguna)" if default_none else (cols[0] if cols else "")

            c_rec, c_nom_rec, c_ing, c_um = st.columns(4)
            with c_rec:
                col_id_rec = st.selectbox("Columna ID Receta:", cols_det, index=cols_det.index(find_best_col(['receta', 'recipe', 'id_receta', 'padre', 'pl_receta', 'pl_padre'], cols_det)))
            with c_nom_rec:
                best_nom_rec = find_best_col(['nombre_receta', 'nombre_padre', 'nombre_producto', 'np_receta', 'receta_nombre', 'producto_padre', 'nombre', 'producto'], cols_det, default_none=True)
                opts_nom_rec = ["(Ninguna / Buscar en Headers / Maestro)"] + cols_det
                idx_nom_rec = opts_nom_rec.index(best_nom_rec) if best_nom_rec in opts_nom_rec else 0
                col_nom_rec = st.selectbox("Columna Nombre Receta (Opcional):", opts_nom_rec, index=idx_nom_rec)
            with c_ing:
                col_id_ingr = st.selectbox("Columna ID Ítem (Ingrediente/Extra):", cols_det, index=cols_det.index(find_best_col(['ingrediente', 'extra', 'pl', 'codigo', 'componente', 'item'], cols_det)))
            with c_um:
                col_um_det = st.selectbox("Columna Unidad Medida:", cols_det, index=cols_det.index(find_best_col(['unidad', 'umed', 'um', 'ub', 'medida'], cols_det)))
            
            df_det = df_det_raw.copy()
            df_det['id_rec_clean'] = df_det[col_id_rec].astype(str).str.strip()
            df_det['id_item_clean'] = df_det[col_id_ingr].astype(str).str.strip()
            df_det['um_det_clean'] = df_det[col_um_det].apply(clean_unit)
            
            # Mapas Activos
            ingr_map = df_ingr_master.set_index('pl')[['np', 'ub']].to_dict('index') if df_ingr_master is not None and not df_ingr_master.empty else {}
            extra_map = df_extra_master.set_index('pl')[['np', 'ub']].to_dict('index') if df_extra_master is not None and not df_extra_master.empty else {}
            
            # Mapas Inactivos (Stock Control OFF)
            ingr_inact_map = df_ingr_inactive.set_index('pl')[['np', 'ub']].to_dict('index') if df_ingr_inactive is not None and not df_ingr_inactive.empty else {}
            extra_inact_map = df_extra_inactive.set_index('pl')[['np', 'ub']].to_dict('index') if df_extra_inactive is not None and not df_extra_inactive.empty else {}

            # Mapa auxiliar de Nombres de Receta proveniente de HEADERS_RECETAS (si está cargado)
            headers_name_map = {}
            if file_head is not None:
                df_head_tmp = read_text_file(file_head)
                if df_head_tmp is not None:
                    cols_h_tmp = list(df_head_tmp.columns)
                    c_id_h = find_best_col(['receta', 'pl', 'id', 'codigo'], cols_h_tmp)
                    c_nom_h = find_best_col(['nombre', 'np', 'descripcion', 'producto', 'receta'], [c for c in cols_h_tmp if c != c_id_h], default_none=True)
                    if c_id_h and c_nom_h != "(Ninguna)":
                        headers_name_map = df_head_tmp.set_index(c_id_h)[c_nom_h].astype(str).str.strip().to_dict()

            def get_recipe_name(row):
                rec_id = row['id_rec_clean']
                if col_nom_rec != "(Ninguna / Buscar en Headers / Maestro)" and col_nom_rec in row and pd.notna(row[col_nom_rec]) and str(row[col_nom_rec]).strip() != "":
                    return str(row[col_nom_rec]).strip()
                if rec_id in headers_name_map and headers_name_map[rec_id] != "":
                    return headers_name_map[rec_id]
                if rec_id in ingr_map:
                    return ingr_map[rec_id]['np']
                if rec_id in extra_map:
                    return extra_map[rec_id]['np']
                if rec_id in ingr_inact_map:
                    return ingr_inact_map[rec_id]['np']
                if rec_id in extra_inact_map:
                    return extra_inact_map[rec_id]['np']
                return "NO ESPECIFICADO"

            df_det['Nombre_Receta_Padre'] = df_det.apply(get_recipe_name, axis=1)

            def check_det_line(row):
                item_id = row['id_item_clean']
                um_recipe = row['um_det_clean']
                
                # 1. Ingrediente Activo
                if item_id in ingr_map:
                    ub_master = clean_unit(ingr_map[item_id]['ub'])
                    if not is_unit_compatible(ub_master, um_recipe):
                        return f"ERROR: Unidad en Receta ('{um_recipe}') no es compatible con Medida Base Ingrediente ('{ub_master}')", "Ingrediente", ingr_map[item_id]['np'], ub_master
                    return "OK", "Ingrediente", ingr_map[item_id]['np'], ub_master
                
                # 2. Extra Activo
                elif item_id in extra_map:
                    ub_master = clean_unit(extra_map[item_id]['ub'])
                    if not is_unit_compatible(ub_master, um_recipe):
                        return f"ERROR: Unidad en Receta ('{um_recipe}') no es compatible con Medida Base Extra ('{ub_master}')", "Extra", extra_map[item_id]['np'], ub_master
                    return "OK", "Extra", extra_map[item_id]['np'], ub_master
                
                # 3. Ingrediente Inactivo (wact = 0)
                elif item_id in ingr_inact_map:
                    ub_master = clean_unit(ingr_inact_map[item_id]['ub'])
                    np_master = ingr_inact_map[item_id]['np']
                    return "ERROR: Ítem con stock control off (wact = 0)", "Stock Control OFF (Ingrediente)", np_master, ub_master
                
                # 4. Extra Inactivo (wact = 0)
                elif item_id in extra_inact_map:
                    ub_master = clean_unit(extra_inact_map[item_id]['ub'])
                    np_master = extra_inact_map[item_id]['np']
                    return "ERROR: Ítem con stock control off (wact = 0)", "Stock Control OFF (Extra)", np_master, ub_master

                # 5. Ítem Verdaderamente Desconocido
                else:
                    return "ERROR: El ítem no existe ni en Maestro de Ingredientes ni en Extras", "Desconocido", "DESCONOCIDO", "N/A"

            results = df_det.apply(check_det_line, axis=1)
            df_det['Estado_Validacion'] = [r[0] for r in results]
            df_det['Tipo_Item'] = [r[1] for r in results]
            df_det['Nombre_Item_Maestro'] = [r[2] for r in results]
            df_det['Medida_Base_Maestro'] = [r[3] for r in results]

            err_det = df_det[df_det['Estado_Validacion'] != "OK"].copy()

            r1, r2, r3 = st.columns(3)
            r1.metric("Total Líneas en Recetas", len(df_det))
            r2.metric("Líneas Correctas", len(df_det) - len(err_det))
            r3.metric("Líneas con Discrepancia", len(err_det), delta="-Requieren acción" if len(err_det)>0 else "OK", delta_color="inverse")

            if len(err_det) > 0:
                st.error(f"¡Se detectaron {len(err_det)} línea(s) de recetas con inconsistencias!")
                
                cols_to_show = [col_id_rec, 'Nombre_Receta_Padre', col_id_ingr, 'Tipo_Item', 'Nombre_Item_Maestro', col_um_det, 'Medida_Base_Maestro', 'Estado_Validacion']
                t_det_show = err_det[cols_to_show].copy()
                t_det_show.columns = ['ID Receta', 'Nombre Receta / Producto Padre', 'ID Ítem', 'Tipo Ítem', 'Nombre Ítem (Maestro)', 'Unidad en Receta', 'Unidad Base (Maestro)', 'Diagnóstico del Error']
                
                st.dataframe(t_det_show, use_container_width=True)
                
                out_det = io.BytesIO()
                with pd.ExcelWriter(out_det, engine='openpyxl') as w:
                    t_det_show.to_excel(w, index=False, sheet_name='Errores_Detalle_Recetas')
                st.download_button("📥 Descargar Reporte Errores DETALLE_RECETAS", out_det.getvalue(), "Errores_Detalle_Recetas.xlsx")
            else:
                st.success("🎉 Todas las unidades usadas en las recetas son válidas y compatibles con la Medida Base (ub) de tus maestros.")
        elif df_ingr_master is None and df_extra_master is None:
            st.warning("⚠️ Carga al menos la **1. Base de Ingredientes** o la **2. Base de Extras** para habilitar el cruce.")
    else:
        st.warning("⚠️ Carga el archivo **3. DETALLE_RECETAS (.txt)** en el panel lateral.")

# --- TAB 4: HEADERS RECETAS ---
with tab4:
    st.header("Validación HEADERS_RECETAS vs Maestros")
    if file_head is not None:
        df_head_raw = read_text_file(file_head)
        
        if df_head_raw is not None and (df_ingr_master is not None or df_extra_master is not None):
            st.subheader("Mapeo de Columnas de Encabezados")
            cols_head = list(df_head_raw.columns)
            
            def find_best_col(options, cols, default_none=False):
                for opt in options:
                    for c in cols:
                        if opt.lower() in str(c).lower():
                            return c
                return "(Ninguna)" if default_none else (cols[0] if cols else "")

            ch1, ch2, ch3 = st.columns(3)
            with ch1:
                col_id_rec_h = st.selectbox("Columna ID Receta / Subreceta:", cols_head, index=cols_head.index(find_best_col(['receta', 'pl', 'id', 'codigo'], cols_head)))
            with ch2:
                best_nom_h = find_best_col(['nombre', 'np', 'descripcion', 'producto', 'receta'], [c for c in cols_head if c != col_id_rec_h], default_none=True)
                opts_nom_h = ["(Ninguna / Buscar en Maestro)"] + cols_head
                idx_nom_h = opts_nom_h.index(best_nom_h) if best_nom_h in opts_nom_h else 0
                col_nom_rec_h = st.selectbox("Columna Nombre Receta (Opcional):", opts_nom_h, index=idx_nom_h)
            with ch3:
                col_um_head = st.selectbox("Columna Unidad Medida Rendimiento:", cols_head, index=cols_head.index(find_best_col(['unidad', 'umed', 'um', 'ub', 'medida', 'rendimiento'], cols_head)))
            
            df_head = df_head_raw.copy()
            df_head['id_rec_clean'] = df_head[col_id_rec_h].astype(str).str.strip()
            df_head['um_head_clean'] = df_head[col_um_head].apply(clean_unit)
            
            ingr_map = df_ingr_master.set_index('pl')[['np', 'ub']].to_dict('index') if df_ingr_master is not None and not df_ingr_master.empty else {}
            extra_map = df_extra_master.set_index('pl')[['np', 'ub']].to_dict('index') if df_extra_master is not None and not df_extra_master.empty else {}
            
            ingr_inact_map = df_ingr_inactive.set_index('pl')[['np', 'ub']].to_dict('index') if df_ingr_inactive is not None and not df_ingr_inactive.empty else {}
            extra_inact_map = df_extra_inactive.set_index('pl')[['np', 'ub']].to_dict('index') if df_extra_inactive is not None and not df_extra_inactive.empty else {}

            def get_header_recipe_name(row):
                rec_id = row['id_rec_clean']
                if col_nom_rec_h != "(Ninguna / Buscar en Maestro)" and col_nom_rec_h in row and pd.notna(row[col_nom_rec_h]) and str(row[col_nom_rec_h]).strip() != "":
                    return str(row[col_nom_rec_h]).strip()
                if rec_id in ingr_map:
                    return ingr_map[rec_id]['np']
                if rec_id in extra_map:
                    return extra_map[rec_id]['np']
                if rec_id in ingr_inact_map:
                    return ingr_inact_map[rec_id]['np']
                if rec_id in extra_inact_map:
                    return extra_inact_map[rec_id]['np']
                return "NO ESPECIFICADO"

            df_head['Nombre_Receta_Header'] = df_head.apply(get_header_recipe_name, axis=1)

            def check_head_line(row):
                rec_id = row['id_rec_clean']
                um_head = row['um_head_clean']
                
                if rec_id in ingr_map:
                    ub_master = clean_unit(ingr_map[rec_id]['ub'])
                    if not is_unit_compatible(ub_master, um_head):
                        return f"ERROR: Unidad Header ('{um_head}') no es compatible con Medida Base Ingrediente ('{ub_master}')"
                    return "OK (Coincide con Maestro de Ingrediente/Subreceta)"
                elif rec_id in extra_map:
                    ub_master = clean_unit(extra_map[rec_id]['ub'])
                    if not is_unit_compatible(ub_master, um_head):
                        return f"ERROR: Unidad Header ('{um_head}') no es compatible con Medida Base Extra ('{ub_master}')"
                    return "OK (Coincide con Maestro de Extra)"
                elif rec_id in ingr_inact_map or rec_id in extra_inact_map:
                    return "ERROR: Receta/Subreceta con stock control off (wact = 0)"
                return "OK (Receta Final)"

            df_head['Estado_Validacion'] = df_head.apply(check_head_line, axis=1)
            err_head = df_head[df_head['Estado_Validacion'].str.startswith("ERROR")].copy()

            h1, h2, h3 = st.columns(3)
            h1.metric("Total Encabezados de Receta", len(df_head))
            h2.metric("Encabezados Correctos", len(df_head) - len(err_head))
            h3.metric("Encabezados con Error", len(err_head), delta="-Requieren acción" if len(err_head)>0 else "OK", delta_color="inverse")

            if len(err_head) > 0:
                st.error(f"¡Se detectaron {len(err_head)} encabezado(s) de recetas con unidades inconsistentes!")
                t_head_show = err_head[[col_id_rec_h, 'Nombre_Receta_Header', col_um_head, 'Estado_Validacion']].copy()
                t_head_show.columns = ['ID Receta', 'Nombre Receta / Producto', 'Unidad en Header', 'Diagnóstico del Error']
                st.dataframe(t_head_show, use_container_width=True)
                
                out_head = io.BytesIO()
                with pd.ExcelWriter(out_head, engine='openpyxl') as w:
                    t_head_show.to_excel(w, index=False, sheet_name='Errores_Headers')
                st.download_button("📥 Descargar Reporte Errores HEADERS_RECETAS", out_head.getvalue(), "Errores_Headers_Recetas.xlsx")
            else:
                st.success("🎉 Todos los encabezados de recetas/subrecetas tienen unidades válidas.")
        elif df_ingr_master is None and df_extra_master is None:
            st.warning("⚠️ Carga al menos la **1. Base de Ingredientes** o la **2. Base de Extras** para habilitar la validación.")
    else:
        st.warning("⚠️ Carga el archivo **4. HEADERS_RECETAS (.txt)** en el panel lateral.")