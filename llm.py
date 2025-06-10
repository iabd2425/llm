from datetime import datetime 
import logging
import os
import json
import re
from elasticsearch import Elasticsearch
from dotenv import load_dotenv

# Cargar entorno
load_dotenv()

# Elasticsearch config
ELASTICSEARCH_HOST = os.getenv('ELASTICSEARCH_HOST')
ELASTICSEARCH_PORT = os.getenv('ELASTICSEARCH_PORT')
ELASTICSEARCH_USERNAME = os.getenv('ELASTICSEARCH_USERNAME')
ELASTICSEARCH_PASSWORD = os.getenv('ELASTICSEARCH_PASSWORD')
ES_INDEX = os.getenv('ES_INDEX')
OUT_DIRECTORY = os.getenv('OUT_DIRECTORY')

# Ruta y modelo LLM
USE_OPEN_ROUTER = os.getenv('USE_OPEN_ROUTER', 'no').lower() == 'yes'

if USE_OPEN_ROUTER:
    from openai import OpenAI
    OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
    OPENROUTER_API_BASE = os.getenv('OPENROUTER_API_BASE')
    OPENROUTER_SITE_URL = os.getenv('OPENROUTER_SITE_URL')
    OPENROUTER_MODEL = os.getenv('OPENROUTER_MODEL')

    openai_client = OpenAI(
        base_url=OPENROUTER_API_BASE,
        api_key=OPENROUTER_API_KEY,
        default_headers={"HTTP-Referer": OPENROUTER_SITE_URL}
    )
else:
    import ollama
    import requests
    OLLAMA_MODEL = os.getenv('OLLAMA_MODEL')

# Elasticsearch connection
es = Elasticsearch(
    [f"http://{ELASTICSEARCH_HOST}:{ELASTICSEARCH_PORT}"],
    basic_auth=(ELASTICSEARCH_USERNAME, ELASTICSEARCH_PASSWORD)
)
es.info()

FEW_SHOT_PROMPT = """
Eres un experto en Elasticsearch. Dado el siguiente esquema de indice de hoteles, genera SOLO la consulta JSON valida para buscar detalles del hotel solicitado. No expliques nada ni pregunges, solo genera la consulta.

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
Pregunta: "Muustrame hoteles en Aguadulce con piscina y parking, ordenados por precio ascendente para el dia 01/06/2025."
Respuesta JSON:
{
  "query": {
    "bool": {
      "must": [
        { "match": { "localidad": "aguadulce" } },
        { "term": { "fechaEntrada":  "2025-06-01"  } },
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
  "sort": [
    { "precio": "asc" }
  ],
  "size": 10
}

Ejemplo 2:
Pregunta: "Dime hoteles que en Madrid disponibles el 10 de julio de 2025."
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

Ejemplo 4:
Pregunta: "¿Cual es el hotel mas barato de la provincia de Huelva?"
Respuesta JSON:
{
  "query": {
    "match": {
      "provincia": "Huelva"
    }
  },
  "sort": [
    { "precio": "asc" }
  ],
  "size": 1
}

Ejemplo 5:
Pregunta: "¿Cual es el hotel mas caro de Huelva?"
Respuesta JSON:
{
  "query": {
    "match": {
      "localidad": "Huelva"
    }
  },
  "sort": [
    { "precio": "desc" }
  ],
  "size": 1
}

Ahora, genera SOLO la consulta JSON para esta pregunta:
"{pregunta}"
"""

def configurar_logging():
    # Ruta a fichero logging
    log_filename = f"chatbot_{datetime.now().strftime('%Y%m%d')}.log"
    full_log_path = os.path.join(OUT_DIRECTORY, log_filename)

    #Crea el directorio de salida en caso de que no exista
    if not os.path.exists(OUT_DIRECTORY):
        os.makedirs(OUT_DIRECTORY)

    write_permission = False
    try:
        # Intenta abrir el fichero en modo append para comprobar los permisos de escritura
        # y se asegura de que el manejador del fichero se cierre inmediatamente después de la comprobación.
        with open(full_log_path, 'a') as f:
            pass
        write_permission = True
    except IOError as e:
        write_permission = False
        print(f"Warning: No se puede escribir en {full_log_path}. Revise los permisos de escritura. Error: {e}")

    # Configuración básica del logging
    logging.basicConfig(
        filename=full_log_path,  # Nombre del archivo de log (corrección aquí)
        level=logging.INFO,      # Nivel mínimo de mensajes que se guardarán
        format='%(asctime)s - CHATBOT - %(levelname)s - %(message)s'  # Formato del mensaje
    )

