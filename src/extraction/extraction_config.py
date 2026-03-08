"""
Configurazione standalone per l'estrazione DICOM.
Sostituisce le Django settings per l'uso in pipeline CLI.
Legge le variabili dal file .env o dall'ambiente.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Cerca il .env nella root del progetto
PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

# AWS
AWS_KMS_KEY_ID = os.environ.get("AWS_KMS_KEY_ID", "")
AWS_REGION = os.environ.get("AWS_REGION", "")
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY", "")

# PACS
PACS_BASE_URL = os.environ.get(
    "PACS_BASE_URL",
    "http://host.docker.internal:8080/dcm4chee-arc/aets/DCM4CHEE/rs"
)
PACS_PATIENTS_URL = f"{PACS_BASE_URL}/patients"
PACS_STUDIES_URL = f"{PACS_BASE_URL}/studies?includefield=all&offset=0"
PACS_SERIES_URL = f"{PACS_BASE_URL}/series?includefield=all&offset=0"
PACS_INSTANCES_URL = f"{PACS_BASE_URL}/instances?includefield=all&offset=0"

# Anonimizzazione
ANONYMIZATION_DATE_OFFSET_DAYS = int(os.environ.get("ANONYMIZATION_DATE_OFFSET_DAYS", "30"))
ANONYMIZATION_TIME_OFFSET_MINUTES = int(os.environ.get("ANONYMIZATION_TIME_OFFSET_MINUTES", "40"))

# Tag DICOM sensibili
SENSITIVE_DICOM_TAGS = [
    'SOPInstanceUID', 'StudyDate', 'SeriesDate', 'AcquisitionDate',
    'ContentDate', 'StudyTime', 'SeriesTime', 'AcquisitionTime',
    'ContentTime', 'AccessionNumber', 'InstitutionName', 'InstitutionAddress',
    'ReferringPhysicianName', 'PatientName', 'PatientID',
    'IssuerOfPatientID', 'PatientBirthDate', 'OtherPatientIDs',
    'PatientAddress', 'PatientComments', 'DeviceSerialNumber', 'ReferencedImageSequence',
    'ReferencedSOPInstanceUID', 'StudyInstanceUID', 'SeriesInstanceUID', 'StudyID',
    'InstanceCreationDate', 'InstanceCreationTime', 'ImageComments',
    'BurnedInAnnotation', 'AdmissionID', 'MediaStorageSOPInstanceUID'
]
