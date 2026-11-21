import io
import os
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from apify_client import ApifyClient

BARRIOS_ROSARIO = [
    "Centro", "Pichincha", "Pellegrini", "Martin", "Abasto", "Echesortu",
    "Lourdes", "Alberdi", "Arroyito", "Republica de la Sexta", "Fisherton",
    "Refineria", "Cinco Esquinas", "Bella Vista", "Agote", "Parque", "Hospitales"
]

MODELOS_DISPONIBLES = [
    "Ensamble Top-3",
    "Gradient Boosting",
    "HuberRegressor",
    "LightGBM",
    "ElasticNet",
    "Ridge",
    "Lasso",
    "XGBoost",
    "SVR (RBF)",
    "Random Forest",
    "KNN Regressor",
]

def _obtener_cliente_apify() -> tuple[ApifyClient | None, str]:
    token = st.secrets.get("APIFY_TOKEN", os.getenv("APIFY_TOKEN", ""))
    actor_id = st.secrets.get("APIFY_ACTOR_ID", os.getenv("APIFY_ACTOR_ID", "inmobify2/inmobify"))
    if not token:
        return None, actor_id
    return ApifyClient(token), actor_id

def _ejecutar_inferencia_apify(payload: dict) -> pd.DataFrame:
    client, actor_id = _obtener_cliente_apify()
    if client is None:
        raise RuntimeError("Falta configurar APIFY_TOKEN en .streamlit/secrets.toml o variables de entorno.")

    run = client.actor(actor_id).call(run_input=payload)
    dataset_id = run.default_dataset_id if hasattr(run, "default_dataset_id") else run["defaultDatasetId"]
    items = list(client.dataset(dataset_id).iterate_items())
    return pd.DataFrame(items)

