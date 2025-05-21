import os
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from elasticsearch import Elasticsearch, helpers, NotFoundError
import requests
from IPython.display import Markdown, display
# requests is already imported once, removing duplicate
from getpass import getpass
import ollama # Import the ollama library
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

# Search template 
search_template_content = {
    "script": {
        "lang": "mustache",
        "source": '''{
query": {
    "bool": {
      "must": [
        {{#nombre}}{ "match": { "nombre": "{{nombre}}" } }{{/nombre}}{{#localidad}},{{/localidad}}
        {{#localidad}}{ "match": { "localidad": "{{localidad}}" } }{{/localidad}}{{#descripcion}},{{/descripcion}}
        {{#descripcion}}{ "match": { "descripcion": "{{descripcion}}" } }{{/descripcion}}{{#servicios}},{{/servicios}}
        {{#servicios}}{ "terms": { "servicios": {{#toJson}}servicios{{/toJson}} } }{{/servicios}}{{#mascotas}},{{/mascotas}}
        {{#mascotas}}{ "terms": { "mascotas": {{#toJson}}mascotas{{/toJson}} } }{{/mascotas}}{{#marca}},{{/marca}}
        {{#marca}}{ "term": { "marca": "{{marca}}" } }{{/marca}}{{#destacados}},{{/destacados}}
        {{#destacados}}{ "terms": { "destacados": {{#toJson}}destacados{{/toJson}} } }{{/destacados}}{{#fechaEntrada}},{{/fechaEntrada}}
        {{#fechaEntrada}}{
          "range": {
            "fechaEntrada": {
              "gte": "{{fechaEntrada}}"
            }
          }
        }{{/fechaEntrada}}{{#fechaSalida}},{{/fechaSalida}}
        {{#fechaSalida}}{
          "range": {
            "fechaSalida": {
              "lte": "{{fechaSalida}}"
            }
          }
        }{{/fechaSalida}}{{#precioMin}},{{/precioMin}}
        {{#precioMin}}{
          "range": {
            "precio": {
              "gte": {{precioMin}}
            }
          }
        }{{/precioMin}}{{#precioMax}},{{/precioMax}}
        {{#precioMax}}{
          "range": {
            "precio": {
              "lte": {{precioMax}}
            }
          }
        }{{/precioMax}}{{#opinionMin}},{{/opinionMin}}
        {{#opinionMin}}{
          "range": {
            "opinion": {
              "gte": {{opinionMin}}
            }
          }
        }{{/opinionMin}}
      ]{{#lat}},
      "filter": {
        "geo_distance": {
          "distancia": "{{distancia}}",
          "coordenadas": {
            "lat": {{lat}},
            "lon": {{lon}}
          }
        }
      }{{/lat}}
    }
  },
  "sort": [
    { "precio": "asc" }
  ]
}'''
}
}


def delete_search_template(template_id):
    """Deletes the search template if it exists"""
    try:
        es.delete_script(id=template_id)
        print(f"Deleted existing search template: {template_id}")
    except Exception as e:
        if "not_found" in str(e):
            print(f"Search template '{template_id}' not found, skipping delete.")
        else:
            print(f"Error deleting template '{template_id}': {e}")


def create_search_template(
    template_id=TEMPLATE_ID, template_content=search_template_content
):
    """Creates a new search template"""
    try:
        es.put_script(id=template_id, body=template_content)
        print(f"Created search template: {template_id}")
    except Exception as e:
        print(f"Error creating template '{template_id}': {e}")

