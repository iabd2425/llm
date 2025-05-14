import os
import json
# Removed: from openai import AzureOpenAI
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from elasticsearch import Elasticsearch, helpers, NotFoundError
import requests
from IPython.display import Markdown, display
# requests is already imported once, removing duplicate
from getpass import getpass
import ollama # Import the ollama library

# Elasticsearch local connection
# Removed: es_cloud_id = getpass(prompt="Enter your Elasticsearch Cloud ID: ")
# Removed: es_api_key = getpass(prompt="Enter your Elasticsearch API key: ")
es = Elasticsearch(['http://localhost:9200'], basic_auth=('elastic', '9cKxyfj9')) # Default local ES

es.info()

# Ollama Configuration
OLLAMA_BASE_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "llama3.2:1b"  # You can change this to your preferred Ollama model

# Removed Azure OpenAI Configuration
# ENDPOINT = getpass("Azure OpenAI Completions Endpoint: ")
# AZURE_API_KEY = getpass("Azure OpenAI API Key: ")
# DEPLOYMENT_NAME = getpass("Azure OpenAI Deployment Name: ")
# deployment_name = DEPLOYMENT_NAME # This variable is no longer used
# API_VERSION = getpass("Completions Endpoint API Version: ")
# client = AzureOpenAI(...) # Removed

##create google maps api key here: https://developers.google.com/maps/documentation/embed/get-api-key
#GMAPS_API_KEY = getpass(prompt="Enter Google Maps API Key: ")
google_maps_api_key = "AIzaSyB-yBrRX8KsYrVEJkrtOV-cT6rVVaJw9TI"

# Elastic index
ES_INDEX = "hotels"
TEMPLATE_ID = "hotel_search_template"

# JSON dataset URL
DATASET_URL = "https://ela.st/hotels-dataset"

ELSER_ENDPOINT_NAME = "my-elser-endpoint"
E5_ENDPOINT_NAME = "my-e5-endpoint"


# Define the index mapping
INDEX_MAPPING = {
    "mappings": {
        "properties": {
            "Address": {"type": "text"},
            "Attractions": {"type": "text"},
            "Description": {"type": "text"},
            "FaxNumber": {"type": "text"},
            "HotelCode": {"type": "long"},
            "HotelFacilities": {"type": "text"},
            "HotelName": {"type": "text"},
            "HotelRating": {"type": "long"},
            "HotelWebsiteUrl": {"type": "keyword"},
            "Map": {"type": "keyword"},
            "PhoneNumber": {"type": "text"},
            "PinCode": {"type": "keyword"},
            "cityCode": {"type": "long"},
            "cityName": {"type": "text"},
            "combined_fields": {
                "type": "text",
                "copy_to": ["semantic_description_elser", "semantic_description_e5"],
            },
            "countryCode": {"type": "keyword"},
            "countryName": {"type": "keyword"},
            "latitude": {"type": "double"},
            "location": {"type": "geo_point"},
            "longitude": {"type": "double"},
            "semantic_description_e5": {
                "type": "semantic_text",
                "inference_id": E5_ENDPOINT_NAME,
            },
            "semantic_description_elser": {
                "type": "semantic_text",
                "inference_id": ELSER_ENDPOINT_NAME,
            },
        }
    }
}

def create_inferencing_endpoints():
    endpoints = [
        {
            "inference_id": ELSER_ENDPOINT_NAME,
            "task_type": "sparse_embedding",
            "body": {
                "service": "elasticsearch",
                "service_settings": {
                    "num_allocations": 2,
                    "num_threads": 1,
                    "model_id": ".elser_model_2_linux-x86_64",
                },
                "chunking_settings": {
                    "strategy": "sentence",
                    "max_chunk_size": 250,
                    "sentence_overlap": 1,
                },
            },
        },
        {
            "inference_id": E5_ENDPOINT_NAME,
            "task_type": "text_embedding",
            "body": {
                "service": "elasticsearch",
                "service_settings": {
                    "num_allocations": 2,
                    "num_threads": 1,
                    "model_id": ".multilingual-e5-small",
                },
                "chunking_settings": {
                    "strategy": "sentence",
                    "max_chunk_size": 250,
                    "sentence_overlap": 1,
                },
            },
        },
    ]

    for endpoint in endpoints:
        try:
            es.inference.delete(inference_id=endpoint["inference_id"], force=True)
            print(f"Deleted endpoint '{endpoint['inference_id']}'")
        except NotFoundError:
            print(
                f"Endpoint '{endpoint['inference_id']}' does not exist. Skipping deletion."
            )

        response = es.inference.put(
            inference_id=endpoint["inference_id"],
            task_type=endpoint["task_type"],
            body=endpoint["body"],
            request_timeout=60 # Increased timeout
        )
        print(f"Created endpoint '{endpoint['inference_id']}': {response}")

