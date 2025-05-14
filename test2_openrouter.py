import requests
import json
import os

# --- Configuración ---
# Intenta obtener la API key de una variable de entorno.
# REEMPLAZA "TU_API_KEY_DE_OPENROUTER" si no usas variables de entorno.
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "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")

if OPENROUTER_API_KEY == "TU_API_KEY_DE_OPENROUTER":
    print("ADVERTENCIA: Por favor, reemplaza 'TU_API_KEY_DE_OPENROUTER' con tu API key real o configúrala como variable de entorno.")
    # Podrías querer salir aquí si es un script real: exit()

API_BASE_URL = "https://openrouter.ai/api/v1"
MODEL_TO_USE = "mistralai/mistral-small-3.1-24b-instruct:free" # Un modelo que soporte tool calling, como Mistral o GPTs

# --- Definición de nuestras herramientas (funciones locales) ---
def get_current_weather(location: str, unit: str = "celsius"):
    """
    Obtiene el clima actual para una ubicación dada.
    Simulación: Devuelve datos fijos para ciertas ciudades.
    """
    print(f"--- Función Python 'get_current_weather' llamada con location='{location}', unit='{unit}' ---")
    if "tokyo" in location.lower():
        return json.dumps({"location": location, "temperature": "10", "unit": unit, "forecast": "soleado con algunas nubes"})
    elif "san francisco" in location.lower():
        return json.dumps({"location": location, "temperature": "15", "unit": unit, "forecast": "parcialmente nublado"})
    elif "paris" in location.lower():
        return json.dumps({"location": location, "temperature": "12", "unit": unit, "forecast": "lluvioso"})
    else:
        return json.dumps({"location": location, "temperature": "22", "unit": unit, "forecast": "desconocido"})

# --- Herramientas disponibles para el LLM (formato JSON Schema) ---
# Esto es lo que le decimos al LLM sobre las herramientas que puede usar.
available_tools_for_llm = [
    {
        "type": "function",
        "function": {
            "name": "get_current_weather",
            "description": "Obtiene el clima actual en una ubicación específica.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "La ciudad y estado, ej. San Francisco, CA. Debe ser específico.",
                    },
                    "unit": {
                        "type": "string",
                        "enum": ["celsius", "fahrenheit"],
                        "description": "La unidad para la temperatura, por defecto es celsius."
                    },
                },
                "required": ["location"], # 'location' es obligatorio
            },
        },
    }
]