def find_a_hotel(content):
    tools = [ # This definition remains the same as it describes the functions
        {
            "type": "function",
            "function": {
                "name": "extract_hotel_search_parameters",
                "description": "Extrae los parámetros de búsqueda para encontrar hoteles (excluyendo la pregunta).  Los parámetro se extraen de la pregunta",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
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
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "geocode_location",
                "description": "Resuelve la latitud y longitud de la localizacion.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "El nombre de la localización, p.ej., Cabo de Gata.",
                        }
                    },
                    "required": ["localizacion"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "query_elasticsearch",
                "description": "Consulta a Elasticsearch por hoteles basados en los parámetros obtenidos desde extract_hotel_search_parameters.  Debe llamar a la funcion extract_hotel_search_parameters antes de llamar a esta funcion. ",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "La pregunta original (e.g., 'hoteles cerca de Cabo de Gata').",
                        },
                        "nombre": {
                            "type": "string",
                            "description": "Nombre del hotel (p.ej., Hotel Playa).",
                        },
                        "localidad": {
                            "type": "string",
                            "description": "Localidad donde está situado el hotel (p.ej. Roquetas de Mar).",
                        },
                        "latitud": {
                            "type": "number",
                            "description": "Latitud de la localización.",
                        },
                        "longitud": {
                            "type": "number",
                            "description": "Longitud de la localización.",
                        },
                        "distancia": {
                            "type": "string",
                            "description": "Radio de búsqueda (p.ej., '5000m', '10km').",
                        },
                        "servicios": {
                            "type": "string",
                            "description": "servicios y destacados (p.ej., playa, gimnasio, piscina). Pueden ser varias opciones. Puede aparecer cualquier caracteristica del hotel.  Puede ser una lista extensa según la pregunta",
                        },
                    },
                    "required": ["query", "latitud", "longitud", "distancia"],
                },
            },
        },
    ]
    
    tools_json_str = json.dumps(tools)
    system_prompt_content = (
                "Eres un experto en hoteles que responde con precisión. El usuario te hará una pregunta y tú debes:\n"
                "1. Extraer los parámetros de búsqueda de la pregunta del usuario usando la función 'extract_hotel_search_parameters'.\n"
                "2. Si la pregunta incluye una localización, llama a 'geocode_location' para obtener la latitud y longitud.\n"
                "3. Usar la funcion 'query_elasticsearch' con los parámetros obtenidos en 1 y 2.\n"
                "Cuando use el parámetro 'servicios', formatea el valor como un array JSON (e.g., ['piscina', 'parking']). "
                "Responde solo con la información obtenida al llamar a la función 'query_elasticsearch'. "
                "Tienes disponibles estas funciones (no llames a otras que no aparezcan aquí):\n" + tools_json_str
        
    )
    messages = [
        {"role": "system", "content": system_prompt_content},
        {"role": "user", "content": content},
    ]

    parameters = {}
    while True:
        ollama_payload = {
            "model": OLLAMA_MODEL,
            "messages": messages,
            "stream": False,
            "format": "json", # Ask Ollama to output JSON directly
            "tools": tools # Add the tools definition
        }
        
        response_message_for_processing = {} # Initialize
        print(f"Using Ollama model: {OLLAMA_MODEL}")
        try:
            
            ollama_response_data = ollama.chat(
                model=OLLAMA_MODEL,
                messages=messages,
                tools=tools, 
                options={"temperature": 0.1}, 
            )
            
            assistant_message_data = ollama_response_data.get("message", {})
            response_message_for_processing = assistant_message_data
            if response_message_for_processing.get("tool_calls"):
                 for tool_call in response_message_for_processing["tool_calls"]:
                     if isinstance(tool_call.get("function", {}).get("arguments"), dict):
                         tool_call["function"]["arguments"] = json.dumps(tool_call["function"]["arguments"])


        except requests.exceptions.RequestException as e:
            print(f"Error calling Ollama: {e}")
            response_message_for_processing = {"role": "assistant", "content": f"Error interacting with Ollama: {e}"}
            messages.append(response_message_for_processing)
            break 
        except json.JSONDecodeError as e:
            raw_resp_text = ollama_response_data.get("text", "N/A") if isinstance(ollama_response_data, dict) else "N/A"
            print(f"Error decoding Ollama JSON response: {e}")
            print(f"Raw response text: {raw_resp_text}")
            response_message_for_processing = {"role": "assistant", "content": f"Error decoding Ollama response. Raw: {raw_resp_text[:200]}"}
            messages.append(response_message_for_processing)
            break

        # Manually construct the message dictionary to append to history
        message_to_append = {"role": response_message_for_processing.get("role")}
        if response_message_for_processing.get("content"):
            message_to_append["content"] = response_message_for_processing["content"]

        messages.append(message_to_append) # Append the constructed message

        # Check for tool calls
        if response_message_for_processing.get("tool_calls"):
            for tool_call in response_message_for_processing["tool_calls"]: # tool_call is a dict
                function_name = tool_call['function']['name']
                function_args_str = tool_call['function']['arguments'] 
                function_args = json.loads(function_args_str)

                if function_name == "extract_hotel_search_parameters":
                    print("Argu for extract_hotel_search_parameters:")
                    print(function_args)
                    function_response = handle_extract_hotel_search_parameters(function_args)
                    print("Response from handle_extract_hotel_search_parameters:")
                    print(function_response)
                    parameters.update(json.loads(function_response))
                    print("Updated parameters after extract_hotel_search_parameters:")
                    print(parameters)

                elif function_name == "query_elasticsearch":
                    if "query" not in parameters and "query" not in function_args : # check both, prefer function_args if present
                        print("Error: 'query' is required for Elasticsearch queries.")
                        # Append a message to ask for query or stop
                        tool_response_content = "Missing 'query' parameter for Elasticsearch. Cannot proceed."
                        messages.append({
                            "tool_call_id": tool_call.get("id"), # if tool_call is a dict
                            "role": "tool",
                            "name": function_name,
                            "content": tool_response_content,
                        })
                        continue # next tool call or next LLM iteration

                    print("Function Arguments for query_elasticsearch:")
                    print(function_args)
                    
                    # Consolidate parameters: function_args take precedence over globally stored 'parameters'
                    # for this specific call, but we should use what's directly passed by LLM for this func.
                    current_call_params = parameters.copy() # Start with general params
                    current_call_params.update(function_args) # Override with LLM provided for this call

                    function_response = call_elasticsearch(
                        query=current_call_params.get("query"),
                        nombre=current_call_params.get("nombre"),
                        latitud=parameters.get("latitud"),
                        longitud=parameters.get("longitud"),
                        distancia=current_call_params.get("distancia"),
                        localidad=current_call_params.get("localidad"), 
                        servicios=current_call_params.get("servicios")                                                                        
                    )

                elif function_name == "geocode_location":
                    function_response = geocode_location(
                        location=function_args.get("location")
                    )
