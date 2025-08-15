import re
import unicodedata
from difflib import SequenceMatcher
import argparse
from collections import defaultdict


def normalize_text(text):
    """
    Normalize text by:
    1. Converting to lowercase
    2. Removing accents
    3. Removing extra spaces
    """
    # Convert to lowercase
    text = text.lower()

    # Remove accents
    text = unicodedata.normalize('NFKD', text)
    text = ''.join([c for c in text if not unicodedata.combining(c)])

    # Remove extra spaces
    text = re.sub(r'\s+', ' ', text).strip()

    return text


def is_header(text):
    """Check if text matches known header patterns"""
    normalized = normalize_text(text)
    return normalized in ["artist - title", "artist - album"]


def find_potential_duplicates(
        albums_with_line_numbers,
        similarity_threshold=0.85
):
    """
    Find potential duplicates in a list of albums based on similarity.
    Returns groups of potential duplicates.

    albums_with_line_numbers: List of tuples (line_number, album_text)
    """
    # Filter out all headers
    filtered_albums = []
    header_count = 0

    for line_num, album in albums_with_line_numbers:
        if is_header(album):
            header_count += 1
        else:
            filtered_albums.append((line_num, album))

    if header_count > 0:
        print(f"Detected and skipped {header_count} header row(s)")

    # Normalize all albums
    normalized_albums = [(line_num, album, normalize_text(album))
                         for line_num, album in filtered_albums]

    # Group albums by artist for faster processing
    artist_groups = defaultdict(list)
    for line_num, original, normalized in normalized_albums:
        try:
            artist = normalized.split(' - ')[0].strip()
            artist_groups[artist].append((line_num, original, normalized))
        except IndexError:
            # Handle entries that don't follow the "Artist - Album" format
            print(f"Warning: Line {line_num}: \
                  Entry doesn't follow 'Artist - Album' format: {original}")
            continue

    # Find potential duplicates within each artist group
    potential_duplicates = []

    for artist, albums in artist_groups.items():
        # If there's only one album by this artist, skip
        if len(albums) <= 1:
            continue

        # Compare each pair of albums by this artist
        for i in range(len(albums)):
            line_num_i, original_i, normalized_i = albums[i]
            album_i = normalized_i.split(' - ', 1)[1] \
                if ' - ' in normalized_i else normalized_i

            duplicates_for_i = [(line_num_i, original_i)]

            for j in range(i + 1, len(albums)):
                line_num_j, original_j, normalized_j = albums[j]
                album_j = normalized_j.split(' - ', 1)[1] \
                    if ' - ' in normalized_j else normalized_j

                # Calculate similarity between album titles
                similarity = SequenceMatcher(None, album_i, album_j).ratio()

                if similarity >= similarity_threshold:
                    duplicates_for_i.append((line_num_j, original_j))

            if len(duplicates_for_i) > 1:
                potential_duplicates.append(duplicates_for_i)

    return potential_duplicates


def main():
    parser = \
        argparse.ArgumentParser(description='Find duplicate albums in a list.')
    parser.add_argument('input_file',
                        help='Path to file containing album list')
    parser.add_argument('--threshold',
                        type=float,
                        default=0.85,
                        help='Similarity threshold (0.0-1.0, higher is more \
                            strict)')
    parser.add_argument('--output',
                        help='Output file for results (optional)')

    args = parser.parse_args()

    # Read the album list with line numbers (1-based for human readability)
    albums_with_line_numbers = []
    with open(args.input_file, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            if line.strip():
                albums_with_line_numbers.append((line_num, line.strip()))

    # Find potential duplicates
    potential_duplicates = find_potential_duplicates(albums_with_line_numbers,
                                                     args.threshold)

    # Prepare output
    output_lines = []
    output_lines.append(f"Found {len(potential_duplicates)} potential \
                        duplicate groups:")
    output_lines.append("-" * 50)

    for i, group in enumerate(potential_duplicates, 1):
        output_lines.append(f"Group {i}:")
        for line_num, album in group:
            # Line numbers are already correct since we preserved them
            # from the file
            output_lines.append(f"  Line {line_num}: {album}")
        output_lines.append("")

    # Output results
    output_text = "\n".join(output_lines)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(output_text)
        print(f"Results written to {args.output}")
    else:
        print(output_text)


if __name__ == "__main__":
    main()