def render_tab_tasador() -> None:
    st.subheader("🔮 Tasador Comercial Predictivo en Vivo (Rosario)")
    st.caption(
        "Conectado en tiempo real al Actor de inferencia en Apify, con geocodificación automática "
        "y cálculo de densidad comercial a 200 m."
    )

    # Selector de modelo oculto en panel avanzado para mantener simple la interfaz operativa
    with st.expander("⚙️ Configuración avanzada del modelo de Machine Learning", expanded=False):
        modelo_elegido = st.selectbox(
            "Modelo a utilizar para la predicción:",
            options=MODELOS_DISPONIBLES,
            index=0,
            help="Por defecto se utiliza Ensamble Top-3 (menor error de validación cruzada).",
        )

    modo_tab_ind, modo_tab_lote = st.tabs(["🏢 Tasación Individual", "📊 Tasación en Lote (CSV)"])

    # =========================================================================
    # MODO 1: INDIVIDUAL
    # =========================================================================
    with modo_tab_ind:
        with st.form("form_tasacion_individual"):
            col1, col2 = st.columns(2)
            with col1:
                direccion = st.text_input(
                    "Dirección en Rosario (recomendado)",
                    value="Bv. Oroño 850",
                    placeholder="Ej: Av. Pellegrini 1420 (si se deja vacía usa el centroide del barrio)",
                )
                barrio = st.selectbox("Barrio (referencia o fallback)", options=BARRIOS_ROSARIO, index=0)
                tipo_inmueble = st.selectbox("Tipo de inmueble", options=["Local comercial", "Oficina"])

            with col2:
                superficie_m2 = st.number_input("Superficie total (m²)", min_value=5.0, max_value=5000.0, value=75.0, step=5.0)
                tiene_expensas = st.radio("¿Abona expensas?", options=[1, 0], format_func=lambda x: "Sí" if x == 1 else "No", horizontal=True)
                precio_publicado = st.number_input(
                    "Precio publicado mensual en USD (0 para omitir)",
                    min_value=0.0,
                    max_value=100000.0,
                    value=620.0,
                    step=10.0,
                )

            submitted = st.form_submit_button("Calcular Tasación", type="primary", use_container_width=True)

        if submitted:
            payload = {
                "kv_store_name": "inmobify-storage",
                "modelo_elegido": modelo_elegido,
                "modo_ejecucion": "individual",
                "id_consulta": "WEB-IND-01",
                "direccion": direccion.strip(),
                "barrio": barrio if not direccion.strip() else "",
                "tipo_inmueble": tipo_inmueble,
                "superficie_m2": float(superficie_m2),
                "tiene_expensas": int(tiene_expensas),
                "precio_publicado_usd": float(precio_publicado) if precio_publicado > 0 else None,
            }

            with st.spinner("Geocodificando ubicación, analizando comercios a 200 m y ejecutando modelo..."):
                try:
                    df_res = _ejecutar_inferencia_apify(payload)
                except Exception as exc:
                    st.error(f"Error al ejecutar inferencia en Apify: {exc}")
                    return

            if df_res.empty:
                st.warning("El Actor no devolvió resultados.")
                return

            res = df_res.iloc[0]

            # KPIs principales en grilla 2x2 para que nunca se corte el texto
            diag_full = str(res["diagnostico_mercado"])
            if "Oportunidad" in diag_full:
                diag_corto = "Oportunidad"
            elif "Sobrevaluado" in diag_full:
                diag_corto = "Sobrevaluado"
            elif "Mercado" in diag_full:
                diag_corto = "Precio de Mercado"
            else:
                diag_corto = "Referencia"

            diff = res.get("diferencia_vs_publicado_pct")
            delta_txt = f"{diff:+.1f}% vs. publicado" if pd.notna(diff) else "Sin precio publicado"

            r1_c1, r1_c2 = st.columns(2)
            r1_c1.metric(
                "Alquiler Mensual Estimado",
                f"USD {res['precio_predicho_usd']:,.2f}",
                delta=f"USD {res['precio_m2_predicho_usd']:,.2f} / m²",
                delta_color="off",
            )
            r1_c2.metric(
                "Diagnóstico de Mercado",
                diag_corto,
                delta=delta_txt,
                delta_color="inverse",
            )

            r2_c1, r2_c2 = st.columns(2)
            r2_c1.metric(
                "Entorno Comercial (200 m)",
                f"{int(res['densidad_comercial_200m'])} comercios",
                delta=f"{int(res['diversidad_rubros_200m'])} rubros distintos",
                delta_color="off",
            )
            r2_c2.metric(
                "Distancia a Polo Comercial",
                f"{res['dist_polo_mas_cercano_m']:.0f} m",
                delta=f"Barrio: {res['barrio']}",
                delta_color="off",
            )

            st.info(
                f"📍 **Ubicación resuelta ({res['origen_coordenadas']}):** Barrio **{res['barrio']}** "
                f"(`{res['latitud_usada']:.5f}, {res['longitud_usada']:.5f}`) | "
                f"Modelo: **{res['modelo_utilizado']}**"
            )

            # Mapa interactivo centrado explícitamente en la propiedad tasada
            lat_pt = float(res["latitud_usada"])
            lon_pt = float(res["longitud_usada"])

            fig_map = px.scatter_map(
                df_res,
                lat="latitud_usada",
                lon="longitud_usada",
                hover_name="barrio",
                hover_data={
                    "direccion_ingresada": True,
                    "precio_predicho_usd": ":$.2f",
                    "precio_m2_predicho_usd": ":$.2f",
                    "densidad_comercial_200m": True,
                    "diagnostico_mercado": True,
                },
                center={"lat": lat_pt, "lon": lon_pt},
                zoom=15,
                height=360,
            )
            fig_map.update_traces(marker=dict(size=18, color="#E63946"))
            fig_map.update_layout(
                map_style="carto-positron",
                margin=dict(l=0, r=0, t=0, b=0),
            )
            st.plotly_chart(fig_map, use_container_width=True)

    # =========================================================================
    # MODO 2: LOTE CSV
    # =========================================================================
    with modo_tab_lote:
        st.markdown("Subí un archivo `.csv` con propiedades para tasar todas juntas en una única ejecución.")

        plantilla_csv = (
            "id_consulta,direccion,barrio,tipo_inmueble,superficie_m2,tiene_expensas,precio_publicado_usd\n"
            "LOTE-01,Bv. Oroño 1120,Centro,Local comercial,80,1,650\n"
            "LOTE-02,Av. Pellegrini 1650,Pellegrini,Local comercial,130,0,1450\n"
            "LOTE-03,,Echesortu,Local comercial,195,0,980\n"
        )
        st.download_button(
            "⬇️ Descargar plantilla CSV de ejemplo",
            data=plantilla_csv.encode("utf-8"),
            file_name="plantilla_tasacion_lote_inmobify.csv",
            mime="text/csv",
        )

        archivo_csv = st.file_uploader("Cargar archivo CSV de propiedades", type=["csv"])
        if archivo_csv is not None:
            df_lote_in = pd.read_csv(archivo_csv)
            st.dataframe(df_lote_in, use_container_width=True)

            if st.button("🚀 Tasar Lote Completo", type="primary"):
                propiedades = []
                for i, r in df_lote_in.iterrows():
                    propiedades.append({
                        "row_number": int(i) + 2,
                        "id_consulta": str(r.get("id_consulta", f"CSV-{i+1:03d}")),
                        "direccion": "" if pd.isna(r.get("direccion")) else str(r.get("direccion")).strip(),
                        "barrio": "" if pd.isna(r.get("barrio")) else str(r.get("barrio")).strip(),
                        "tipo_inmueble": "Local comercial" if pd.isna(r.get("tipo_inmueble")) else str(r.get("tipo_inmueble")).strip(),
                        "superficie_m2": float(r.get("superficie_m2", 60)),
                        "tiene_expensas": int(r.get("tiene_expensas", 0)) if pd.notna(r.get("tiene_expensas")) else 0,
                        "precio_publicado_usd": float(r["precio_publicado_usd"]) if pd.notna(r.get("precio_publicado_usd")) and float(r["precio_publicado_usd"]) > 0 else None,
                    })

                payload_lote = {
                    "kv_store_name": "inmobify-storage",
                    "modelo_elegido": modelo_elegido,
                    "modo_ejecucion": "lote",
                    "propiedades": propiedades,
                }

                with st.spinner(f"Procesando {len(propiedades)} propiedades en Apify..."):
                    try:
                        df_lote_out = _ejecutar_inferencia_apify(payload_lote)
                    except Exception as exc:
                        st.error(f"Error al procesar lote: {exc}")
                        return

                st.success(f"Tasación completada: {len(df_lote_out)} propiedades procesadas con **{modelo_elegido}**.")
                st.dataframe(df_lote_out, use_container_width=True)

                st.download_button(
                    "⬇️ Descargar resultados tasados (CSV)",
                    data=df_lote_out.to_csv(index=False).encode("utf-8"),
                    file_name="resultados_tasacion_inmobify.csv",
                    mime="text/csv",
                )

