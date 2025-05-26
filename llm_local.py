import os
import json
import re
from elasticsearch import Elasticsearch
import ollama
import requests 
from dotenv import load_dotenv

load_dotenv()

ELASTICSEARCH_HOST = os.getenv('ELASTICSEARCH_HOST')
ELASTICSEARCH_PORT = os.getenv('ELASTICSEARCH_PORT')
ELASTICSEARCH_USERNAME = os.getenv('ELASTICSEARCH_USERNAME')
ELASTICSEARCH_PASSWORD = os.getenv('ELASTICSEARCH_PASSWORD') 

# Conexión Elasticsearch
hosts = f"http://{ELASTICSEARCH_HOST}:{ELASTICSEARCH_PORT}"
es = Elasticsearch([hosts], basic_auth=(ELASTICSEARCH_USERNAME, ELASTICSEARCH_PASSWORD))
es.info()


# Configuración Ollama
OLLAMA_BASE_URL = os.getenv('OLLAMA_BASE_URL')
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL')



ES_INDEX = os.getenv('ES_INDEX')
TEMPLATE_ID = os.getenv('TEMPLATE_ID')


indice = ES_INDEX

mensajes = [
        {"role": "user", "content": "hola"},
    ]

 # Inicialización del cliente Ollama
try:        
    respuesta = ollama.chat(
                model=OLLAMA_MODEL,
                messages=mensajes,
                options={"temperature": 0.1}, 
            )

except requests.exceptions.RequestException as e:
    print(f"Error iniciando Ollama: {e}")

FEW_SHOT_PROMPT = """
Eres un experto en Elasticsearch. Dado el siguiente esquema de índice de hoteles, genera SOLO la consulta JSON válida para buscar detalles del hotel solicitado.

Esquema:
- nombre: text
- provincia: text
- localidad: text
- servicios: text
- location: geo_point
- descripcion: text
- precio: integer
- fechaEntrada: date (yyyy-MM-dd)

Ejemplo 1:
Pregunta: "Muéstrame hoteles en Aguadulce con piscina y parking, ordenados por precio ascendente para el día 01/06/2025."
Respuesta JSON:
{
  "query": {
    "bool": {
      "must": [
        { "match": { "localidad": "aguadulce" } },
        { "term": { "fechaEntrada":  "2025-06-01"  } }
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
  "size": 10
}


Ejemplo 2:
Pregunta: "Dime hoteles que  en Madrid disponibles el 10 de julio de 2025."
Respuesta JSON:
{
  "query": {
    "bool": {
      "filter": [
        { "match": { "localidad": "Madrid" } },
        { "term": { "fechaEntrada": "2025-07-10" } }
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

Ahora, genera SOLO la consulta JSON para esta pregunta:
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
        print("Respuesta raw:\n", texto)
        return None

def generar_consulta_llm(pregunta: str) -> dict:
    prompt = FEW_SHOT_PROMPT.replace("{pregunta}", pregunta)
    try:        
        respuesta = ollama.chat(
                model=OLLAMA_MODEL,
                messages=[{"role":"user", "content": prompt}],
                options={"temperature": 0.1}, 
            )

    except requests.exceptions.RequestException as e:
        print(f"Error iniciando Ollama: {e}")
    mensaje = respuesta.get("message", {})
    consulta = extraer_json_valido(mensaje.content)
    print("Respuesta raw del LLM:")
    print(consulta)
    return consulta

def buscar_en_elasticsearch(consulta: dict):
    resultados = es.search(index=indice, body=consulta)
    return resultados

def construir_prompt_multiple(resultados) -> str:
    prompt = "Describe brevemente y en lenguaje natural los siguientes hoteles como si fuera parte de una recomendación turística. Usa viñetas o párrafos separados para cada hotel y no inventes ni añadas información, solo la recibida. Si no obtienes resultados indica solamente que no se han encontrado resultados:\n\n"

    hits = resultados.get("hits", {}).get("hits", [])
    if not hits:
        return "No se encontraron resultados para la consulta."
    for hit in hits:
        hotel = hit.get("_source", {})    
        nombre = hotel.get("nombre", "Nombre desconocido")
        localidad = hotel.get("localidad", "Localidad desconocida")
        provincia = hotel.get("provincia", "Provincia desconocida")
        descripcion = hotel.get("descripcion", "")
        servicios = ", ".join(hotel.get("servicios", []))
        opinion = hotel.get("opinion", "Sin opiniones")
        comentarios = hotel.get("comentarios", "sin comentarios")
        url = hotel.get("url", "sin URL")

        prompt += f"""Hotel {nombre}:

- Nombre: {nombre}
- Ubicación: {localidad}, {provincia}
- Descripción: {descripcion}
- Servicios: {servicios}
- Puntuación: {opinion} (basada en {comentarios} comentario/s)
- Más información: {url}

"""
    return prompt.strip()

def respuesta_natural(resultados) -> str:
    try:        
        respuesta = ollama.chat(
                model=OLLAMA_MODEL,
                messages=[{"role":"user", "content": resultados}],
                options={"temperature": 0.1}, 
            )
    except requests.exceptions.RequestException as e:
        print(f"Error iniciando Ollama: {e}")
        return None
    mensaje = respuesta.get("message", {})
    if mensaje:
        return mensaje.content.strip()
    else:
        return None
    
def main():
    pregunta_usuario = input("Pregunta sobre hoteles: ")
    consulta = generar_consulta_llm(pregunta_usuario)
    print("Consulta Elasticsearch generada:")
    print(json.dumps(consulta, indent=2))
    resultados = buscar_en_elasticsearch(consulta)
    prompt_hoteles = construir_prompt_multiple(resultados)
    respuesta = respuesta_natural(prompt_hoteles)
    print(respuesta)

if __name__ == "__main__":
    main()