# Step 1: Create the index with mapping
def create_index():
    try:
        if es.indices.exists(index=ES_INDEX):
            print(f"Index '{ES_INDEX}' already exists. Deleting and recreating...")
            es.indices.delete(index=ES_INDEX)

        es.indices.create(index=ES_INDEX, body=INDEX_MAPPING)
        print(f"Index '{ES_INDEX}' created successfully.")
    except Exception as e:
        print(f"Error creating index: {e}")
        exit(1)


# Step 2: Download the JSON file
def download_json():
    """Reads JSON records from a local file."""
    file_path = "hotels-02-18-2025.json"  # Assuming the file is in the current directory
    print(f"Reading dataset from local file: {file_path}")

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            # Return a generator that yields lines from the file
            for line in f:
                yield line.strip() # Use yield to return an iterator
    except FileNotFoundError:
        print(f"Error: Local file not found at {file_path}")
        # Depending on desired behavior, you might want to exit or handle differently
        exit(1)
    except Exception as e:
        print(f"Error reading local file {file_path}: {e}")
        exit(1)


# Step 3: Ingest JSON records into Elasticsearch
def ingest_data():
    print("Ingesting data into Elasticsearch...")
    actions = []

    for line in download_json():
        if line:
            record = json.loads(line)
            if "latitude" in record and "longitude" in record:
                record["location"] = {
                    "lat": record["latitude"],
                    "lon": record["longitude"],
                }

            actions.append({"_index": ES_INDEX, "_source": record})

            if len(actions) >= 50:
                try:
                    helpers.bulk(es, actions, request_timeout=80) # Increased timeout
                    print(f"Ingested {len(actions)} records...")
                    actions = []
                except helpers.BulkIndexError as e:
                    print(f"Bulk indexing failed for {len(e.errors)} documents:")
                    for error in e.errors:
                        print(json.dumps(error, indent=2))
                    # Depending on desired behavior, you might want to re-raise or handle differently
                    # For now, we'll print and continue to see if other batches fail
                    actions = [] # Clear actions to avoid retrying the same failed batch

    if actions:
        try:
            helpers.bulk(es, actions, request_timeout=80) # Increased timeout
            print(f"Ingested {len(actions)} remaining records.")
        except helpers.BulkIndexError as e:
            print(f"Bulk indexing failed for {len(e.errors)} remaining documents:")
            for error in e.errors:
                print(json.dumps(error, indent=2))
            # Re-raise the exception after printing details if you want the script to stop
            # raise e # Uncomment to re-raise

    print("Data ingestion complete.")