st.set_page_config(
    page_title="Inmobify Rosario — Inteligencia Comercial",
    page_icon="🏢",
    layout="wide",
)

# ------------------------------------------------------------------------------
# CARGA DE DATOS VIA APIFY SDK (R1) CON FALLBACK LOCAL
@st.cache_data(ttl=600)
def cargar_datos() -> pd.DataFrame:
    token = ""
    if "APIFY_TOKEN" in st.secrets:
        token = str(st.secrets["APIFY_TOKEN"]).strip()
    elif os.getenv("APIFY_TOKEN"):
        token = os.getenv("APIFY_TOKEN").strip()

    if not token:
        st.error(f"No se encontró la clave APIFY_TOKEN. Claves detectadas: {list(st.secrets.keys())}")
        st.stop()

    try:
        client = ApifyClient(token)
        stores = client.key_value_stores().list().items
        store_match = next((s for s in stores if getattr(s, "name", None) == "inmobify-storage"), None)

        if not store_match:
            st.error("Autenticación OK, pero no se encontró el Key-Value Store 'inmobify-storage'.")
            st.stop()

        rec = client.key_value_store(store_match.id).get_record("dataset_inmobiliario_completo_rosario.csv")
        val = rec.get("value") if isinstance(rec, dict) else getattr(rec, "value", None)

        if not val:
            st.error("No se encontró 'dataset_inmobiliario_completo_rosario.csv' dentro de 'inmobify-storage'.")
            st.stop()

        text = val.decode("utf-8") if isinstance(val, bytes) else str(val)
        return pd.read_csv(io.StringIO(text))

    except Exception as e:
        st.error(f"Fallo al conectar con Apify ({type(e).__name__}: {e}).")
        st.stop()


df = cargar_datos()

# ------------------------------------------------------------------------------
# SIDEBAR — FILTROS INTERACTIVOS
# ------------------------------------------------------------------------------
st.sidebar.title("🏢 Inmobify Rosario")
st.sidebar.caption("Valuación y entorno comercial geoespacial")

tipos = st.sidebar.multiselect(
    "Tipo de inmueble",
    options=sorted(df["tipo_inmueble"].dropna().unique()),
    default=sorted(df["tipo_inmueble"].dropna().unique()),
)
barrios_disp = sorted(df["barrio"].dropna().unique())
barrios = st.sidebar.multiselect("Barrios (vacío = todos)", options=barrios_disp, default=[])

