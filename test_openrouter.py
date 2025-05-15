import os
import json
from openai import OpenAI, APIError, APIStatusError, APIConnectionError, RateLimitError, AuthenticationError
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from elasticsearch import Elasticsearch, helpers, NotFoundError
import requests
from dotenv import load_dotenv


# Cargar las variables desde el archivo .env
load_dotenv()

OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
OPENROUTER_API_BASE = os.getenv('OPENROUTER_API_BASE')
OPENROUTER_SITE_URL = os.getenv('OPENROUTER_SITE_URL')
OPENROUTER_MODEL = os.getenv('OPENROUTER_MODEL', 'gpt-3.5-turbo-16k') # Default to gpt-3.5-turbo-16k if not set

ELASTICSEARCH_HOST = os.getenv('ELASTICSEARCH_HOST')
ELASTICSEARCH_PORT = os.getenv('ELASTICSEARCH_PORT')
ELASTICSEARCH_USERNAME = os.getenv('ELASTICSEARCH_USERNAME')
ELASTICSEARCH_PASSWORD = os.getenv('ELASTICSEARCH_PASSWORD') 

# Elasticsearch local connection
hosts = f"http://{ELASTICSEARCH_HOST}:{ELASTICSEARCH_PORT}"
es = Elasticsearch([hosts], basic_auth=('elastic', 'r4iKdEp3')) # Default local ES
es.info()

