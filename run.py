from distutils import config
import os
import requests
from dotenv import load_dotenv
import yaml
import PIL
from PIL import Image
import base64
import json
import logging
import datetime

log_file = "jellybean.log"

if os.path.isfile(log_file):
    os.remove(log_file) 

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)

# Ensure the needed folders exist
if not os.path.exists('./assets/originals'):
    os.makedirs('./assets/originals')

if not os.path.exists('./temp'):
    os.makedirs('./temp')

if not os.path.exists('./logs'):
    os.makedirs('./logs')

# Remove any existing log files
for file in os.listdir('./logs'):
    if file.endswith('.log'):
        os.remove(f'./logs/{file}')

# Generate a log file
log_file = "jellybean.log"

# Load .env file
load_dotenv(".env")

# Global variables
jellyfin_url = os.getenv('JELLYFIN_URL')
api_key = os.getenv('JELLYFIN_API_KEY')

def main():
    
    # Get admin user ID
    response = requests.get(f"{jellyfin_url}/Users",
                            headers={"X-Emby-Token": api_key})

    users = response.json()

    for user in users:
        if user["Policy"]["IsAdministrator"]:
            global user_id
            user_id = user["Id"]
            #logging.info(f"Admin user ID: {user_id}")
            break

    # Get list of libraries from the config.yaml file
    with open("config.yaml", "r") as file:
        config_vars = yaml.safe_load(file)

    libraries = config_vars["libraries"]
    logging.info(f"Lodaded config.yaml:\n {libraries}")

    # Initialize empty list of library parent ids
    libraries_dict = {}

    # Get the parent id of each library
    for library in libraries:

        # Get all items
        response = requests.get(f"{jellyfin_url}/Users/{user_id}/Views",
                                headers={"X-Emby-Token": api_key})
        
        #print(library)

        views = response.json()["Items"]

        for view in views:
            if view['Name'] == library:
                parent_id = view["Id"]
                logging.info(f"Parent ID: {parent_id}")
                collection_type = view["CollectionType"]
                logging.info(f'Collection Type: {collection_type}')
                break
            else:
                parent_id = None
                collection_type = None

        # Add the library name and parent id to the dictionary
        libraries_dict.update({library: {"parent_id": parent_id, "collection_type": collection_type}})

    # Cycle through the libraries
    for library in libraries_dict:

        logging.info(f"Checking {library}")

        library_type = libraries_dict[library].get('collection_type')

        # Call function to get list of items in the library
        items = get_all_items_library(libraries_dict[library])

        # Check Library Type     

        if library_type == 'none':
            logging.info(f"{library}: Library is not set to movies or tv shows, skipping library.")
            continue

        # Check if library is enabled
        if not config_vars["libraries"][library]["enabled"]:
            logging.info(f"Library Name: {library} \nLibrary Type: {library_type}\nAction: Library is not enabled in the config.yaml file, skipping library.\n------")
            continue
        
        logging.info(f"Library Name: {library} \nLibrary Type: {library_type}\nAction: Library is enabled in the config.yaml file, checking overlays.\n------")
        
        overlays(library, library_type, items, config_vars)

def collection(library, library_type, items, filename):
    # Get the config from the filename
    with open(f"./collections/{filename}", "r") as file:
        config_vars = yaml.safe_load(file)

    # Create an empty dictionary to store the collections
    collections_dict = {}

    # Iterate over collections
    for collection_name, collection_data in config_vars["collections"].items():
        # Add the sub-section to the collections dictionary
        collections_dict[collection_name] = collection_data

    # Get a list of all existing collections in the Jellyfin server
    response = requests.get(f"{jellyfin_url}/Users/{user_id}/Views",
                            headers={"X-Emby-Token": api_key})
    
    collections = response.json()["Items"]

    # Loop through all collections
    for collection_name, collection_data in collections_dict.items():
        logging.info(f"Checking {collection_name}")
        collection_type = collection_data["type"]
        logging.info(f"Collection Type: {collection_type}")
        collection_link = collection_data["link"]
        logging.info(f"Collection Link: {collection_link}")
        collection_limit = collection_data["limit"]
        logging.info(f"Collection Limit: {collection_limit}")

        # Check if collection exists in the server