# --- Función principal para interactuar con OpenRouter ---
def chat_with_tools(user_query: str):
    """
    Realiza una conversación con el LLM, permitiéndole usar herramientas.
    """
    print(f"Usuario: {user_query}\n")

    messages = [
        {"role": "user", "content": user_query}
    ]

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    # --- PRIMERA LLAMADA A LA API: El LLM decide si usar una herramienta ---
    print("--- 1. Enviando petición inicial al LLM para que decida si usa una herramienta ---")
    payload_first_call = {
        "model": MODEL_TO_USE,
        "messages": messages,
        "tools": available_tools_for_llm,
        "tool_choice": "auto" # "auto" (default), "none", o {"type": "function", "function": {"name": "my_function"}}
    }

    try:
        response = requests.post(
            f"{API_BASE_URL}/chat/completions",
            headers=headers,
            json=payload_first_call
        )
        response.raise_for_status() # Lanza una excepción para códigos de error HTTP
        response_data = response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error en la petición a OpenRouter: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Detalles del error: {e.response.text}")
        return

    assistant_message = response_data['choices'][0]['message']
    messages.append(assistant_message) # Añadimos la respuesta del asistente al historial

    print(f"\nRespuesta del Asistente (puede solicitar llamada a herramienta):")
    print(json.dumps(assistant_message, indent=2, ensure_ascii=False))
    print("---")

    # --- PASO DE EJECUCIÓN DE HERRAMIENTA (si el LLM lo solicitó) ---
    if assistant_message.get("tool_calls"):
        tool_calls = assistant_message["tool_calls"]
        
        # Mapeo de nombres de función a funciones Python reales
        function_dispatch_table = {
            "get_current_weather": get_current_weather
        }

        tool_outputs = [] # Aquí guardaremos los resultados de las herramientas

        for tool_call in tool_calls:
            function_name = tool_call['function']['name']
            function_args_str = tool_call['function']['arguments']
            tool_call_id = tool_call['id']

            print(f"\nEl LLM quiere llamar a la función: '{function_name}' con argumentos: {function_args_str}")

            if function_name in function_dispatch_table:
                try:
                    function_args = json.loads(function_args_str)
                    # Llama a la función Python real
                    function_response_str = function_dispatch_table[function_name](**function_args)
                    
                    print(f"Respuesta de la función local '{function_name}': {function_response_str}")

                    tool_outputs.append({
                        "tool_call_id": tool_call_id,
                        "role": "tool",
                        "name": function_name,
                        "content": function_response_str # El contenido DEBE ser un string
                    })
                except Exception as e:
                    print(f"Error al ejecutar la función local '{function_name}': {e}")
                    tool_outputs.append({
                        "tool_call_id": tool_call_id,
                        "role": "tool",
                        "name": function_name,
                        "content": json.dumps({"error": str(e)}) # Informar al LLM del error
                    })
            else:
                print(f"Error: El LLM intentó llamar a una función desconocida: {function_name}")
                # Opcionalmente, podrías enviar un mensaje de error de vuelta al LLM
                tool_outputs.append({
                    "tool_call_id": tool_call_id,
                    "role": "tool",
                    "name": function_name,
                    "content": json.dumps({"error": f"Función '{function_name}' no encontrada."})
                })
        
        messages.extend(tool_outputs) # Añadimos los resultados de las herramientas al historial

        # --- SEGUNDA LLAMADA A LA API: Enviamos los resultados de las herramientas al LLM ---
        print("\n--- 2. Enviando resultados de las herramientas al LLM para obtener respuesta final ---")
        payload_second_call = {
            "model": MODEL_TO_USE,
            "messages": messages, # El historial ahora incluye la solicitud del usuario, la llamada a herramienta del LLM y los resultados de la herramienta.
            "tools": available_tools_for_llm # Es buena práctica reenviar las herramientas por si el LLM necesita otra.
        }
        print("\nMensajes enviados en la segunda llamada:")
        print(json.dumps(messages, indent=2, ensure_ascii=False))


        try:
            response_final = requests.post(
                f"{API_BASE_URL}/chat/completions",
                headers=headers,
                json=payload_second_call
            )
            response_final.raise_for_status()
            response_final_data = response_final.json()
        except requests.exceptions.RequestException as e:
            print(f"Error en la segunda petición a OpenRouter: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Detalles del error: {e.response.text}")
            return

        final_assistant_response = response_final_data['choices'][0]['message']
        print("\nRespuesta final del Asistente (después de usar la herramienta):")
        print(json.dumps(final_assistant_response, indent=2, ensure_ascii=False))
        if final_assistant_response.get("content"):
             print(f"\nRespuesta final procesada: {final_assistant_response['content']}")
        print("---")

    elif assistant_message.get("content"):
        # El LLM respondió directamente sin usar herramientas
        print(f"\nRespuesta directa del Asistente (sin usar herramientas): {assistant_message['content']}")
        print("---")
    else:
        print("\nEl Asistente no devolvió contenido ni solicitó herramientas. Respuesta inesperada:")
        print(json.dumps(assistant_message, indent=2, ensure_ascii=False))
        print("---")


# --- Ejecutar el ejemplo ---
if __name__ == "__main__":
    # Ejemplo 1: Pregunta que debería usar la herramienta
    # chat_with_tools("¿Cómo está el clima en Tokyo hoy?")
    
    # Ejemplo 2: Pregunta que podría requerir múltiples llamadas a herramientas
    chat_with_tools("¿Cómo está el clima en San Francisco y en Paris? ¿Qué unidad de temperatura usa cada uno por defecto?")

    # Ejemplo 3: Pregunta que probablemente no use la herramienta
    # chat_with_tools("Hola, ¿cómo estás?")
    
    # Ejemplo 4: Pregunta con una ubicación no cubierta por la función simulada
    # chat_with_tools("¿Cómo está el clima en Buenos Aires?")