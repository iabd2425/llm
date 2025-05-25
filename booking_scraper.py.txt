import requests
from bs4 import BeautifulSoup
import json
import re
import time
import random
from urllib.parse import urlparse, parse_qs
from datetime import date, timedelta

def get_province_from_dest_id(dest_id):
    """Maps a destination ID to a province name."""
    province_map = {
        '1363': 'Almería',
        '755': 'Granada',
        '766': 'Málaga',
        '747': 'Cadíz',
        '774': 'Sevilla',
        '758': 'Huelva',
        '750': 'Cordoba',
        '759': 'Jaen',
    }
    return province_map.get(dest_id, 'Unknown Province')

def scrape_booking_region(dest_id, checkin_date, checkout_date):
    """
    Scrapes hotel data from Booking.com for a specified region based on dest_id.

    Args:
        dest_id (str): The destination ID for the region (e.g., '1363' for Almería, '755' for Granada).
        checkin_date (str): Check-in date in 'YYYY-MM-DD' format.
        checkout_date (str): Check-out date in 'YYYY-MM-DD' format.

    Returns:
        list: A list of dictionaries, where each dictionary represents a hotel.
    """
    # Base URL for Booking.com search results
    # The dates and currency will be added as query parameters.
    # Added selected_currency=EUR to try and force EUR prices.
    base_url = f"https://www.booking.com/searchresults.es.html?lang=es%E2%82%8AC&dest_id={dest_id}&dest_type=region&ac_langcode=es&nflt=ht_id%3D204&shw_aparth=0&selected_currency=EUR&checkin={{}}&checkout={{}}"
    url = base_url.format(checkin_date, checkout_date)

    # Get the province name from the dest_id
    province_name = get_province_from_dest_id(dest_id)

    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15',
        'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36',
    ]
    headers = {
        'User-Agent': random.choice(user_agents)
    }

    hotel_list = []

    try:
        # Add a random delay before making the request
        time.sleep(random.uniform(2, 5)) # Delay between 2 and 5 seconds

        response = requests.get(url, headers=headers)
        response.raise_for_status() # Raise an exception for bad status codes

        soup = BeautifulSoup(response.content, 'html.parser')

        # Find all hotel listings on the page
        # You'll need to inspect the HTML of the search results page
        # to find the correct selector for individual hotel listings.
        # This is a placeholder selector.
        hotels = soup.select('div[data-testid="property-card"]')

        for hotel in hotels:
            hotel_data = {}

            # Extract data points
            # You'll need to inspect the HTML for each data point and find its selector.
            # These are placeholder selectors and logic.

            # URL hotel (sin fechas)
            try:
                url_element = hotel.select_one('a[data-testid="title-link"]')
                if url_element and 'href' in url_element.attrs:
                    full_url = url_element['href']
                    hotel_data['url'] = full_url # Keep full URL to extract locality

                    # Extract ID from the URL path (text after last '/' and before '.html')
                    last_part = full_url.split('/')[-1]
                    hotel_id_with_extension = last_part.split('.html')[0]
                    # Eliminar todo lo que va después del primer punto inclusive
                    hotel_id = hotel_id_with_extension.split('.')[0]
                    hotel_data['id'] = hotel_id

                    # Extract locality from the URL
                    parsed_hotel_url = urlparse(full_url)
                    hotel_query_params = parse_qs(parsed_hotel_url.query)
                    locality = hotel_query_params.get('ss', [None])[0]
                    if locality:
                        # Replace '+' with spaces
                        hotel_data['localidad'] = locality.replace('+', ' ')
                    else:
                        hotel_data['localidad'] = None


                else:
                    hotel_data['url'] = None
                    hotel_data['id'] = None
                    hotel_data['localidad'] = None # Also set locality to None if URL is missing
            except Exception as e:
                print(f"Error extracting URL, Hotel ID, or Localidad: {e}")
                hotel_data['url'] = None
                hotel_data['id'] = None
                hotel_data['localidad'] = None # Also set locality to None in case of error

            # Nombre
            try:
                name_element = hotel.select_one('div[data-testid="title"]')
                hotel_data['nombre'] = name_element.get_text(strip=True) if name_element else None
            except Exception as e:
                print(f"Error extracting Nombre: {e}")
                hotel_data['nombre'] = None

            # marca (Often not directly available on search results, might need to visit hotel page)
            hotel_data['marca'] = None # Placeholder

            # Dirección y Localidad
            try:
                address_element = hotel.select_one('span[data-testid="address"]')
                if address_element:
                    full_address = address_element.get_text(strip=True)
                    # Assuming the locality is the first part before a comma or the whole string
                    address_parts = full_address.split(',', 1)
                    hotel_data['localidad'] = address_parts[0].strip()
                    hotel_data['Dirección'] = full_address # Keep the full address as Dirección
                else:
                    hotel_data['localidad'] = None
                    hotel_data['Dirección'] = None
            except Exception as e:
                print(f"Error extracting Dirección or Localidad: {e}")
                hotel_data['localidad'] = None
                hotel_data['Dirección'] = None


            # Coordenadas (Often not directly available on search results, might need to visit hotel page or use geocoding)
            hotel_data['Coordenadas'] = None # Placeholder

            # Servicios populares (Often not directly available on search results, might need to visit hotel page)
            hotel_data['Servicios populares'] = None # Placeholder

            # ¿Mascotas? (Often not directly available on search results, might need to visit hotel page)
            hotel_data['¿Mascotas?'] = None # Placeholder

            # Descripción (Often not fully available on search results, might need to visit hotel page)
            hotel_data['Descripción'] = None # Placeholder

            # Puntuación, Opinión, Numero comentarios
            try:
                review_score_container = hotel.select_one('div[data-testid="review-score"]')
                if review_score_container:
                    # Get all direct child div texts
                    score_texts = [div.get_text(strip=True) for div in review_score_container.select(':scope > div')]

                    # Assign based on index, similar to the provided snippet
                    # Puntuación (numeric value from index 0)
                    if len(score_texts) > 0 and score_texts[0]:
                        try:
                            hotel_data['Puntuación'] = float(score_texts[0])
                        except (ValueError, TypeError):
                            hotel_data['Puntuación'] = None
                    else:
                        hotel_data['Puntuación'] = None

                    # Opinión (from index 1)
                    if len(score_texts) > 1 and score_texts[1]:
                        try:
                            # Replace comma with dot for float conversion
                            opinion_str = score_texts[1].replace(',', '.')
                            hotel_data['Opinión'] = float(opinion_str)
                        except (ValueError, TypeError):
                            hotel_data['Opinión'] = None
                    else:
                        hotel_data['Opinión'] = None

                    # Numero comentarios (numeric value from index 2 using split)
                    if len(score_texts) > 2 and score_texts[2]:
                        num_comments_text = score_texts[2]
                        # Use regex to find the number of comments
                        match = re.search(r'\d+', num_comments_text)
                        # Extract only the number and convert to integer
                        try:
                            hotel_data['Numero comentarios'] = int(match.group(0)) if match else None
                        except (ValueError, TypeError):
                            hotel_data['Numero comentarios'] = None
                    else:
                        hotel_data['Numero comentarios'] = None

                else:
                    hotel_data['Puntuación'] = None
                    hotel_data['Opinión'] = None
                    hotel_data['Numero comentarios'] = None

            except Exception as e:
                print(f"Error extracting Puntuación, Opinión, or Numero comentarios: {e}")
                hotel_data['Puntuación'] = None
                hotel_data['Opinión'] = None
                hotel_data['Numero comentarios'] = None


            # Fecha entrada (Provided by user)
            hotel_data['Fecha entrada'] = checkin_date

            # Fecha salida (Provided by user)
            hotel_data['Fecha salida'] = checkout_date

            # Precio
            try:
                price_element = hotel.select_one('span[data-testid="price-and-discounted-price"]')
                price_text = None
                if price_element:
                     price_text = price_element.get_text(strip=True)
                else:
                    # Sometimes the price is in a different structure
                    price_element_alt = hotel.select_one('div[data-testid="price-and-discounted-price"] span')
                    if price_element_alt:
                        price_text = price_element_alt.get_text(strip=True)

                if price_text:
                    # Clean the price string: remove '€', spaces, and replace comma with dot
                    cleaned_price_text = price_text.replace('€', '').replace(' ', '').replace(',', '.')
                    try:
                        # Convert to integer
                        hotel_data['Precio'] = int(cleaned_price_text)
                    except (ValueError, TypeError):
                        print(f"Could not convert price to float: {cleaned_price_text}")
                        hotel_data['Precio'] = None
                    else:
                        hotel_data['Precio'] = None

            except Exception as e:
                print(f"Error extracting or processing Precio: {e}")
                hotel_data['Precio'] = None


            # Scrape additional details from the hotel's individual page
            if hotel_data.get('url'):
                hotel_details = scrape_hotel_details(hotel_data['url'])
                if hotel_details:
                    # Construct the dictionary in the desired order
                    ordered_hotel_data = {
                        'url': hotel_data.get('url'),
                        'id': hotel_data.get('id'),
                        'nombre': hotel_data.get('nombre'),
                        'marca': hotel_details.get('marca'), # Get marca from hotel_details
                        'destacados': hotel_details.get('Destacados'), # Add Destacados
                        'provincia': province_name, # Add the province name here
                        'localidad': hotel_data.get('localidad'), # Add the locality here
                        'direccion': hotel_details.get('Dirección_detalle'), # Get Dirección from hotel_details
                        'Coordenadas': { # Create a nested dictionary for coordinates
                            'lat': hotel_details.get('lat'), # Get lat from hotel_details
                            'lon': hotel_details.get('lon'), # Get lon from hotel_details
                        },
                        'servicios': hotel_details.get('Servicios populares'), # Get Servicios populares from hotel_details
                        'descripcion': hotel_details.get('Descripción'), # Get Descripción from hotel_details
                        'puntuacion': hotel_data.get('Puntuación'),
                        'opinion': hotel_data.get('Opinión'),
                        'comentarios': hotel_data.get('Numero comentarios'),
                        'fechaEntrada': hotel_data.get('Fecha entrada'),
                        'fechaSalida': hotel_data.get('Fecha salida'),
                        'precio': hotel_data.get('Precio'),
                    }
                    # Remove keys with None or empty list values to keep the output clean
                    hotel_data = {k: v for k, v in ordered_hotel_data.items() if v is not None and v != []}


            hotel_list.append(hotel_data)

        # TODO: Implement pagination if needed


    except requests.exceptions.RequestException as e:
        print(f"Error fetching the page: {e}")
        return None

    return hotel_list

