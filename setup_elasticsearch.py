import json
from elasticsearch import Elasticsearch, helpers, NotFoundError
import requests
from getpass import getpass # Keep for now, might remove later

# Elasticsearch local connection
es = Elasticsearch(['http://localhost:9200'], basic_auth=('elastic', '9cKxyfj9')) # Default local ES

# Elastic index
ES_INDEX = "hotels"
TEMPLATE_ID = "hotel_search_template" # Also needed for setup

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


if __name__ == "__main__":
    print("Starting Elasticsearch setup...")
    create_inferencing_endpoints()
    create_index()
    ingest_data()
    delete_search_template(TEMPLATE_ID) # Delete if exists
    create_search_template()
    print("Elasticsearch setup complete.")