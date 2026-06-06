import argparse 
import os
import re
import unicodedata
from difflib import SequenceMatcher
from collections import defaultdict

# Google API Imports
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# If modifying these scopes, delete the file token.json.
# We only need read-only access to look for duplicates.
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']

# -------------------------------------------------------------
# Paste your Spreadsheet ID here. 
# Found in the URL: https://docs.google.com/spreadsheets/d/[SPREADSHEET_ID]/edit
# -------------------------------------------------------------
SPREADSHEET_ID = '1YzeNXeZ3Ff1ZAjiDI9QDMjs4_JOHE8TGgwrUVLCRXBQ'

def get_sheets_service():
    """Handles OAuth2 authentication and returns the Sheets API service."""
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    try:
        service = build('sheets', 'v4', credentials=creds)
        return service
    except HttpError as err:
        print(f"An error occurred connecting to Google Sheets: {err}")
        return None


def normalize_text(text):
    text = text.lower()
    text = unicodedata.normalize('NFKD', text)
    text = ''.join([c for c in text if not unicodedata.combining(c)])
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def is_header(text):
    normalized = normalize_text(text)
    return normalized in ["artist - title", "artist - album", "album", "artist"]


def find_potential_duplicates(albums_with_locations, similarity_threshold=0.85):
    """
    albums_with_locations: List of tuples (tab_name, row_number, album_text)
    """
    filtered_albums = []
    header_count = 0

    for tab, row, album in albums_with_locations:
        if is_header(album):
            header_count += 1
        else:
            filtered_albums.append((tab, row, album))

    if header_count > 0:
        print(f"Detected and skipped {header_count} header row(s)\n")

    # Normalize entries
    normalized_albums = [(tab, row, original, normalize_text(original))
                         for tab, row, original in filtered_albums]

    # Group by artist
    artist_groups = defaultdict(list)
    for tab, row, original, normalized in normalized_albums:
        try:
            # Assumes format "Artist - Album". If no delimiter, whole string is treated as artist group
            artist = normalized.split(' - ')[0].strip() if ' - ' in normalized else normalized
            artist_groups[artist].append((tab, row, original, normalized))
        except Exception:
            continue

    potential_duplicates = []

    for artist, albums in artist_groups.items():
        if len(albums) <= 1:
            continue

        for i in range(len(albums)):
            tab_i, row_i, original_i, normalized_i = albums[i]
            album_i = normalized_i.split(' - ', 1)[1] if ' - ' in normalized_i else normalized_i

            duplicates_for_i = [(tab_i, row_i, original_i)]

            for j in range(i + 1, len(albums)):
                tab_j, row_j, original_j, normalized_j = albums[j]
                album_j = normalized_j.split(' - ', 1)[1] if ' - ' in normalized_j else normalized_j

                similarity = SequenceMatcher(None, album_i, album_j).ratio()

                if similarity >= similarity_threshold:
                    duplicates_for_i.append((tab_j, row_j, original_j))

            if len(duplicates_for_i) > 1:
                potential_duplicates.append(duplicates_for_i)

    return potential_duplicates


def main():
    parser = argparse.ArgumentParser(
        description='Find duplicate music albums across all tabs of a Google Sheet using fuzzy matching.'
    )
    parser.add_argument(
        '--id', 
        metavar='SPREADSHEET_ID',
        help='The Google Spreadsheet ID. If not provided, defaults to the hardcoded ID in the script.'
    )
    parser.add_argument(
        '--threshold', 
        type=float, 
        default=0.85,
        help='Similarity threshold (0.0-1.0). Higher is more strict. Default is 0.85.'
    )

    args = parser.parse_args()

    # Determine which Spreadsheet ID to use
    spreadsheet_id = args.id if args.id else SPREADSHEET_ID

    if not spreadsheet_id or spreadsheet_id == 'YOUR_SPREADSHEET_ID_HERE':
        print("Error: Please provide a Spreadsheet ID either by editing the SPREADSHEET_ID ")
        print("variable in the script or by passing it via the --id argument.")
        print("\nRun 'python album-duplicate-finder.py --help' for usage instructions.")
        return

    service = get_sheets_service()
    if not service:
        return

    print("Fetching sheet metadata...")
    try:
        # 1. Get all Tab (Sheet) names automatically
        sheet_metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheets = sheet_metadata.get('sheets', '')
        tab_names = [sheet['properties']['title'] for sheet in sheets]
        
        # 2. Pull data from all tabs in a single batch call
        ranges = [f"'{tab}'!A:A" for tab in tab_names]
        print(f"Reading data from tabs: {', '.join(tab_names)}...")
        
        result = service.spreadsheets().values().batchGet(
            spreadsheetId=spreadsheet_id, ranges=ranges).execute()
        value_ranges = result.get('valueRanges', [])

        # 3. Parse the data into a master list tracking (tab, row, value)
        albums_with_locations = []
        for tab_name, value_range in zip(tab_names, value_ranges):
            rows = value_range.get('values', [])
            for row_num, row_data in enumerate(rows, 1):
                if row_data and str(row_data[0]).strip():
                    albums_with_locations.append((tab_name, row_num, str(row_data[0]).strip()))

    except HttpError as err:
        print(f"API Error: {err}")
        return

    # Run duplicate logic with the CLI-specified threshold
    potential_duplicates = find_potential_duplicates(albums_with_locations, args.threshold)

    # Print results
    print(f"Found {len(potential_duplicates)} potential duplicate groups (Threshold: {args.threshold}):")
    print("-" * 60)

    for i, group in enumerate(potential_duplicates, 1):
        print(f"Group {i}:")
        for tab, row, album in group:
            print(f"  [{tab}] Row {row}: {album}")
        print("")


if __name__ == "__main__":
    main()