def extraer_json_valido(texto):
    try:
        match = re.search(r'\{.*\}', texto, re.DOTALL)
        if not match:
            raise ValueError("No se encontri bloque JSON.")
        return json.loads(match.group())
    except json.JSONDecodeError as e:
        print(" Error al parsear JSON:", e)
        print("Respuesta raw:\n", texto)
        return None

def generar_consulta_llm(pregunta: str) -> dict:
    prompt = FEW_SHOT_PROMPT.replace("{pregunta}", pregunta)

    if USE_OPEN_ROUTER:
        respuesta = openai_client.chat.completions.create(
            model=OPENROUTER_MODEL,
            messages=[{"role": "user", "content": prompt}],
            timeout=60
        )
        contenido = respuesta.choices[0].message.content
    else:
        try:
            respuesta = ollama.chat(
                model=OLLAMA_MODEL,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.1},
            )
            contenido = respuesta["message"]["content"]
        except requests.exceptions.RequestException as e:
            print(f" Error al llamar a Ollama: {e}")
            return None

    consulta = extraer_json_valido(contenido)
    json_comprimido = json.dumps(consulta, separators=(',', ':'))
    print("Respuesta raw del LLM:\n", json_comprimido)
    logging.info(f"Consulta generada: {json_comprimido}")
    return json_comprimido

def buscar_en_elasticsearch(consulta: dict):
    return es.search(index=ES_INDEX, body=consulta)

def construir_prompt_multiple(resultados) -> str:
    hits = resultados.get("hits", {}).get("hits", [])
    if not hits:
        return "No se encontraron resultados para la consulta."

    prompt = "Describe brevemente y en lenguaje natural los siguientes hoteles:\n\n"
    for hit in hits:
        hotel = hit["_source"]
        servicios = hotel.get("servicios", [])
        prompt += f"""Hotel {hotel.get('nombre', 'N/A')}:

- Provincia: {hotel.get('provincia', 'N/A')}
- Localidad: {hotel.get('localidad', 'N/A')} 
- Direccion: {hotel.get('direccion', 'N/A')}
- Descripcion: {hotel.get('descripcion', '')}
- Servicios: {', '.join(servicios) if isinstance(servicios, list) else servicios}
- Puntuacion: {hotel.get('opinion', 'Sin opiniones')} 
- Número de comentarios: ({hotel.get('comentarios', '0')} comentarios)
- Url: {hotel.get('url', 'N/A')}
- Precio: {hotel.get('precio', 'N/A')} EUR

"""
    return prompt.strip()

def respuesta_natural(texto_prompt: str) -> str:
    if USE_OPEN_ROUTER:
        respuesta = openai_client.chat.completions.create(
            model=OPENROUTER_MODEL,
            messages=[{"role": "user", "content": texto_prompt}],
            timeout=60
        )
        return respuesta.choices[0].message.content
    else:
        try:
            respuesta = ollama.chat(
                model=OLLAMA_MODEL,
                messages=[{"role": "user", "content": texto_prompt}],
                options={"temperature": 0.1}
            )
            return respuesta["message"]["content"].strip()
        except requests.exceptions.RequestException as e:
            print(f" Error al llamar a Ollama: {e}")
            return None

def main():
    configurar_logging()
    pregunta_usuario = input("Pregunta sobre hoteles: ")
    logging.info(f"Pregunta: {pregunta_usuario}")
    consulta = generar_consulta_llm(pregunta_usuario)
    if not consulta:
        return
    resultados = buscar_en_elasticsearch(consulta)
    prompt_hoteles = construir_prompt_multiple(resultados)
    respuesta = respuesta_natural(prompt_hoteles)
    print("\nRespuesta:\n", respuesta)
    logging.info("Respuesta: " + respuesta)

if __name__ == "__main__":
    main()