# Search template content
search_template_content = {
    "script": {
        "lang": "mustache",
        "source": """{
            "_source": false,
            "fields": ["HotelName", "HotelRating", "countryName", "cityName", "countryCode", "Attractions"],
            "retriever": {
                "standard": {
                    "query": {
                        "semantic": {
                            "field": "semantic_description_elser",
                            "query": "{{query}}"
                        }
                    },
                    "filter": {
                        "bool": {
                            "must": [
                                {{#distance}}{
                                    "geo_distance": {
                                        "distance": "{{distance}}",
                                        "location": {
                                            "lat": {{latitude}},
                                            "lon": {{longitude}}
                                        }
                                    }
                                }{{/distance}}
                                {{#rating}}{{#distance}},{{/distance}}{
                                    "range": {
                                        "HotelRating": {
                                            "gte": {{rating}}
                                        }
                                    }
                                }{{/rating}}
                                {{#countryName}}{{#distance}}{{^rating}},{{/rating}}{{/distance}}{{#rating}},{{/rating}}{
                                    "term": {
                                        "countryName": "{{countryName}}"
                                    }
                                }{{/countryName}}
                                {{#city}}{{#distance}}{{^rating}},{{/rating}}{{/distance}}{{#rating}},{{/rating}}{
                                    "match": {
                                        "cityName": "{{city}}"
                                    }
                                }{{/city}}
                                {{#countryCode}}{{#distance}}{{^rating}},{{/rating}}{{/distance}}{{#rating}},{{/rating}}{
                                    "term": {
                                        "countryCode": "{{countryCode}}"
                                    }
                                }{{/countryCode}}
                                {{#distance}}{{^rating}}{{/rating}}{{/distance}}{{#rating}}{{/rating}}
                            ],
                            "should": [
                                {{#attraction}}{
                                    "wildcard": {
                                        "Attractions": {
                                            "value": "*{{attraction}}*",
                                            "case_insensitive": true
                                        }
                                    }
                                }{{/attraction}}
                            ]
                        }
                    }
                }
            }
        }""",
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
                "description": "Extract search parameters for finding hotels (excluding the query itself).  the parameters are extracted from the input query",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "the full input query",
                        },
                        "distance": {
                            "type": "string",
                            "description": "The search radius (e.g., 500m, 1000m).",
                        },
                        # "rating": {
                        #     "type": "number",
                        #     "description": "The minimum hotel rating (e.g., 3, 4, or 5 stars).",
                        # },
                        "location": {
                            "type": "string",
                            "description": "Location mentioned in the query (e.g., Belongil Beach, Byron Bay).",
                        },
                        "countryName": {
                            "type": "string",
                            "description": "Name of the country (e.g., Australia, Germany).",
                        },
                        "city": {
                            "type": "string",
                            "description": "City name (e.g., Byron Bay, Chicago, Houston).",
                        },
                        "State": {
                            "type": "string",
                            "description": "State or province (e.g., Texas, Alaska, Alberta).",
                        },
                        "countryCode": {
                            "type": "string",
                            "description": "The country code (e.g., AU for Australia).",
                        },
                        "attraction": {
                            "type": "string",
                            "description": "Hotel attractions, amenities, or descriptive terms (e.g., Beach, Museum, gym, modern, luxurious). This can include multiple options.",
                        },
                    },
                    "required": ["query", "attraction"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "geocode_location",
                "description": "Resolve a location to its latitude and longitude.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "The name of the location, e.g., Belongil Beach.",
                        }
                    },
                    "required": ["location"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "query_elasticsearch",
                "description": "Query Elasticsearch for accommodations based on provided parameters from extract_hotel_search_parameters.  Must call extract_hotel_search_parameters prior to call this function ",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The original search query (e.g., 'hotels near Belongil Beach').",
                        },
                        "latitude": {
                            "type": "number",
                            "description": "Latitude of the location.",
                        },
                        "longitude": {
                            "type": "number",
                            "description": "Longitude of the location.",
                        },
                        "distance": {
                            "type": "string",
                            "description": "Search radius (e.g., '5000m', '10km').",
                        },
                        # "rating": {
                        #     "type": "number",
                        #     "description": "Minimum hotel rating (e.g., 3, 4, 5 stars).",
                        # },
                        "countryName": {
                            "type": "string",
                            "description": "The country name (e.g., 'Australia', 'United States').",
                        },
                        "countryCode": {
                            "type": "string",
                            "description": "The country code (e.g., 'AU', 'US').",
                        },
                        "attraction": {
                            "type": "string",
                            "description": "hotel attractions or amenity (e.g., Beach, Museum, gym, coffee shop, pool). This can be muliple options. Any feature of a hotel can be used here.  Attractions in the query may be obvious so this can be a comprehensive list",
                        },
                    },
                    "required": ["query"],
                },
            },
        },
    ]
    
    tools_json_str = json.dumps(tools)
    system_prompt_content = (
        "You are an assistant that helps find hotels based on user queries by using available tools. "
        "Follow these steps:\n"
        "1. First, use the `extract_hotel_search_parameters` tool to get the search criteria from the user's query.\n"
        "2. If a location is provided in the extracted parameters, use the `geocode_location` tool to get the latitude and longitude for that location.\n"
        "3. Finally, use the `query_elasticsearch` tool with all the gathered information (query, location coordinates if available, distance, attractions, etc.) to find matching hotels.\n"
        "4. Provide recommendations based *only* on the results from the `query_elasticsearch` tool. Do not make up information.\n\n"
        "The last answer must explain in natural language the result from `query_elasticsearch` tool. Avoid to mention query_elasticsearch. \n"
        "If you need to call a function, respond *only* with a single JSON object in the following format, and nothing else before or after it:\n"
        '```json\n{"tool_call": {"name": "function_name", "arguments": {"arg1": "value1", ...}}}\n```\n'
        "The 'arguments' should be an object.\n\n"
        "Available functions (do not call functions not listed here):\n" + tools_json_str
        
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

        try:
            # Use ollama.chat for tool calling
            ollama_response_data = ollama.chat(
                model=OLLAMA_MODEL,
                messages=messages,
                tools=tools, # Pass the tools definition
                options={"temperature": 0.0}, # Optional: control creativity
            )
            
            # The response structure from ollama.chat is similar to OpenAI's
            assistant_message_data = ollama_response_data.get("message", {})
            response_message_for_processing = assistant_message_data
            # Ensure tool_calls is a list if present, and arguments are strings
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
            raw_resp_text = api_response.text if 'api_response' in locals() and hasattr(api_response, 'text') else "N/A"
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
                    print("Function Arguments for extract_hotel_search_parameters:")
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
                        latitude=parameters.get("latitude"),
                        attraction=current_call_params.get("attraction"),
                        longitude=parameters.get("longitude"),
                        distance=current_call_params.get("distance"),
                        rating=current_call_params.get("rating"),
                        country_name=current_call_params.get("countryName"), # Note: case difference with `country_name` in call_elasticsearch
                        country_code=current_call_params.get("countryCode")
                    )

                elif function_name == "geocode_location":
                    function_response = geocode_location(
                        location=function_args.get("location")
                    )
