import pandas as pd
from apify_client import ApifyClient
from google.colab import userdata

# 1. Obtener el token e instanciar ApifyClient
token = userdata.get('APIFY_TOKEN')
client = ApifyClient(token)

# 2. Preparar el input del Actor
run_input = {
  "kv_store_name": "inmobify-storage",
  "modelo_elegido": "Ensamble Top-3",
  "modo_ejecucion": "lote",
  "propiedades": [
    {
      "row_number": 2,
      "id_consulta": "GEO-001",
      "direccion": "Bv. Oroño 850",
      "barrio": "",
      "tipo_inmueble": "Local comercial",
      "superficie_m2": 75,
      "tiene_expensas": 1,
      "precio_publicado_usd": 620
    },
    {
      "row_number": 3,
      "id_consulta": "GEO-002",
      "direccion": "Av. Pellegrini 1420",
      "barrio": "Pellegrini",
      "tipo_inmueble": "Local comercial",
      "superficie_m2": 110,
      "tiene_expensas": 0,
      "precio_publicado_usd": 1250
    },
    {
      "row_number": 4,
      "id_consulta": "GEO-003",
      "direccion": "",
      "barrio": "Echesortu",
      "tipo_inmueble": "Local comercial",
      "superficie_m2": 220,
      "tiene_expensas": 0,
      "precio_publicado_usd": 1100
    },
    {
      "row_number": 5,
      "id_consulta": "GEO-004",
      "direccion": "Córdoba 1150",
      "barrio": "Centro",
      "tipo_inmueble": "Oficina",
      "superficie_m2": 48,
      "tiene_expensas": 1,
      "precio_publicado_usd": 380
    },
    {
      "row_number": 6,
      "id_consulta": "GEO-005",
      "direccion": "",
      "barrio": "",
      "latitud": -32.9512,
      "longitud": -60.6295,
      "tipo_inmueble": "Oficina",
      "superficie_m2": 85,
      "tiene_expensas": 1,
      "precio_publicado_usd": 0
    }
  ]
}

# 3. Ejecutar el Actor y esperar a que finalice
# (Verificá si el slug en tu Apify Console es "inmobify2/inmobify" o "inmobify2/inmobify-inference")
run = client.actor("inmobify2/inmobify").call(run_input=run_input)

# 4. Mostrar los resultados en tabla
dataset_id = run.default_dataset_id
print(f"Resultados en Apify Console: https://console.apify.com/storage/datasets/{dataset_id}\n")

items = list(client.dataset(dataset_id).iterate_items())
display(pd.DataFrame(items))