# Add this block to update parameters with geocoded location
                    try:
                        geo_data = json.loads(function_response)
                        if "latitud" in geo_data and "longitud" in geo_data:
                            parameters["latitud"] = geo_data["latitud"]
                            parameters["longitud"] = geo_data["longitud"]
                            print(f"Updated parameters with geocoded location: {parameters}")
                    except json.JSONDecodeError:
                        print(f"Error decoding geocode response: {function_response}")
                else:
                    function_response = json.dumps({"error": f"Unknown function: {function_name}"})

                # Manually construct the tool result message dictionary to append to history
                tool_result_message = {
                    "tool_call_id": tool_call.get("id"),
                    "role": "tool",
                    "name": function_name,
                    "content": str(function_response), # Ensure content is a string
                }
                messages.append(tool_result_message)
                print_messages([tool_result_message]) # Display the tool result message
        else: # No tool calls, LLM provided a direct answer
            # Print the final response message
            print_messages([message_to_append])
            return # End of conversation

def format_message(message_data):
    role_style = {"user": "🧑", "assistant": "🤖", "system": "⚙️", "tool": "🛠️"} # Changed "function" to "tool"
    
    is_dict = isinstance(message_data, dict)
    
    role = message_data.get("role") if is_dict else getattr(message_data, "role", "unknown")
    content = message_data.get("content") if is_dict else getattr(message_data, "content", None)
    name = message_data.get("name") if is_dict else getattr(message_data, "name", None) # For tool role

    role_str = str(role if role is not None else "unknown")
    
    # Constructing the initial part of the message (role)
    formatted_message = f"{role_style.get(role_str, '❓')} **{role_str.upper()}"
    if role_str == "tool" and name:
        formatted_message += f" (Function: {name})"
    formatted_message += "**:\n"

    if content: # Content can be None for tool calls that are successfully processed by assistant
        formatted_message += f"{str(content)}\n"

    tool_calls = None
    if is_dict:
        tool_calls = message_data.get("tool_calls")
    elif hasattr(message_data, "tool_calls"): # For OpenAI-like message objects
        tool_calls = message_data.tool_calls
        
    if tool_calls:
        formatted_message += "Tool Calls:\n"
        for tool_call_item in tool_calls:
            is_tool_call_dict = isinstance(tool_call_item, dict)
            function_data = tool_call_item.get("function") if is_tool_call_dict else getattr(tool_call_item, "function", None)
            
            if function_data:
                is_function_data_dict = isinstance(function_data, dict)
                func_name = function_data.get("name") if is_function_data_dict else getattr(function_data, "name", "N/A")
                func_args_obj = function_data.get("arguments") if is_function_data_dict else getattr(function_data, "arguments", "N/A")
                func_args_str = str(func_args_obj) # arguments should be a JSON string

                formatted_message += (
                    f"  - Function: {func_name}\n"
                    f"    Arguments: {func_args_str}\n"
                )
            else:
                formatted_message += f"  - Malformed tool_call item: {str(tool_call_item)}\n"
    
    # For displaying tool responses (role: "tool")
    if role_str == "tool" and not tool_calls and content: # If it's a tool response message, content is already set
        pass # Already handled by the main content part for tool role

    return formatted_message