def scrape_hotel_details(url):
    """
    Scrapes additional details from an individual hotel page on Booking.com.

    Args:
        url (str): The URL of the individual hotel page.

    Returns:
        dict: A dictionary containing additional hotel details.
    """
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15',
        'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36',
    ]
    headers = {
        'User-Agent': random.choice(user_agents)
    }

    details = {}

    try:
        # Add a random delay before making the request
        time.sleep(random.uniform(2, 5)) # Delay between 2 and 5 seconds

        response = requests.get(url, headers=headers)
        response.raise_for_status() # Raise an exception for bad status codes

        soup = BeautifulSoup(response.content, 'html.parser')

        # Extract additional data points from the hotel page
        # You'll need to inspect the HTML of an individual hotel page
        # to find the correct selectors for each data point.
        # These are placeholder selectors and logic.

        # Destacados
        # Destacados
        try:
            # Use the corrected selector for the main container of Destacados
            highlight_container = soup.select_one('span.hp__hotel_ratings.pp-header__badges.pp-header__badges--combined div[data-capla-component-boundary="b-property-web-property-page/Badges"]')
            if highlight_container:
                # Select all span or div elements within the container
                highlight_elements = highlight_container.select('span, div')
                # Extract text from each element and store in a list, filtering out empty strings
                # Extract text from each element and store in a list, filtering out empty strings
                extracted_highlights = [elem.get_text(strip=True) for elem in highlight_elements if elem.get_text(strip=True)]

                # Filter out elements that seem to be concatenated (heuristic: look for lowercase followed by uppercase without space)
                # Remove duplicates
                filtered_highlights = []
                seen_highlights = set()
                for highlight in extracted_highlights:
                    # Check for pattern like "aB" (lowercase followed by uppercase)
                    if re.search(r'[a-z][A-Z]', highlight):
                        continue # Skip if pattern found

                    # Add to filtered list and seen set if not a duplicate
                    if highlight not in seen_highlights:
                        filtered_highlights.append(highlight)
                        seen_highlights.add(highlight)

                details['Destacados'] = filtered_highlights
            else:
                details['Destacados'] = [] # Use an empty list if container not found

        except Exception as e:
            print(f"Error extracting Destacados from {url}: {e}")
            details['Destacados'] = [] # Use an empty list in case of error

        # marca
        try:
            brand_element = soup.select_one('div.d7b319a0ec div.b08850ce41')
            details['marca'] = brand_element.get_text(strip=True) if brand_element else None
        except Exception as e:
            print(f"Error extracting marca from {url}: {e}")
            details['marca'] = None

        # Coordenadas
        try:
            coords_element = soup.select_one('a#map_trigger_header_pin')
            coords_data = None
            if coords_element and 'data-atlas-latlng' in coords_element.attrs:
                coords_str = coords_element['data-atlas-latlng']
                if coords_str:
                    lat, lon = coords_str.split(',')
                    details['lat'] = float(lat)
                    details['lon'] = float(lon)
            else:
                # Fallback to meta tags if the primary selector is not found
                lat_meta = soup.find('meta', {'property': 'booking_com:location:latitude'})
                lon_meta = soup.find('meta', {'property': 'booking_com:location:longitude'})
                coords_content = None
                if lat_meta and 'content' in lat_meta.attrs and lon_meta and 'content' in lon_meta.attrs:
                    coords_content = f"{lat_meta['content']},{lon_meta['content']}"

                if not coords_content or coords_content == ',':
                     # Try alternative meta tag
                     geo_position_meta = soup.find('meta', {'name': 'geo.position'})
                     if geo_position_meta and 'content' in geo_position_meta.attrs:
                          coords_content = geo_position_meta['content']

                if coords_content and coords_content != ',':
                    lat, lon = coords_content.split(',')
                    details['lat'] = float(lat)
                    details['lon'] = float(lon)

        except Exception as e:
            print(f"Error extracting Coordenadas from {url}: {e}")
            details['lat'] = None
            details['lon'] = None

        # Servicios populares
        try:
            amenities_list = soup.select('div.hp--popular_facilities ul.e9f7361569 li.b0bf4dc58f div.aa8988bf9c span.f006e3fcbd')
            details['Servicios populares'] = [amenity.get_text(strip=True) for amenity in amenities_list] if amenities_list else None
        except Exception as e:
            print(f"Error extracting Servicios populares from {url}: {e}")
            details['Servicios populares'] = None

        # Descripción
        try:
            description_element = soup.select_one('p[data-testid="property-description"]')
            details['Descripción'] = description_element.get_text(strip=True) if description_element else None
        except Exception as e:
            print(f"Error extracting Descripción from {url}: {e}")
            details['Descripción'] = None

        # Dirección (from hotel page)
        try:
            address_container = soup.select_one('div.b99b6ef58f.cb4b7a25d9')
            if address_container:
                full_text = address_container.get_text(strip=True)
                # Find the second div within the container
                second_div = address_container.select_one('div:nth-of-type(2)')
                if second_div:
                    second_div_text = second_div.get_text(strip=True)
                    # Split the full text by the second div's text
                    address_parts = full_text.split(second_div_text, 1)
                    if address_parts:
                        extracted_address = address_parts[0].strip()
                    else:
                        extracted_address = full_text.strip() # Fallback if split fails
                else:
                    extracted_address = full_text.strip() # If no second div, take all text

                # Find "España" and truncate
                if extracted_address:
                    espana_index = extracted_address.find('España')
                    if espana_index != -1:
                        # Include "España" in the result
                        details['Dirección_detalle'] = extracted_address[:espana_index + len('España')]
                    else:
                        details['Dirección_detalle'] = extracted_address # Keep original if "España" not found
                else:
                    details['Dirección_detalle'] = None # Keep None if no address extracted
            else:
                details['Dirección_detalle'] = None
        except Exception as e:
            print(f"Error extracting Dirección from hotel page {url}: {e}")
            details['Dirección_detalle'] = None

        # Precio (Already extracted from search results, but confirming selector if needed)
        # The price on the individual page might be different or more detailed.
        # For now, we'll rely on the price from the search results as requested initially.
        # If a more specific price from the hotel page is needed, this section would be updated.
        # try:
        #     price_element = soup.select_one('selector_for_price_on_hotel_page')
        #     details['Precio'] = price_element.get_text(strip=True) if price_element else None
        # except Exception as e:
        #     print(f"Error extracting Precio from {url}: {e}")
        #     details['Precio'] = None


    except requests.exceptions.RequestException as e:
        print(f"Error fetching hotel page {url}: {e}")
        return None

    return details

