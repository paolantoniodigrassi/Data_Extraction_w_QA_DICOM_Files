"""
Gestione download istanze DICOM dal PACS.
Versione standalone senza dipendenze Django.
"""
import requests
from requests_toolbelt.multipart import decoder
from src.extraction import extraction_config as cfg


def download_instance(study_uid, series_uid, sop_instance_uid, output_path):
    """
    Scarica un'istanza DICOM dal PACS e la salva nel percorso indicato.
    """
    instance_url = (
        f"{cfg.PACS_BASE_URL}/studies/{study_uid}"
        f"/series/{series_uid}"
        f"/instances/{sop_instance_uid}"
    )

    try:
        response = requests.get(instance_url)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"[WARN] Errore nel download dell'istanza {sop_instance_uid}: {e}")
        return

    content_type = response.headers.get('Content-Type', '')
    if 'multipart/related' in content_type:
        multipart_data = decoder.MultipartDecoder.from_response(response)
        for part in multipart_data.parts:
            if 'application/dicom' in part.headers[b'Content-Type'].decode('utf-8'):
                with open(output_path, 'wb') as dicom_file:
                    dicom_file.write(part.content)
                return
    else:
        print(f"[WARN] Risposta non multipart per istanza {sop_instance_uid}")
