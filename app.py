import os
import time

import requests
import streamlit as st

URL = os.getenv(
    "ENDPOINT_URL",
    "https://dbc-adc59796-504b.cloud.databricks.com/serving-endpoints/enigh-ingreso-alto/invocations",
)
TOKEN = os.getenv("DATABRICKS_TOKEN")

TIMEOUT = (5, 60)  # (conexión, respuesta) en segundos
REINTENTOS = 3
ESPERA = 10

GRUPOS = {"011": 0.30, "046": 0.05, "111": 0.08, "072": 0.06,
          "131": 0.03, "083": 0.04, "056": 0.03, "045": 0.04}

TAM_LOC = {1: "100,000 habitantes o más", 2: "15,000 a 99,999", 3: "2,500 a 14,999", 4: "Menos de 2,500"}
EST_SOCIO = {1: "Bajo", 2: "Medio bajo", 3: "Medio alto", 4: "Alto"}
CLASE_HOG = {1: "Unipersonal", 2: "Nuclear", 3: "Ampliado", 4: "Compuesto", 5: "Corresidente"}
SEXO = {1: "Hombre", 2: "Mujer"}
EDUCA = {1: "Sin instrucción", 2: "Preescolar", 3: "Primaria incompleta", 4: "Primaria completa",
         5: "Secundaria incompleta", 6: "Secundaria completa", 7: "Preparatoria incompleta",
         8: "Preparatoria completa", 9: "Profesional incompleta", 10: "Profesional completa", 11: "Posgrado"}


def falla(mensaje, cuerpo, r=None):
    return {"ok": False, "error": mensaje, "peticion": cuerpo,
            "respuesta": r.text[:500] if r is not None else ""}


def consultar(registro):
    cuerpo = {"dataframe_records": [registro]}
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    problema = ""
    for intento in range(1, REINTENTOS + 1):
        try:
            r = requests.post(URL, headers=headers, json=cuerpo, timeout=TIMEOUT)
        except requests.exceptions.Timeout:
            problema = "El servicio tardó demasiado en responder (puede estar despertando)."
        except requests.exceptions.ConnectionError:
            problema = "No se pudo conectar con el servicio. Revisa tu conexión a internet."
        except requests.exceptions.RequestException as e:
            return falla(f"Error inesperado al llamar al servicio: {e}", cuerpo)
        else:
            if r.status_code == 200:
                try:
                    prediccion = int(r.json()["predictions"][0])
                    if prediccion not in (0, 1):
                        raise ValueError("valor fuera de rango")
                except (ValueError, KeyError, IndexError, TypeError):
                    return falla("El servicio respondió, pero con un formato inesperado.", cuerpo, r)
                return {"ok": True, "prediccion": prediccion, "peticion": cuerpo, "respuesta": r.text}
            if r.status_code in (401, 403):
                return falla("El token no es válido o no tiene permiso. Revisa DATABRICKS_TOKEN.", cuerpo, r)
            if r.status_code == 404:
                return falla("No se encontró el endpoint. Revisa la URL (ENDPOINT_URL).", cuerpo, r)
            if r.status_code == 400:
                return falla("El servicio rechazó los datos enviados (código 400).", cuerpo, r)
            if r.status_code in (429, 500, 502, 503, 504):
                problema = f"El servicio no está disponible por ahora (código {r.status_code})."
            else:
                return falla(f"Respuesta inesperada del servicio (código {r.status_code}).", cuerpo, r)
        if intento < REINTENTOS:
            time.sleep(ESPERA)
    return falla(problema + " Intenta de nuevo en un minuto.", cuerpo)


st.set_page_config(page_title="ENIGH 2024 | Ingreso del hogar", page_icon="🏠")
st.title("🏠 ¿Es un hogar de ingreso alto?")
st.write("Esta app consulta un modelo publicado en Databricks, entrenado con la ENIGH 2024 (INEGI), "
         "para estimar si un hogar está en el 20% de mayor ingreso.")
st.caption("El corte del 20% superior equivale a ~$99,708 pesos de ingreso corriente trimestral por hogar.")

if not TOKEN:
    st.error("Falta el token de acceso. Define la variable de entorno DATABRICKS_TOKEN antes de abrir la app.")
    st.stop()