if __name__ == "__main__":
    # Get today's date as the starting check-in date
    start_date = date.today()

    # List of destination IDs for the provinces to scrape
    # '1363': 'Almería'
    # '755': 'Granada'
    dest_ids_to_scrape = ['1363', '755']

    # Scrape for each province and for 3 consecutive days
    for dest_id in dest_ids_to_scrape:
        province_name = get_province_from_dest_id(dest_id)
        print(f"--- Starting scraping for {province_name} ---")

        for i in range(3):
            checkin_date = start_date + timedelta(days=i)
            checkout_date = checkin_date + timedelta(days=1)

            checkin_str = checkin_date.strftime("%Y-%m-%d")
            checkout_str = checkout_date.strftime("%Y-%m-%d")

            print(f"Starting scraping for {province_name} from {checkin_str} to {checkout_str}...")
            hotels_data = scrape_booking_region(dest_id, checkin_str, checkout_str)

            if hotels_data:
                # Define the filename based on province and check-in date
                filename = f"{province_name.lower().replace(' ', '_')}_{checkin_date.strftime('%Y%m%d')}.json"
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(hotels_data, f, ensure_ascii=False, indent=4)
                print(f"Successfully scraped and saved data for {province_name} on {checkin_str} to {filename}")
            else:
                print(f"Failed to scrape data for {province_name} on {checkin_str}")
        print(f"--- Finished scraping for {province_name} ---")
