
# LLM - Buscador de Hoteles con Elasticsearch y Modelos de Lenguaje

Este proyecto es una aplicación de línea de comandos que permite realizar consultas sobre un índice de Elasticsearch con datos de hoteles. Utiliza un modelo de lenguaje (LLM) para transformar preguntas en consultas JSON válidas para Elasticsearch y para generar respuestas en lenguaje natural basadas en los resultados obtenidos.

---

## Características principales

- Traduce preguntas naturales sobre hoteles en consultas Elasticsearch usando un modelo LLM (OpenRouter o Ollama).
- Soporta diferentes modelos configurables mediante variables de entorno.
- Consulta un índice Elasticsearch con datos de hoteles.
- Genera descripciones naturales y resumidas de los hoteles encontrados.
- Compatible con autenticación básica para Elasticsearch.
- Ejecución sencilla desde consola.

---

## Esquema esperado en Elasticsearch

El índice debe tener los siguientes campos (tipos indicados):

- `nombre`: text  
- `provincia`: text  
- `localidad`: text  
- `servicios`: text (puede ser lista)  
- `location`: geo_point  
- `descripcion`: text  
- `precio`: integer  
- `fechaEntrada`: date (formato yyyy-MM-dd)  
- `opinion`: float  
- `comentarios`: integer  
- `url`: text (opcional)  

---

## Requisitos

- Python 3.8+  
- Elasticsearch corriendo y accesible  
- Cuenta y claves API para OpenRouter o modelo Ollama (opcional)  
- Variables de entorno configuradas (ver sección Configuración)

---

## Instalación

```bash
pip install elasticsearch python-dotenv openai ollama requests
```

---

## Configuración (variables de entorno)

Crea un archivo `.env` con al menos las siguientes variables:

```env
ELASTICSEARCH_HOST=localhost
ELASTICSEARCH_PORT=9200
ELASTICSEARCH_USERNAME=usuario
ELASTICSEARCH_PASSWORD=contraseña
ES_INDEX=nombre_del_indice

USE_OPEN_ROUTER=yes  # o "no"
OPENROUTER_API_KEY=tu_api_key
OPENROUTER_API_BASE=https://api.openrouter.ai/v1
OPENROUTER_SITE_URL=https://tu_sitio
OPENROUTER_MODEL=gpt-4o-mini

OLLAMA_MODEL=nombre_modelo_ollama
```

- Si `USE_OPEN_ROUTER` es `yes`, se usará OpenRouter.  
- Si es `no`, se usará Ollama localmente.

---

## Uso

Ejecuta el script principal:

```bash
python llm.py
```

Ingresa una pregunta sobre hoteles, por ejemplo:

```
Muéstrame hoteles en Málaga con piscina y parking para el 01/06/2025.
```

El sistema generará una consulta Elasticsearch, la ejecutará, y te devolverá una descripción natural de los hoteles encontrados.

---

## Funcionamiento interno

- **Generación de consulta:** Se construye un prompt con ejemplos (few-shot) para que el LLM genere una consulta JSON válida para Elasticsearch.  
- **Consulta Elasticsearch:** Se ejecuta la consulta generada sobre el índice configurado.  
- **Construcción de prompt para respuesta:** Los resultados obtenidos se convierten en un prompt con detalles de hoteles para generar la respuesta final en lenguaje natural.  
- **Respuesta natural:** El LLM genera un texto amigable explicando los hoteles encontrados.

---

## Funciones principales

- `generar_consulta_llm(pregunta: str) -> dict`: genera la consulta JSON para Elasticsearch a partir de la pregunta.  
- `buscar_en_elasticsearch(consulta: dict)`: ejecuta la consulta en Elasticsearch y devuelve resultados.  
- `construir_prompt_multiple(resultados) -> str`: crea el texto para que el LLM genere la respuesta natural.  
- `respuesta_natural(texto_prompt: str) -> str`: genera la respuesta final en lenguaje natural usando el LLM.  

---

## Ejemplo de prompt generado (simplificado)

```json
{
  "query": {
    "bool": {
      "must": [
        { "match": { "localidad": "Málaga" } },
        { "term": { "fechaEntrada": "2025-06-01" } },
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
```

---

## Licencia

[Indica aquí la licencia del proyecto, si aplica]

---

## Autor

[iabd2425](https://github.com/iabd2425)

---

¿Quieres ayuda para documentar más funcionalidades o crear scripts adicionales? ¡Dímelo!