def overlays(library, library_type, items, config_vars):      
           
    # Check if overlays will be added or removed
    overlay_config = config_vars["libraries"][library]["overlays"]

    # Check if Overlays is set to true
    if overlay_config:
        logging.info(f"{library}: Overlays is true in the config.yaml file, adding missing overlays.")
    else:
        logging.info(f"{library}: Overlays is false in the config.yaml file, removing overlays.")

    #### MOVIES ####

    if library_type == 'movies':
        # Loop through all movies
        logging.info(f"Found {len(items)} items in {library}")
        for item in items:

            response2 = requests.get(f"{jellyfin_url}/Users/{user_id}/Items/{item['Id']}",
                                headers={"X-Emby-Token": api_key})
            
            movie = response2.json()

            if not 'MediaSources' in movie:
                logging.info(f"Movie {item['Name']} has no media sources, skipping.")
                continue

            tagged = check_tags(movie)

            if overlay_config:
                if tagged:
                    logging.info(f"{item['Name']} has custom overlay, skipping.")
                    continue
                logging.info(f"{item['Name']} does not have a custom overlay. Adding overlay to {item['Name']}: {item['Id']}")
                if add_overlay(movie["Id"], item):
                    update_tag(movie, item, True, 'custom-overlay')
            else:
                if not tagged:
                    logging.info(f"{item['Name']} does not have a custom overlay, skipping.")
                    continue
                logging.info(f"{item['Name']} has a custom overlay. Removing overlay from {item['Name']}: {item['Id']}")
                if remove_overlay(movie["Id"], item):
                    update_tag(movie, item, False, 'custom-overlay')

    ### TV SHOWS ###

    elif library_type == 'tvshows':
        logging.info(f'Found {len(items)} items in {library}')
        # Loop through all tv shows
        for item in items:

            response2 = requests.get(f"{jellyfin_url}/Users/{user_id}/Items/{item['Id']}",
                                headers={"X-Emby-Token": api_key})
            
            tv_show = response2.json()

            logging.info(f"Checking {item['Name']}: {tv_show['Id']}")

            # Get all episodes from that TV Show
            response3 = requests.get(f"{jellyfin_url}/Shows/{tv_show['Id']}/Episodes",
                                headers={"X-Emby-Token": api_key})
        
            episodes = response3.json()['Items']

            # Get the first episode ID

            if len(episodes) == 0:
                logging.info(f"TV Show {item['Name']} has no episodes, skipping.")
                continue

            episode_id = episodes[0]["Id"]

            # Check that episode_id is not None
            if episode_id is None:
                logging.info(f"TV Show {item['Name']} has no episodes, skipping.")
                continue

            response4 = requests.get(f"{jellyfin_url}/Users/{user_id}/Items/{episode_id}",
                                headers={"X-Emby-Token": api_key})
            
            episode = response4.json()

            # Get MediaSources from first episode
            if not 'MediaSources' in episode:
                logging.info(f"Episode {episode['Name']} has no media sources, skipping.")
                continue

            tagged = check_tags(tv_show)

            if overlay_config:
                if tagged:
                    continue
                logging.info(f"Adding overlay to {item['Name']}: {tv_show['Id']}")
                if add_overlay(tv_show["Id"], item):
                    update_tag(tv_show, item, True, 'custom-overlay')
            else:
                if not tagged:
                    continue
                logging.info(f"Removing overlay from {item['Name']}: {tv_show['Id']}")
                if remove_overlay(tv_show["Id"], item):
                    update_tag(tv_show, item, False, 'custom-overlay')
    

def get_all_items_library(library):
    # Get all items in the library
    response = requests.get(f"{jellyfin_url}/Items",
                            headers={"X-Emby-Token": api_key},
                            params={"ParentId": library["parent_id"]})    

    items = response.json()["Items"]
    return items                  

def check_tags(file):

    # Check if the movie has the tag "custom-overlay"
    if "custom-overlay" in file["Tags"]:
        return True
    else:
        return False

