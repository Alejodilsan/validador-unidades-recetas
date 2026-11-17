# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Streamlit app used by Toteat consultants to validate unit-of-measure (UoM) consistency in a client's exported inventory/recipe data. UI text, identifiers and comments are in Spanish; keep new code consistent with that. There are no tests, linters or build step.

## Commands

```bash
python -m venv venv && source venv/bin/activate   # venv/ is gitignored
pip install -r requirements.txt                    # streamlit, pandas, openpyxl, st-gsheets-connection
streamlit run app_validador.py
```

Google Sheets logging requires `.streamlit/secrets.toml` (gitignored) with a `[connections.gsheets]` section (service-account credentials + spreadsheet URL). Without it the app still validates, but shows a "Error al guardar en Sheets" message.

Smoke-test the UI headlessly with `streamlit.testing.v1.AppTest` (note: AppTest cannot drive `file_uploader`, so test validation logic by calling the `validador` functions directly with DataFrames).

## Architecture

- `validador/` — pure logic, **no Streamlit imports** (meant to be reused by a planned bulk/multi-client mode):
  - `lectura.py` — `leer_maestro(bytes, name) -> (activos, inactivos)` (detects header row containing `pl`/`ub` in the first 10 rows; splits `wact` ∈ `0/FALSE/FALSO` as inactive), `leer_texto` (utf-8 → latin-1, separator sniffing), `normalizar_id`, `clean_unit`, `find_best_col`.
  - `reglas.py` — `VALID_UB_MASTERS`, `ALLOWED_UNITS` (unit synonyms per base unit — edit here to accept new units), `validar_maestro`, `construir_maestros` (dicts `pl -> (np, ub)`), `validar_detalle`, `validar_headers`.
  - `reporte.py` (Excel bytes), `registro.py` (append to the `Registro` worksheet).
- `app_validador.py` — UI only. The script reruns top-to-bottom on every interaction; file parsing is wrapped in `st.cache_data` keyed on file bytes.

Key invariants:
- **All IDs are read as strings (`dtype=str`) and passed through `normalizar_id`** (`'123.0' → '123'`, keeps leading zeros). Any new lookup between files must normalize both sides, or matches silently fail.
- Every validated table carries `Severidad` (`OK`/`ERROR`/`INFO`) and `Codigo_Error` (keys of `CODIGOS` in `reglas.py`; masters may hold several joined by ` | `). The UI filters on `Severidad`, not on message text. Items found only among inactive (`wact = 0`) master rows are `INFO`, never counted as errors. New error types need a `CODIGOS` entry.
- `causa_raiz` groups DETALLE errors by item and uses `ids_con_error_maestro` (filled by tabs 1/2, which run before tab 3) to suggest whether to fix the master or the recipes.
- Each tab registers its display tables in `hojas_reporte` and its full validated frame in `validados`; the summary builds the consolidated Excel (`excel_consolidado`) and the per-code table (`resumen_por_codigo`) from those.
- Recipe name resolution order: mapped name column → HEADERS file → master `np` → `"NO ESPECIFICADO"`.
- Error counts live in the `errores` dict (`ingr/extra/det/head`); a new validation must add a key there so it reaches the summary metrics and the Sheets record (`crear_registro`).
- Sheets logging is de-duplicated per session via `st.session_state.ultimo_estado_guardado` (client ID + total errors + file names).
