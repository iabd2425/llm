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



def call_elasticsearch(
    pregunta, nombre=None, latitud=None, longitud=None, distancia=None, localidad=None, servicios=None
):
    """
    Query Elasticsearch using the search template and provided parameters.
    """
    params = {"pregunta": pregunta}
    if latitud is not None and longitud is not None:
        params["latitud"] = latitud
        params["longitud"] = longitud
    if nombre:
        params["nombre"] = nombre
    if distancia:
        params["distancia"] = "5km"
    if localidad:
        params["localidad"] = localidad 
    if servicios:
        params["servicios"] = servicios
    
    print(f"Elasticsearch search_template params: {params}")

    elastic_query = {
                    "bool": {
                        "must": [
                            {
                                "match": {
                                    "localidad": localidad
                                }
                            },
                            {
                                "match": {
                                    "servicios": servicios  
                                }
                            }
                        ],
                    }
                }
    print (elastic_query)
    try:
        response = es.search(
                index=ES_INDEX,
                size=5,
                query=elastic_query
            )
        print("Elasticsearch response received.")
        # Process and return hits or a summary
        hits = response["hits"]["hits"]
        if not hits:
            return json.dumps({"message": "No hotels found matching your criteria."})

        resultados = []
        total_results = response.get("hits", {}).get("total", {}).get("value", 0)
        print(f"Number of results found: {total_results}")
        
        for hit in hits:   
            hotel = {
                "nombre": hit["_source"].get("nombre", ""),
                "marca": hit["_source"].get("marca", ""),
                "ubicacion": hit["_source"].get("ubicacion", ""),
                "descripcion": hit["_source"].get("descripcion", ""),
                "servicios": hit["_source"].get("servicios", []),
                "mascotas": hit["_source"].get("mascotas", ""),
                "coordenadas": hit["_source"].get("coordenadas", ""),
                "puntuacion": hit["_source"].get("puntuacion", ""),
                "opinion": hit["_source"].get("opinion", ""),
                "numero_comentarios": hit["_source"].get("numero_comentarios", ""),
                "url": hit["_source"].get("url", ""),
                "precio": hit["_source"].get("precio", ""),
            }
            resultados.append(hotel)
        return json.dumps({"encontrados" : total_results, "resultados": resultados}) 

    except Exception as e:
        print(f"Error querying Elasticsearch: {e}")
        return json.dumps({"error": f"Error querying Elasticsearch: {str(e)}"})

tool_extraer_parametros = [ 
    {
        "type": "function",
        "function": {
            "name": "extract_hotel_search_parameters",
            "description": "Extrae de la pregunta los parámetros de búsqueda para encontrar hoteles (excluyendo la propia pregunta)",
            "parameters": {
                "type": "object",
                "properties": {
                    "pregunta": {
                        "type": "string",
                        "description": "La pregunta completa",
                    },
                    "nombre": {
                        "type": "string",
                        "description": "Nombre del hotel (p.ej., Hotel Playa).",
                    },
                    "distancia": {
                        "type": "string",
                        "description": "El radio de distancia (p.ej., 500m, 1000m).",
                    },
                    "opinionMin": {
                        "type": "number",
                        "description": "La nota de opinión mínima  (p.ej, 5, 8, o 9).",
                    },
                    "localidad": {
                        "type": "string",
                        "description": "Localidad donde está situado el hotel (p.ej. Roquetas de Mar).",
                    },
                    "marca": {
                        "type": "string",
                        "description": "Marca o grupo hotelero (p.ej., Senator, Meliá).",
                    },
                    "mascotas": {
                        "type": "string",
                        "description": "Si el hotel acepta mascotas (p.ej., 'sí', 'no').",
                    },
                    "servicios": {
                        "type": "string",
                        "description": "Servicios y caracteristicas (p.ej., piscina, gimnasio, parking)",
                    },
                },
                "required": ["pregunta"],
            },
        },
    },
]


user_query = input("Pregunta:")

mensajes = [
        {
            "role": "system",
            "content": (
                "Eres un asistente para extraer parámetros de búsqueda de hoteles "
                "No fabriques información ni respondas en base a suposiciones."
                "Utiliza la herramienta extract_hotel_search_parameters para extraer los parámetros de búsqueda de la pregunta del usuario."                
            ),
        },
        {"role": "user", "content": user_query},
    ]

parameters = {}
while True:
    # Call the LLM with tools
    response = ollama.chat(
        model=OLLAMA_MODEL,
        messages=mensajes,
        tools=tool_extraer_parametros        
        )
    response_message = response.get("message", {})
    print("Respuesta del LLM:", response_message)

    # Print formatted messages for debugging
    #print_messages([response_message])

    # Check for tool calls
    if response_message.tool_calls:
        for tool_call in response_message.tool_calls:
            function_name = tool_call.function.name
            function_args = json.dumps(tool_call["function"]["arguments"])

            if function_name == "extract_hotel_search_parameters":
                # Debug: Print function_args
                print("Function Arguments for extract_hotel_search_parameters:")
                print(function_args)

                # Extract required and optional parameters
               # function_response = handle_extract_hotel_search_parameters(
               #     function_args
               # )

                # Debug: Print function_response
                #print("Response from handle_extract_hotel_search_parameters:")
                #print(function_response)

                parameters.update(json.loads(function_args))

                # Debug: Print updated parameters
                print("Updated parameters after extract_hotel_search_parameters:")
                print(parameters)

            function_response = call_elasticsearch(
                pregunta=parameters.get("pregunta"),
                nombre=parameters.get("nombre"),
                latitud=parameters.get("latitud"),
                longitud=parameters.get("longitud"),
                distancia=parameters.get("distancia"),
                localidad=parameters.get("localidad"), 
                servicios=parameters.get("servicios")                                                                        
            )

            mensajes = [
            {
                "role": "system",
                    "content": (
                        "Eres un recomendador de hoteles. "
                        "No inventes información ni respondas en base a suposiciones. Muestra respuestas concisas, claras y escuetas."
                        "Dados los resultados de la entrada del usuario, generame una respuesta en lenguage natural"                
                    ),
                },
                {"role": "user", "content": function_response},
            ]

            response = ollama.chat(
                model=OLLAMA_MODEL,
                messages=mensajes,
                )
            response_message = response.get("message", {})
            print("Response from LLM:", response_message)



    else:
        # If no further tools are requested, break the loop
        break