rango_sup = st.sidebar.slider(
    "Superficie (m²)",
    min_value=int(df["superficie_m2"].min()),
    max_value=int(df["superficie_m2"].max()),
    value=(int(df["superficie_m2"].min()), int(df["superficie_m2"].max())),
)

df_f = df[
    (df["tipo_inmueble"].isin(tipos))
    & (df["superficie_m2"].between(rango_sup[0], rango_sup[1]))
].copy()
if barrios:
    df_f = df_f[df_f["barrio"].isin(barrios)]

# ------------------------------------------------------------------------------
# ENCABEZADO Y KPIs EJECUTIVOS
# ------------------------------------------------------------------------------
st.title("🏢 Inmobify — Radar Comercial e Inmobiliario de Rosario")
st.markdown(
    "Análisis de alquileres comerciales cruzado con **densidad y tráfico de reseñas (200m / 350m)** "
    "y distancia a polos comerciales (*Monumento, Pichincha, Pellegrini*)."
)

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Propiedades analizadas", f"{len(df_f):,}")
k2.metric("Mediana Alquiler (USD)", f"USD {df_f['precio_usd'].median():,.0f}")
k3.metric("Mediana Alquiler (USD / m² / mes)", f"USD {df_f['precio_m2_usd'].median():.2f}")

mask_oport = df_f["indice_precio_relativo_barrio"] < 0.85
cant_oport = int(mask_oport.sum())
ahorro_med = (1 - df_f.loc[mask_oport, "indice_precio_relativo_barrio"].median()) * 100 if cant_oport > 0 else 0
k4.metric(
    "Oportunidades (IPR < 0.85)",
    f"{cant_oport} ({cant_oport / max(len(df_f), 1) * 100:.0f}%)",
    f"-{ahorro_med:.0f}% vs mediana barrial",
)

med_dens = df_f["densidad_comercial_200m"].median()
oport_calif = int((mask_oport & (df_f["densidad_comercial_200m"] >= med_dens)).sum())
k5.metric(
    "Oportunidades Calificadas",
    f"{oport_calif}",
    "IPR < 0.85 + alta densidad comercial",
)

st.divider()

# ------------------------------------------------------------------------------
# PESTAÑAS PRINCIPALES
# ------------------------------------------------------------------------------
tab_tasador, tab_mapa, tab_eda, tab_corr, tab_metricas, tab_datos = st.tabs([
    "🔮 Tasador en Vivo",
    "🗺️ Mapa Geoespacial",
    "📊 Análisis por Barrio y Segmento",
    "🔬 Correlaciones y Elasticidad",
    "🎯 Métricas, KPIs y Selección de Features",
    "📋 Explorador de Oportunidades",
])

with tab_tasador:
    render_tab_tasador()

with tab_mapa:
    st.subheader("Distribución Geográfica y Posición respecto a la Mediana Barrial")

    df_mapa = df_f.dropna(subset=["lat", "lon"]).copy()
    if df_mapa.empty:
        st.warning("No hay propiedades con coordenadas válidas para los filtros seleccionados.")
    else:
        fig_map = px.scatter_map(
            df_mapa,
            lat="lat",
            lon="lon",
            color="posicion_mercado_barrio",
            size="superficie_m2",
            size_max=22,
            zoom=12,
            center={"lat": -32.947, "lon": -60.650},
            map_style="open-street-map",
            color_discrete_map={
                "1. Oportunidad (<85% mediana)": "#2a9d8f",
                "2. En rango de barrio (85-115%)": "#457b9d",
                "3. Premium / Sobre mediana (>115%)": "#e63946",
            },
            hover_name="barrio",
            hover_data={
                "tipo_inmueble": True,
                "superficie_m2": ":.0f",
                "precio_usd": ":,.0f",
                "precio_m2_usd": ":.2f",
                "densidad_comercial_200m": True,
                "diversidad_rubros_200m": True,
                "trafico_resenas_200m": ":,.0f",
                "lat": False,
                "lon": False,
            },
            height=560,
        )
        fig_map.update_layout(margin={"r": 0, "t": 10, "l": 0, "b": 0})
        st.plotly_chart(fig_map, use_container_width=True)

