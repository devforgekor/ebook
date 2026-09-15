import datetime

def incoming_path(filename):
    # incoming/{filename}.pdf
    return f"incoming/{filename}"

def optimized_webp_path(person_id, record_key, year):
    # optimized-copies/{year}.{person_id}.{record_key}.webp
    return f"optimized-copies/{year}.{person_id}.{record_key}.webp"

def optimized_pdf_path(person_id, record_key, year):
    # optimized-copies/{year}.{person_id}.{record_key}.pdf
    return f"optimized-copies/{year}.{person_id}.{record_key}.pdf"

def archive_webp_path(generation, record_key):
    return f"archive/{generation}/webp/{record_key}.webp"