with st.form("hogar"):
    st.subheader("Datos del hogar")
    c1, c2 = st.columns(2)
    entidad = c1.number_input("Entidad federativa (clave 1 a 32)", 1, 32, 14)
    tam_loc = c2.selectbox("Tamaño de localidad", list(TAM_LOC), index=0, format_func=lambda k: TAM_LOC[k])
    est_socio = c1.selectbox("Estrato socioeconómico", list(EST_SOCIO), index=2, format_func=lambda k: EST_SOCIO[k])
    clase_hog = c2.selectbox("Clase de hogar", list(CLASE_HOG), index=1, format_func=lambda k: CLASE_HOG[k])
    tot_integ = c1.number_input("Integrantes del hogar", 1, 30, 4)
    ocupados = c2.number_input("Integrantes ocupados", 0, 30, 2)

    st.subheader("Jefe(a) del hogar")
    c3, c4, c5 = st.columns(3)
    sexo_jefe = c3.selectbox("Sexo", list(SEXO), index=0, format_func=lambda k: SEXO[k])
    edad_jefe = c4.number_input("Edad", 12, 110, 45)
    educa_jefe = c5.selectbox("Escolaridad", list(EDUCA), index=8, format_func=lambda k: EDUCA[k])

    st.subheader("Gasto trimestral del hogar")
    gasto_total_tri = st.number_input("Gasto total trimestral (pesos)", 1.0, 100000000.0, 90000.0, step=1000.0)
    c6, c7, c8 = st.columns(3)
    n_registros = c6.number_input("Número de gastos registrados", 1, 2000, 60)
    n_claves = c7.number_input("Productos o servicios distintos", 1, 2000, 50)
    n_grupos = c8.number_input("Grupos de gasto distintos", 1, 100, 20)
    pct_nm = st.slider("% del gasto no monetario (regalos, autoconsumo)", 0.0, 1.0, 0.05, 0.01)

    st.subheader("Distribución del gasto por grupo")
    st.caption("Proporción del gasto total en cada grupo (la suma no puede pasar de 1).")
    pct_g = {}
    cols = st.columns(4)
    for i, (g, v) in enumerate(GRUPOS.items()):
        pct_g[g] = cols[i % 4].slider(f"Grupo {g}", 0.0, 1.0, v, 0.01)

    enviado = st.form_submit_button("Consultar modelo")

if enviado:
    errores = []
    if sum(pct_g.values()) > 1.0:
        errores.append("La suma de los porcentajes por grupo no puede ser mayor a 1.")
    if n_claves > n_registros:
        errores.append("Los productos distintos no pueden ser más que los gastos registrados.")
    if n_grupos > n_claves:
        errores.append("Los grupos distintos no pueden ser más que los productos distintos.")
    if ocupados > tot_integ:
        errores.append("Los integrantes ocupados no pueden ser más que los integrantes del hogar.")

    if errores:
        for e in errores:
            st.error(e)
    else:
        registro = {
            "entidad": float(entidad), "tam_loc": float(tam_loc), "est_socio": float(est_socio),
            "clase_hog": float(clase_hog), "sexo_jefe": float(sexo_jefe), "edad_jefe": float(edad_jefe),
            "educa_jefe": float(educa_jefe), "tot_integ": float(tot_integ), "ocupados": float(ocupados),
            "gasto_total_tri": float(gasto_total_tri), "n_registros": float(n_registros),
            "n_claves": float(n_claves), "n_grupos": float(n_grupos), "pct_no_monetario": float(pct_nm),
        }
        for g, v in pct_g.items():
            registro[f"pct_g_{g}"] = float(v)

        with st.spinner("Consultando el modelo... la primera consulta puede tardar un par de minutos."):
            resultado = consultar(registro)

        if resultado["ok"]:
            if resultado["prediccion"] == 1:
                st.success("Predicción: hogar de **ingreso ALTO** (dentro del 20% superior).")
            else:
                st.info("Predicción: hogar de **ingreso no alto** (fuera del 20% superior).")
        else:
            st.error(resultado["error"])

        with st.expander("Detalle técnico"):
            st.write("Petición enviada:")
            st.json(resultado["peticion"])
            st.write("Respuesta recibida:")
            st.code(resultado.get("respuesta", ""))