with tab_eda:
    c1, c2 = st.columns(2)
    with c1:
        top_b = df_f["barrio"].value_counts().head(10).index
        fig_box = px.box(
            df_f[df_f["barrio"].isin(top_b)],
            x="precio_m2_usd",
            y="barrio",
            color="tipo_inmueble",
            category_orders={"barrio": list(top_b)},
            title="Dispersión de USD/m² en los 10 Barrios Principales",
            labels={"precio_m2_usd": "USD / m²", "barrio": ""},
        )
        st.plotly_chart(fig_box, use_container_width=True)

    with c2:
        fig_hist = px.histogram(
            df_f,
            x="precio_usd",
            color="tipo_inmueble",
            nbins=30,
            barmode="overlay",
            opacity=0.75,
            title="Distribución de Alquiler Mensual (USD)",
            labels={"precio_usd": "Alquiler Mensual (USD)"},
        )
        st.plotly_chart(fig_hist, use_container_width=True)

with tab_corr:
    c1, c2 = st.columns([1.2, 1])
    with c1:
        cols_num = [
            "precio_usd", "precio_m2_usd", "log_superficie_m2",
            "tiene_expensas", "densidad_comercial_200m", "diversidad_rubros_200m",
            "log_trafico_resenas_200m", "ratio_densidad_200_350", "dist_polo_mas_cercano_m",
        ]
        corr = df_f[cols_num].corr().round(2)
        fig_heat = px.imshow(
            corr,
            text_auto=True,
            color_continuous_scale="RdBu_r",
            zmin=-1,
            zmax=1,
            title="Matriz de Correlación Interactiva (Pearson)",
        )
        st.plotly_chart(fig_heat, use_container_width=True)

    with c2:
        df_plot = df_f.copy()
        df_plot["log_precio_usd"] = np.log1p(df_plot["precio_usd"])
        fig_reg = px.scatter(
            df_plot,
            x="log_superficie_m2",
            y="log_precio_usd",
            color="tipo_inmueble",
            trendline="ols",
            title="Elasticidad Log-Log: Superficie vs Alquiler (r = 0.77)",
            labels={"log_superficie_m2": "log(Superficie m² + 1)", "log_precio_usd": "log(Precio USD + 1)"},
        )
        st.plotly_chart(fig_reg, use_container_width=True)

    st.divider()
    st.subheader("📐 Comportamiento de Elasticidad y Efectos No Lineales de las Features Elegidas")

    col_e1, col_e2 = st.columns(2)

    with col_e1:
        # 1. Economía de escala: caída del USD/m² al aumentar log_superficie_m2
        fig_escala = px.scatter(
            df_f,
            x="log_superficie_m2",
            y="precio_m2_usd",
            color="tipo_inmueble",
            trendline="ols",
            opacity=0.65,
            hover_name="barrio",
            hover_data=["superficie_m2", "precio_usd"],
            title="Economía de Escala: log(Superficie) vs USD/m² (r = -0.35)",
            labels={
                "log_superficie_m2": "log(Superficie m² + 1)",
                "precio_m2_usd": "Alquiler Unitario (USD / m² / mes)",
                "tipo_inmueble": "Tipo",
            },
        )
        st.plotly_chart(fig_escala, use_container_width=True)

    with col_e2:
        # 2. Gradiente no lineal: distancia a polos vs tráfico de reseñas y diversidad de rubros
        fig_polo = px.scatter(
            df_f,
            x="dist_polo_mas_cercano_m",
            y="log_trafico_resenas_200m",
            color="diversidad_rubros_200m",
            size="densidad_comercial_200m",
            size_max=18,
            color_continuous_scale="Viridis",
            hover_name="barrio",
            hover_data=["tipo_inmueble", "precio_m2_usd"],
            title="Decaimiento Espacial: Distancia a Polos vs Tráfico Comercial (200m)",
            labels={
                "dist_polo_mas_cercano_m": "Distancia al Polo Más Cercano (m)",
                "log_trafico_resenas_200m": "log(Tráfico Reseñas 200m + 1)",
                "diversidad_rubros_200m": "Rubros (200m)",
            },
        )
        st.plotly_chart(fig_polo, use_container_width=True)

    # 3. Efecto combinado de las binarias estructurales (es_gran_superficie y tiene_expensas)
    df_bin = df_f.copy()
    df_bin["Escala"] = np.where(df_bin["es_gran_superficie"] == 1, "Gran Superficie (>200 m²)", "Estándar (≤200 m²)")
    df_bin["Expensas"] = np.where(df_bin["tiene_expensas"] == 1, "Con Expensas", "Sin Expensas")

    fig_struct = px.box(
        df_bin,
        x="Escala",
        y="precio_usd",
        color="Expensas",
        points="outliers",
        color_discrete_map={"Sin Expensas": "#2a9d8f", "Con Expensas": "#e76f51"},
        title="Impacto Estructural en Alquiler Total (USD): Gran Superficie vs Expensas",
        labels={"Escala": "", "precio_usd": "Alquiler Mensual (USD)"},
    )
    st.plotly_chart(fig_struct, use_container_width=True)

