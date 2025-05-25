import json
import os
from elasticsearch import Elasticsearch, helpers, NotFoundError
import requests
from dotenv import load_dotenv

# Cargar las variables desde el archivo .env
load_dotenv()
ELASTICSEARCH_HOST = os.getenv('ELASTICSEARCH_HOST')
ELASTICSEARCH_PORT = os.getenv('ELASTICSEARCH_PORT')
ELASTICSEARCH_USERNAME = os.getenv('ELASTICSEARCH_USERNAME')
ELASTICSEARCH_PASSWORD = os.getenv('ELASTICSEARCH_PASSWORD') 


# Conexión Elasticsearch
hosts = f"http://{ELASTICSEARCH_HOST}:{ELASTICSEARCH_PORT}"
es = Elasticsearch([hosts], basic_auth=(ELASTICSEARCH_USERNAME, ELASTICSEARCH_PASSWORD)) 

# Índice y plantilla
ES_INDEX = os.getenv('ES_INDEX')
TEMPLATE_ID = os.getenv('TEMPLATE_ID')


# Mapping de hoteles
INDEX_MAPPING = {
    "mappings": {
        "properties": {
            "url": {"type": "keyword"},
      "id": {
        "type": "keyword"
      },
      "nombre": {
        "type": "text"
      },
      "localidad": {
        "type": "text"
      },
      "coordenadas": {
        "type": "geo_point"
      },
      "servicios": {
        "type": "text"
      },
      "mascotas": {
        "type": "boolean"
      },
      "descripcion": {
        "type": "text"
      },
      "opinion": {
        "type": "float"
      },
      "comentarios": {
        "type": "integer"
      },
      "fechaEntrada": {
        "type": "date",
        "format": "yyyy-MM-dd"
      },
      "fechaSalida": {
        "type": "date",
        "format": "yyyy-MM-dd"
      },
      "precio": {
        "type": "integer"
      },
      "marca": {
        "type": "text"
      },
      "destacados": {
        "type": "text"
      }
    }        
    }
}


# Creación del índice con el mapping
def crear_index():
    try:
        if es.indices.exists(index=ES_INDEX):
            print(f"Indice '{ES_INDEX}' existe. Borrando y recreando...")
            es.indices.delete(index=ES_INDEX)

        es.indices.create(index=ES_INDEX, body=INDEX_MAPPING)
        print(f"Index '{ES_INDEX}' creado correctamente.")
    except Exception as e:
        print(f"Error creando índice: {e}")
        exit(1)


# Lectura de JSON con hoteles
def carga_json():
    file_path = "almería_20250522.json"
    print(f"Leyendo datos desde: {file_path}")
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            for item in data:
                yield json.dumps(item)
    except FileNotFoundError:
        print(f"Error: Fichero {file_path} no encontrado")
        exit(1)
    except json.JSONDecodeError as e:
        print(f"Error decodificando JSON: {e}")
        exit(1)


# Ingesta de datos en Elasticsearch
def ingesta_datos():
    print("Carga datos en Elasticsearch...")
    actions = []

    for json_str in carga_json():
        if json_str:
            try:
                record = json.loads(json_str)
                if "coordenadas" in record:
                    record["coordenadas"] = {
                        "lat": record["coordenadas"]["latitud"],
                        "lon": record["coordenadas"]["longitud"]
                    }
                if "mascotas" in record:
                    record["mascotas"] = True if record["mascotas"].lower() == "sí" else False
                actions.append({"_index": ES_INDEX, "_source": record})
            except json.JSONDecodeError as e:
                print(f"Error decoding JSON: {e}. Skipping line.")
                continue
     
    if actions:
        try:
            helpers.bulk(es.options(request_timeout=80), actions)
            print(f"Cargados {len(actions)} registros restantes.")
        except helpers.BulkIndexError as e:
            print(f"Falla de carga masiva de {len(e.errors)} documentos restantes:")
            for error in e.errors:
                print(json.dumps(error, indent=2))

    print("Carga de datos completada.")


if __name__ == "__main__":
    print("Carga de datos a ElastiSearch. Iniciando conexión...")    
    crear_index()
    carga_json()
    ingesta_datos()
    print("Carga de datos completada.")