# Elastic index
ES_INDEX = os.getenv('ES_INDEX')
TEMPLATE_ID = os.getenv('TEMPLATE_ID')

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
    
    system_prompt_content = (
        "You are an assistant that helps find hotels based on user queries by using available tools. "
        "Follow these steps:\n"
        "1. First, use the `extract_hotel_search_parameters` tool to get the search criteria from the user's query.\n"
        "2. Second, use the `query_elasticsearch` tool with all the gathered information (query, location coordinates if available, distance, attractions, etc.) to find matching hotels.\n"
        "Provide recommendations based *only* on the results from the `query_elasticsearch` tool. Do not make up information.\n\n"
        "The last answer must explain in natural language the result from `query_elasticsearch` tool. Avoid to mention query_elasticsearch. \n"
        "When you need to call a function, use the provided tools. The 'arguments' for the function should be an object."
        
    )
    messages = [
        {"role": "system", "content": system_prompt_content},
        {"role": "user", "content": content},
    ]

    # Initialize OpenAI client for OpenRouter
    openai_client = OpenAI(
        base_url=OPENROUTER_API_BASE,
        api_key=OPENROUTER_API_KEY,
        default_headers={ # Recommended headers for OpenRouter
            "HTTP-Referer": OPENROUTER_SITE_URL,
            # "X-Title": "Your App Name" # Optional
        }
    )
    
    parameters = {} # To store extracted parameters across calls if needed by logic

    while True:
        assistant_message_obj = None # Will hold the ChatCompletionMessage object from SDK

        try:
            print(f"Sending request to OpenRouter with model: {OPENROUTER_MODEL}")
            # print_messages(messages) # Uncomment for debugging message history

            completion = openai_client.chat.completions.create(
                model=OPENROUTER_MODEL,
                messages=messages,
                tools=tools,
                #tool_choice="required", # Explicitly set tool_choice, "auto" is default
                timeout=60 # Timeout for the API call
            )
            
            if completion.choices and completion.choices[0].message:
                assistant_message_obj = completion.choices[0].message
            else:
                print("Error: No message choice returned from OpenRouter.")
                messages.append({"role": "assistant", "content": "Error: LLM did not return a valid message."})
                break

            # Append the assistant's message (which might include tool calls) to messages list for context
            # The OpenAI SDK returns a ChatCompletionMessage object. Convert to dict for appending.
            messages.append(assistant_message_obj.model_dump(exclude_none=True))
            # print_messages([messages[-1]]) # Uncomment for debugging the assistant's response

        except APIStatusError as e:
            print(f"OpenRouter API returned an API Status Error: {e.status_code}")
            print(f"Response: {e.response.text if e.response else 'N/A'}")
            error_content = f"Error: API Status {e.status_code}"
            if hasattr(e, 'message') and e.message: error_content += f" - {e.message}"
            messages.append({"role": "assistant", "content": error_content})
            break
        except APIConnectionError as e:
            print(f"Failed to connect to OpenRouter API: {e}")
            messages.append({"role": "assistant", "content": "Error: Could not connect to OpenRouter."})
            break
        except RateLimitError as e:
            print(f"OpenRouter API request exceeded rate limit: {e}")
            messages.append({"role": "assistant", "content": "Error: Rate limit exceeded with OpenRouter."})
            break
        except AuthenticationError as e:
            print(f"OpenRouter API authentication failed: {e}")
            messages.append({"role": "assistant", "content": "Error: Authentication failed with OpenRouter."})
            break
        except APIError as e: # General API error from OpenAI SDK
            print(f"OpenRouter API returned an error: {e}")
            error_content = f"Error interacting with OpenRouter: {str(e)}"
            if hasattr(e, 'message') and e.message: error_content = e.message
            if hasattr(e, 'code') and e.code: error_content += f" (Code: {e.code})"
            if hasattr(e, 'response') and hasattr(e.response, 'text') and e.response.text:
                print(f"Response text from APIError: {e.response.text}")
            messages.append({"role": "assistant", "content": error_content })
            break
        except Exception as e: # Catch-all for other unexpected errors
            print(f"An unexpected error occurred during API interaction: {e}")
            messages.append({"role": "assistant", "content": f"Unexpected error: {str(e)}"})
            break

        if not assistant_message_obj:
            print("No assistant message object received or error occurred, breaking loop.")
            break # Should have been caught by exceptions, but as a safeguard.

        if assistant_message_obj.tool_calls:
            # Iterate over tool calls requested by the LLM
            for tool_call in assistant_message_obj.tool_calls:
                function_name = tool_call.function.name
                # Arguments from the OpenAI SDK tool_call.function.arguments is a string
                function_args_str = tool_call.function.arguments
                function_response_content = None # Will hold the content for the tool role message

                print(f"LLM requests to call function: {function_name} with args: {function_args_str}")

                try:
                    function_args = json.loads(function_args_str)
                except json.JSONDecodeError as e_json:
                    print(f"Error decoding JSON arguments for {function_name}: {e_json}")
                    print(f"Raw arguments string: {function_args_str}")
                    function_response_content = json.dumps({
                        "error": "Invalid JSON arguments provided by LLM",
                        "details": str(e_json),
                        "arguments_received": function_args_str
                    })
                    # Append tool response with error and continue to next tool_call or let LLM handle
                    messages.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": function_name,
                        "content": function_response_content,
                    })
                    continue # Process next tool call if any

                # --- Call the actual Python functions based on name ---
                if function_name == "extract_hotel_search_parameters":
                    # This "tool" is about the LLM structuring data.
                    # The "response" is the data it extracted.
                    # We might update our 'parameters' dict here.
                    extracted_params = handle_extract_hotel_search_parameters(function_args)
                    if isinstance(extracted_params, str): # handle_extract_hotel_search_parameters returns a JSON string
                        parameters.update(json.loads(extracted_params))
                    elif isinstance(extracted_params, dict):
                         parameters.update(extracted_params)
                    function_response_content = extracted_params # Pass back the extracted params as the tool's result
                    print(f"Updated global parameters: {parameters}")
                
                elif function_name == "query_elasticsearch":
                    # Consolidate parameters for this call. LLM-provided args for this specific call take precedence.
                    current_call_es_params = parameters.copy() # Start with general/global params
                    current_call_es_params.update(function_args) # Override/add with LLM provided args for this call

                    if not current_call_es_params.get("query"):
                         function_response_content = json.dumps({"error": "Missing 'query' for Elasticsearch."})
                    else:
                        # Ensure all expected arguments for call_elasticsearch are present or defaulted
                        es_args = {
                            "query": current_call_es_params.get("query"),
                            "latitude": current_call_es_params.get("latitude"),
                            "longitude": current_call_es_params.get("longitude"),
                            "distance": current_call_es_params.get("distance"),
                            "rating": current_call_es_params.get("rating"),
                            "attraction": current_call_es_params.get("attraction"),
                            "country_name": current_call_es_params.get("countryName"), # Match case if needed
                            "country_code": current_call_es_params.get("countryCode")
                        }
                        # Filter out None values, as call_elasticsearch might expect missing args vs. None
                        es_args_cleaned = {k: v for k, v in es_args.items() if v is not None}
                        try:
                            function_response_content = call_elasticsearch(**es_args_cleaned) # call_elasticsearch returns JSON string
                        except Exception as e_es:
                            print(f"Error calling Elasticsearch: {e_es}")
                            function_response_content = json.dumps({"error": f"Error during Elasticsearch query: {str(e_es)}"})
                else:
                    function_response_content = json.dumps({"error": f"Unknown function requested: {function_name}"})

                # Append the actual tool's response to the messages list
                messages.append({
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": function_name,
                    "content": function_response_content, # Content must be a string
                })
                # print_messages([messages[-1]]) # Uncomment for debugging tool response

            # After processing all tool calls for this turn, loop again to send tool responses to the LLM
        else:
            # No tool calls in the assistant's message, so this is the final natural language response.
            final_response_content = assistant_message_obj.content
            if final_response_content:
                # Assuming format_message and display are defined elsewhere for IPython/notebook display
                formatted_final_response = format_message({"content": final_response_content})
                display(Markdown(formatted_final_response))
                break # Exit the while loop as we have the final answer or an unrecoverable state.
            else:
                # Handle cases where there's no content (e.g. error or empty response from LLM)
                display(Markdown("Assistant did not provide a final content message or tool calls."))
                print(f"Full assistant message (no content/tool_calls): {assistant_message_obj.model_dump_json(indent=2) if assistant_message_obj else 'None'}")
            # If no tool calls and no content, the loop continues, allowing the model another turn.
            # If this leads to an infinite loop, further debugging might be needed.
    
    return messages # Return the full conversation history including all turns

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