with tab_metricas:
    st.subheader("🎯 Fundamentación de Features (4 Lineales + 5 No Lineales) y KPIs de Negocio")

    # --- FILA 1: TORNADO DE CORRELACIONES LINEALES + DISTRIBUCIÓN DEL IPR ---
    col_m1, col_m2 = st.columns(2)

    with col_m1:
        features_eval = [
            "log_superficie_m2", "superficie_m2", "es_gran_superficie",
            "tiene_expensas", "dist_pichincha_m", "ratio_densidad_200_350",
            "densidad_comercial_200m", "dist_polo_mas_cercano_m",
            "diversidad_rubros_200m", "log_trafico_resenas_200m"
        ]
        corrs = df_f[features_eval].corrwith(df_f["precio_usd"]).dropna().sort_values()
        df_tornado = pd.DataFrame({
            "Feature": corrs.index,
            "Correlación (r)": corrs.values,
            "Signo": ["Positiva (+)" if v >= 0 else "Negativa (-)" for v in corrs.values],
        })
        fig_tornado = px.bar(
            df_tornado,
            x="Correlación (r)",
            y="Feature",
            color="Signo",
            orientation="h",
            text=df_tornado["Correlación (r)"].round(3),
            color_discrete_map={"Positiva (+)": "#2a9d8f", "Negativa (-)": "#e63946"},
            title="Ranking de Correlación Lineal (r) con Alquiler Total (USD)",
        )
        fig_tornado.update_traces(textposition="outside")
        fig_tornado.update_layout(xaxis_range=[-0.5, 0.95], showlegend=True)
        st.plotly_chart(fig_tornado, use_container_width=True)

    with col_m2:
        fig_ipr = px.histogram(
            df_f,
            x="indice_precio_relativo_barrio",
            color="posicion_mercado_barrio",
            nbins=35,
            color_discrete_map={
                "1. Oportunidad (<85% mediana)": "#2a9d8f",
                "2. En rango de barrio (85-115%)": "#457b9d",
                "3. Premium / Sobre mediana (>115%)": "#e63946",
            },
            title="Distribución del Índice de Precio Relativo Barrial (IPR)",
            labels={"indice_precio_relativo_barrio": "IPR (Precio/m² / Mediana Barrio)"},
        )
        fig_ipr.add_vline(
            x=0.85, line_dash="dash", line_color="#2a9d8f",
            annotation_text="Umbral Oportunidad (0.85)", annotation_position="top left"
        )
        fig_ipr.add_vline(
            x=1.15, line_dash="dash", line_color="#e63946",
            annotation_text="Umbral Premium (1.15)", annotation_position="top right"
        )
        st.plotly_chart(fig_ipr, use_container_width=True)

    # --- FILA 2: BUBBLE CHART NO LINEAL + FRECUENCIA DE SEGMENTOS ---
    col_m3, col_m4 = st.columns([1.3, 1])

    with col_m3:
        fig_bubble = px.scatter(
            df_f,
            x="log_trafico_resenas_200m",
            y="precio_m2_usd",
            size="densidad_comercial_200m",
            color="posicion_mercado_barrio",
            hover_name="barrio",
            hover_data=["tipo_inmueble", "superficie_m2", "precio_usd", "diversidad_rubros_200m"],
            color_discrete_map={
                "1. Oportunidad (<85% mediana)": "#2a9d8f",
                "2. En rango de barrio (85-115%)": "#457b9d",
                "3. Premium / Sobre mediana (>115%)": "#e63946",
            },
            title="Interacción No Lineal: Tráfico Peatonal vs USD/m² (Tamaño = Densidad 200m)",
            labels={
                "log_trafico_resenas_200m": "log(Tráfico Reseñas 200m + 1)",
                "precio_m2_usd": "Alquiler (USD / m² / mes)",
            },
        )
        fig_bubble.add_hline(
            y=df_f["precio_m2_usd"].median(), line_dash="dot", line_color="gray",
            annotation_text=f"Mediana USD {df_f['precio_m2_usd'].median():.2f}/m²"
        )
        st.plotly_chart(fig_bubble, use_container_width=True)

    with col_m4:
        df_seg = (
            df_f.groupby(["posicion_mercado_barrio", "tipo_inmueble"])
            .size()
            .reset_index(name="Cantidad")
        )
        fig_freq = px.bar(
            df_seg,
            x="posicion_mercado_barrio",
            y="Cantidad",
            color="tipo_inmueble",
            barmode="group",
            text="Cantidad",
            title="Diagrama de Frecuencia: Segmentación por Tipo",
            labels={"posicion_mercado_barrio": "Segmento de Mercado", "Cantidad": "Propiedades"},
        )
        fig_freq.update_traces(textposition="outside")
        st.plotly_chart(fig_freq, use_container_width=True)

    # --- FILA 3: RESUMEN DE LAS 9 FEATURES SELECCIONADAS Y META DE EVALUACIÓN ---
    st.divider()
    c_feat, c_met = st.columns([1.6, 1])
    with c_feat:
        df_features_sel = pd.DataFrame([
            {"Feature": "log_superficie_m2", "Tipo": "Lineal (1/4)", "Evidencia": "r = +0.773 con precio_usd", "Rol": "Elasticidad log-log y economía de escala"},
            {"Feature": "superficie_m2", "Tipo": "Lineal (2/4)", "Evidencia": "r = +0.741 con precio_usd", "Rol": "Escala física directa del inmueble"},
            {"Feature": "es_gran_superficie", "Tipo": "Lineal (3/4)", "Evidencia": "r = +0.689 con precio_usd", "Rol": "Salto estructural en locales > 200 m²"},
            {"Feature": "tiene_expensas", "Tipo": "Lineal (4/4)", "Evidencia": "r = -0.315 con precio_usd", "Rol": "Descuento en canon por carga de expensas"},
            {"Feature": "barrio + tipo_inmueble", "Tipo": "No Lineal (1/5)", "Evidencia": "Mediana USD 6.88 a 14.20/m²", "Rol": "Prima por categoría edilicia y vidriera"},
            {"Feature": "log_trafico_resenas_200m", "Tipo": "No Lineal (2/5)", "Evidencia": "r = -0.54 dist. Monumento", "Rol": "Proxy no lineal de flujo peatonal real"},
            {"Feature": "densidad_comercial_200m", "Tipo": "No Lineal (3/5)", "Evidencia": "0 a 71 comercios en 200m", "Rol": "Concentración de oferta en el entorno inmediato"},
            {"Feature": "diversidad_rubros_200m", "Tipo": "No Lineal (4/5)", "Evidencia": "0 a 36 rubros distintos", "Rol": "Sinergia comercial y atracción de público"},
            {"Feature": "dist_polo_mas_cercano_m", "Tipo": "No Lineal (5/5)", "Evidencia": "Mín. Monumento/Pichincha/Pellegrini", "Rol": "Gradiente de centralidad urbana"},
        ])
        st.dataframe(df_features_sel, use_container_width=True, hide_index=True)

    with c_met:
        st.info(
            "**Target Principal:** `log1p(precio_usd)` (canon mensual en USD).\n\n"
            "**Métrica Técnica-Financiera:** **MAPE ≤ 18%** y **MAE ≤ USD 2.00/m²**.\n\n"
            "**Justificación estadística:** La asimetría positiva de `precio_usd` y el sesgo derecho del "
            "Índice de Precio Relativo (`IPR`) justifican usar **MAPE** y **medianas segmentadas**, "
            "evitando que los locales de gran metraje distorsionen la evaluación."
        )

with tab_datos:
    st.subheader("Listado Priorizado por Índice Relativo al Barrio")
    cols_tabla = [
        "posting_id", "barrio", "tipo_inmueble", "superficie_m2",
        "precio_usd", "precio_m2_usd", "precio_m2_mediana_barrio",
        "indice_precio_relativo_barrio", "posicion_mercado_barrio",
        "densidad_comercial_200m", "diversidad_rubros_200m", "dist_polo_mas_cercano_m",
    ]
    st.dataframe(
        df_f[cols_tabla].sort_values("indice_precio_relativo_barrio"),
        use_container_width=True,
        hide_index=True,
    )