# Add this block to update parameters with geocoded location
                    try:
                        geo_data = json.loads(function_response)
                        if "latitude" in geo_data and "longitude" in geo_data:
                            parameters["latitude"] = geo_data["latitude"]
                            parameters["longitude"] = geo_data["longitude"]
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
    return json.dumps(args)


def call_elasticsearch(
    query, latitude=None, longitude=None, distance=None, rating=None, country_name=None, country_code=None, attraction=None
):
    """
    Query Elasticsearch using the search template and provided parameters.
    """
    params = {"query": query}
    if latitude is not None and longitude is not None:
        params["latitude"] = latitude
        params["longitude"] = longitude
    if distance:
        params["distance"] = distance
    if rating:
        params["rating"] = rating
    if country_name:
        params["countryName"] = country_name # Ensure key matches template
    if country_code:
        params["countryCode"] = country_code
    if attraction:
        params["attraction"] = attraction
    
    print(f"Elasticsearch search_template params: {params}")

    try:
        response = es.search_template(
            index=ES_INDEX, id=TEMPLATE_ID, params=params
        )
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
            return json.dumps({"latitude": lat, "longitude": lng})
        else:
            print(f"Error geocoding '{location}': {data['status']}")
            return json.dumps({"error": f"Geocoding failed for {location}: {data['status']}"})
    except requests.exceptions.RequestException as e:
        print(f"Error calling Geocoding API: {e}")
        return json.dumps({"error": f"Geocoding API request error: {str(e)}"})


if __name__ == "__main__":
    print("Starting hotel search application...")
#    create_inferencing_endpoints()
#    create_index()
#    ingest_data()
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