def check_hdr(item):

    # Get movie from item
    response = requests.get(f"{jellyfin_url}/Users/{user_id}/Items/{item['Id']}",
                        headers={"X-Emby-Token": api_key})
    
    media_file = response.json()

    # Check if media_file has "Type": "Series"
    if media_file["Type"] == "Series":
        logging.info("Media file is a TV show, getting the first episode")
        # Get all episodes from that TV Show
        response2 = requests.get(f"{jellyfin_url}/Shows/{media_file['Id']}/Episodes",
                            headers={"X-Emby-Token": api_key})
    
        episodes = response2.json()['Items']

        # Get the first episode ID
        episode_id = episodes[0]["Id"]

        response3 = requests.get(f"{jellyfin_url}/Users/{user_id}/Items/{episode_id}",
                            headers={"X-Emby-Token": api_key})
        
        episode = response3.json()

        media_file = episode

    # Check if media_file resoltion is 4K
    if media_file['Width'] >= 2500:
        # Check if the movie is SDR, HDR, or DoVI
        for media_source in media_file['MediaSources']:
            for media_stream in media_source['MediaStreams']:
                if media_stream['Codec'] == 'hevc' or media_stream['Codec'] == 'h264' or media_stream['Codec'] == 'vp9' or media_stream['Codec'] == 'av1':
                    if media_stream['VideoRange'] == 'SDR' and media_stream['VideoRangeType'] == 'SDR':
                        logging.info("HDR type is SDR")
                        return '4KSDR'
                    elif media_stream['VideoRange'] == 'HDR' and (media_stream['VideoRangeType'].startswith('HDR10') or media_stream['VideoRangeType'].startswith('HLG')):
                        if 'VideoDoViTitle' in media_stream:
                            if media_stream['VideoDoViTitle'].startswith('DV Profile'):
                                logging.info("HDR type is DV + HDR")
                                return '4KDVHDR'
                        else:
                            logging.info("HDR type is HDR Only")
                            return '4KHDR'
                    elif media_stream['VideoRange'] == 'HDR' and media_stream['VideoRangeType'] == 'DOVI':
                        if 'VideoDoViTitle' in media_stream and media_stream['VideoDoViTitle'].startswith('DV Profile'):
                            logging.info("HDR type is DV only")
                            return '4KDV'
                        else:
                            logging.info("Unknown HDR type")
                            return '4KSDR'
                    else:
                        logging.info("Unknown HDR type") 
                        return '4KSDR'
    elif media_file['Width'] > 1280:
        # Placeholder for 1080p overlays
        # Check if the movie is SDR, HDR, or DoVI
        for media_source in media_file['MediaSources']:
            for media_stream in media_source['MediaStreams']:
                if media_stream['Codec'] == 'hevc' or media_stream['Codec'] == 'h264' or media_stream['Codec'] == 'vp9' or media_stream['Codec'] == 'av1':
                    if media_stream['VideoRange'] == 'SDR' and media_stream['VideoRangeType'] == 'SDR':
                        logging.info("HDR type is SDR")
                        return 'FHDSDR'
                    elif media_stream['VideoRange'] == 'HDR' and (media_stream['VideoRangeType'].startswith('HDR10') or media_stream['VideoRangeType'].startswith('HLG')):
                        if 'VideoDoViTitle' in media_stream:
                            if media_stream['VideoDoViTitle'].startswith('DV Profile'):
                                logging.info("HDR type is DV + HDR")
                                return 'FHDDVHDR'
                        else:
                            logging.info("HDR type is HDR Only")
                            return 'FHDHDR'
                    elif media_stream['VideoRange'] == 'HDR' and media_stream['VideoRangeType'] == 'DOVI':
                        if 'VideoDoViTitle' in media_stream and media_stream['VideoDoViTitle'].startswith('DV Profile'):
                            logging.info("HDR type is DV only")
                            return 'FHDDV'
                        else:
                            logging.info("Unknown HDR type")
                            return 'FHDSDR'
                    else:
                        logging.info("Unknown HDR type") 
                        return 'FHDSDR'
        #return '1080p'
    else:
        return 'unknown'

def update_tag(movie, item, add, tag):
    
        if add:
            # Add the tag to the item
            movie["Tags"].append(tag)
        else:
            # remove the tag from the item
            movie["Tags"].remove(tag)

        # Update the movie in the Jellyfin server
        response3 = requests.post(f"{jellyfin_url}/Items/{item['Id']}",
                        headers={"X-Emby-Token": api_key,
                                "Content-Type": "application/json"},
                        data=json.dumps(movie))
    
        # Print response from the request
    
        if response3.status_code == 204:
            logging.info(f'Tag for {item["Name"]} updated successfully')
        else:
            logging.info(f'Failed to update tag for {item["Name"]}')

