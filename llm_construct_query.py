import os
import json
import re
from elasticsearch import Elasticsearch
import ollama 
from dotenv import load_dotenv

load_dotenv()

ELASTICSEARCH_HOST = os.getenv('ELASTICSEARCH_HOST')
ELASTICSEARCH_PORT = os.getenv('ELASTICSEARCH_PORT')
ELASTICSEARCH_USERNAME = os.getenv('ELASTICSEARCH_USERNAME')
ELASTICSEARCH_PASSWORD = os.getenv('ELASTICSEARCH_PASSWORD') 

# Elasticsearch local connection
hosts = f"http://{ELASTICSEARCH_HOST}:{ELASTICSEARCH_PORT}"
es = Elasticsearch([hosts], basic_auth=(ELASTICSEARCH_USERNAME, ELASTICSEARCH_PASSWORD))
es.info()


# Ollama Configuration
OLLAMA_BASE_URL = os.getenv('OLLAMA_BASE_URL')
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL')


ES_INDEX = os.getenv('ES_INDEX')
TEMPLATE_ID = os.getenv('TEMPLATE_ID')

google_maps_api_key = os.getenv('GMAPS_API_KEY')


indice = "hoteles"  # tu índice



FEW_SHOT_PROMPT = """
Eres un experto en Elasticsearch. Dado el siguiente esquema de índice de hoteles, genera SOLO la consulta JSON válida para buscar detalles del hotel solicitado.

Esquema relevante:
- nombre: text
- localidad: text
- servicios: text
- mascotas: boolean
- descripcion: text
- precio: integer
- fechaEntrada: date (yyyy-MM-dd)
- fechaSalida: date (yyyy-MM-dd)

Ejemplo 1:
Pregunta: "Muéstrame hoteles en Aguadulce con piscina y parking, ordenados por precio ascendente para el día 01/06/2025."
Respuesta JSON:
{
  "query": {
    "bool": {
      "must": [
        { "match": { "localidad": "aguadulce" } },
        { "range": { "fechaEntrada": { "lte": "2025-06-01" } } }
        {
          "bool": {
            "should": [
              { "match": { "servicios": "piscina" } },
              { "match": { "servicios": "parking" } }
            ],
            "minimum_should_match": 2
          }
        }
      ]
    }
  },
  "sort": [{ "precio": "asc" }],
  "size": 10
}


Ejemplo 2:
Pregunta: "Dime hoteles que admiten mascotas en Madrid disponibles el 10 de julio de 2025."
Respuesta JSON:
{
  "query": {
    "bool": {
      "filter": [
        { "match": { "localidad": "Madrid" } },
        { "term": { "mascotas": true } },
        { "range": { "fechaEntrada": { "gte": "2025-07-10" } } }
      ]
    }
  },
  "size": 10
}

Ejemplo 3:
Pregunta: "Quiero conocer los detalles del hotel La Perla."
Respuesta JSON:
{
  "query": {
    "match": {
      "nombre": "La Perla"
    }
  },
  "size": 1
}

Ahora, genera la consulta JSON para esta pregunta:
"{pregunta}"
"""

def extraer_json_valido(texto):
    """Extrae y parsea el primer bloque JSON válido de un string."""
    try:
        match = re.search(r'\{.*\}', texto, re.DOTALL)
        if not match:
            raise ValueError("No se encontró bloque JSON.")
        return json.loads(match.group())
    except json.JSONDecodeError as e:
        print("⚠️ Error al parsear JSON:", e)
        print("Respuesta cruda:\n", texto)
        return None

def generar_consulta_llm(pregunta: str) -> dict:
    prompt = FEW_SHOT_PROMPT.replace("{pregunta}", pregunta)
    respuesta = ollama.chat(model=OLLAMA_MODEL, messages=[{"role":"user", "content": prompt}])
    contenido = respuesta['message']['content']  # <- Extrae el texto
    consulta = extraer_json_valido(contenido)
    print("🔍 Respuesta raw del LLM:")
    print(consulta)
    return consulta

def buscar_en_elasticsearch(consulta: dict):
    resultados = es.search(index=indice, body=consulta)
    return resultados

def resumen_resultados(resultados) -> str:
    hits = resultados.get("hits", {}).get("hits", [])
    if not hits:
        return "No se encontraron resultados para la consulta."
    resumen = "Resultados encontrados:\n"
    for hit in hits:
        fuente = hit.get("_source", {})
        resumen += f"- Hotel: {fuente.get('nombre', 'N/A')}, Localidad: {fuente.get('localidad', 'N/A')}, Precio: {fuente.get('precio', 'N/A')}€\n"
    return resumen

def main():
    pregunta_usuario = input("Pregunta sobre hoteles: ")
    consulta = generar_consulta_llm(pregunta_usuario)
    print("Consulta Elasticsearch generada:")
    print(json.dumps(consulta, indent=2))
    resultados = buscar_en_elasticsearch(consulta)
    respuesta_natural = resumen_resultados(resultados)
    print("\nRespuesta en lenguaje natural:")
    print(respuesta_natural)

if __name__ == "__main__":
    main()