def print_messages(messages_list): # Renamed messages to messages_list to avoid conflict
    for msg in messages_list:
        print(format_message(msg))


def handle_extract_hotel_search_parameters(args):
    # This function remains largely the same, just ensure it returns a JSON string
    # For simplicity, assume it just returns the args as a JSON string.
    # You might have more complex logic here.
    print(f"handle_extract_hotel_search_parameters received: {args}")
    if args["distancia"] == "":
            args["distancia"] = "5000m"  # Default distance
    return json.dumps(args)


def call_elasticsearch(
    query, nombre=None, latitud=None, longitud=None, distancia=None, localidad=None, servicios=None
):
    """
    Query Elasticsearch using the search template and provided parameters.
    """
    params = {"query": query}
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

    try:
        # rendered = es.render_search_template(id=TEMPLATE_ID, params=params)
        # print(json.dumps(rendered["template_output"], indent=2))
     
        response = es.search(
                index=ES_INDEX,
                size=5,
                query={
                    "bool": {
                        "must": [
                            {
                                "match": {
                                    "localidad": localidad
                                }
                            },
                            {
                                "match": {
                                    "servicios": servicios  # Asegúrate de que `servicios` sea un string como "parking"
                                }
                            }
                        ],
                        "filter": [
                            {
                                "geo_distance": {
                                    "distance": "5km",  # Por ejemplo, "10km"
                                    "coordenadas": {
                                        "lat": latitud,
                                        "lon": longitud
                                    }
                                }
                            }
                        ]
                    }
                },
                sort=[
                    {
                        "_geo_distance": {
                            "coordenadas": {
                                "lat": latitud,
                                "lon": longitud
                            },
                            "order": "asc",
                            "unit": "km",
                            "mode": "min",
                            "distance_type": "arc"
                        }
                    }
                ]
            )
     #response = es.search_template(
        #    index=ES_INDEX, id=TEMPLATE_ID, params=params
        #)
        print("Elasticsearch response received.")
        # Process and return hits or a summary
        hits = response.get("hits", {}).get("hits", [])
        if not hits:
            return json.dumps({"message": "No hotels found matching your criteria."})

        results = []
        total_results = response.get("hits", {}).get("total", {}).get("value", 0)
        print(f"Number of results found: {total_results}")
        
        for hit in hits:
            fields = hit.get("fields", {})
            # Flatten fields if they are lists
            processed_fields = {k: (v[0] if isinstance(v, list) and len(v) > 0 else v) for k, v in fields.items()}
            results.append(processed_fields)
        
        return json.dumps({"results": results[:5]}) # Return top 5 results as JSON string

    except Exception as e:
        print(f"Error querying Elasticsearch: {e}")
        return json.dumps({"error": f"Error querying Elasticsearch: {str(e)}"})

def geocode_location(location):
    """Resolve a location to its latitude and longitude using Google Maps API."""
    geocode_url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": location, "key": google_maps_api_key}
    try:
        response = requests.get(geocode_url, params=params)
        response.raise_for_status()
        data = response.json()
        if data["status"] == "OK":
            lat = data["results"][0]["geometry"]["location"]["lat"]
            lng = data["results"][0]["geometry"]["location"]["lng"]
            print(f"Geocoded '{location}': lat={lat}, lng={lng}")
            return json.dumps({"latitud": lat, "longitud": lng})
        else:
            print(f"Error geocoding '{location}': {data['status']}")
            return json.dumps({"error": f"Geocoding failed for {location}: {data['status']}"})
    except requests.exceptions.RequestException as e:
        print(f"Error calling Geocoding API: {e}")
        return json.dumps({"error": f"Geocoding API request error: {str(e)}"})


if __name__ == "__main__":
    print("Starting hotel search application...")
    delete_search_template(TEMPLATE_ID) # Delete if exists
    create_search_template()

    print("\nHotel data loaded and Elasticsearch is ready.")
    print("Ask me about hotels! For example: 'Find hotels near the Eiffel Tower with a gym and a rating of at least 4 stars.'")
    #find_a_hotel("Find a hotel near Eiffel Tower with gym")
    while True:
        user_query = input("\nYour query (or type 'exit' to quit): ")
        if user_query.lower() == 'exit':
            break
        if not user_query.strip():
            print("Please enter a query.")
            continue
        find_a_hotel(user_query)
    
    print("Exiting application.")