def add_overlay(movie_id, item):

    logging.info(f"Adding overlay to {item['Name']}: {movie_id}")
    
    response = requests.get(f"{jellyfin_url}/Items/{movie_id}/Images",
                         headers={"X-Emby-Token": api_key})

    image_data = response.json()

    if len(image_data) == 0:
        logging.info(f"Movie {item['Name']} has no poster, skipping.")    
        return False

    # Save a copy of the original poster
    response = requests.get(f"{jellyfin_url}/Items/{movie_id}/Images/Primary",
                            headers={"X-Emby-Token": api_key})
    
    with open(f"./assets/originals/{movie_id}.jpg", "wb") as f:
        f.write(response.content)

    overlay_name = check_hdr(item)

    # Check if the Primary image exists
    if not os.path.exists(f'./assets/originals/{movie_id}.jpg'):
        logging.info(f"{item['Name']} does not have a Primary image, skipping.")
        return False

    # Check if the overlay file exists
    if not os.path.exists(f'./assets/overlays/{overlay_name}.png'):
        logging.info(f"Overlay {overlay_name}.png does not exist, skipping.")
        return False

    # combine poster with the 4kdv logo
    try:
        img1 = Image.open(f'./assets/originals/{movie_id}.jpg')
    except PIL.UnidentifiedImageError as e:
        logging.error(f"Unable to open {movie_id}.jpg, skipping.")
        os.remove(f'./assets/originals/{movie_id}.jpg')
        return False
    except FileNotFoundError as e:
        logging.error(f"Poster not found for {movie_id}.jpg, skipping.")
        return False
    img2 = Image.open(f'./assets/overlays/{overlay_name}.png')

    # Resize the second image to match the first one if they have different sizes
    if img1.size != img2.size:
        img2 = img2.resize(img1.size)

    # Overlay the transparent image on top of the first image
    combined = Image.alpha_composite(img1.convert('RGBA'), img2.convert('RGBA'))

    # Save the new image
    combined.convert('RGB').save(f'./temp/{movie_id}.jpg', 'JPEG')
    
    # Upload the new image to the server
    with open(f'./temp/{movie_id}.jpg', 'rb') as file:
        image_data = file.read()

    image_data_base64 = base64.b64encode(image_data)

    # Define the headers for the request
    headers = {"X-Emby-Token": api_key,
            "Content-Type": "image/jpeg"}

    # Define the endpoint URL
    url = f"{jellyfin_url}/Items/{movie_id}/Images/Primary"

    # Send the POST request
    response = requests.post(url, headers=headers, data=image_data_base64)

    #print(response)

    # Check the response
    if response.status_code == 204:
        logging.info('Image uploaded successfully') 
        os.remove(f'./temp/{movie_id}.jpg')
        return True
    else:
        logging.info('Failed to upload image')
        logging.info(f'Response: {response.text}') 
        return False

def remove_overlay(movie_id, item):

    response = requests.get(f"{jellyfin_url}/Items/{movie_id}/Images",
                        headers={"X-Emby-Token": api_key})

    image_data = response.json()

    if len(image_data) == 0:
        #print(f"Movie {item['Name']} has no poster, skipping.")
        return False
    
    try:
    # Upload the new image to the server
        with open(f'./assets/originals/{movie_id}.jpg', 'rb') as file:
            image_data = file.read()
    except FileNotFoundError as e:
        logging.error(f"Unable to open {movie_id}.jpg, skipping.")
        return False

    image_data_base64 = base64.b64encode(image_data)

    # Define the headers for the request
    headers = {"X-Emby-Token": api_key,
            "Content-Type": "image/jpeg"}

    # Define the endpoint URL
    url = f"{jellyfin_url}/Items/{movie_id}/Images/Primary"

    # Send the POST request
    response = requests.post(url, headers=headers, data=image_data_base64)

    #print(response)

    # Check the response
    if response.status_code == 204:
        logging.info('Image uploaded successfully')
        os.remove(f'./assets/originals/{movie_id}.jpg')
        return True
    else:
        logging.info('Failed to upload image')
        logging.info(f'Response: {response.text}')
        return False

if __name__ == '__main__':

    main()
