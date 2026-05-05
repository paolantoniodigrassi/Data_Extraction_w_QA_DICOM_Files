#!/usr/bin/env python3
"""
Script standalone per l'estrazione di file DICOM dal PACS.
Sostituisce l'interfaccia web Django con un'interfaccia a linea di comando.

Uso:
    python3 extract_dicom.py <csv_file> <anonymization_type> <output_dir>

    anonymization_type: clear | partial | irreversible
"""
import csv
import os
import sys
import base64
from pathlib import Path

# Aggiungi la root del progetto al path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import pydicom

from src.extraction import extraction_config as cfg
from src.extraction.helpers import format_patient_name, mask_name
from src.extraction.network_utils import get_patient_id, get_studies, get_series, get_instances
from src.extraction.dicom_handler import download_instance
from src.extraction.crypto_utils import (
    anonymize_date,
    anonymize_time,
    encrypt_value_with_kms,
    hash_value,
    partially_encrypt_institution_name_with_kms,
    partially_encrypt_uid_with_kms,
    anonymize_referenced_sop_instance_uid,
)
from src.extraction.decryption import (
    decrypt_base64_value,
    decrypt_fields,
    decrypt_person_name,
    decrypt_value_with_kms,
    decrypt_with_offset,
    partially_decrypt_uid,
)


# Pseudonimi

def generate_pseudonymized_ids(patient_names, patient_data):
    """Genera ID pseudonimizzati per ogni paziente."""
    pseudonym_map = {}
    patient_id_mapping = {}
    for index, name in enumerate(patient_names, start=1):
        pseudonym_id = f"{index:03}"
        pseudonym_map[name] = pseudonym_id
        original_id = patient_data.get(name)
        if original_id:
            patient_id_mapping[pseudonym_id] = original_id
    return pseudonym_map, patient_id_mapping


def save_pseudonym_map(pseudonym_map, output_path):
    """Salva la mappa di pseudonimi in un file CSV."""
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        f.write("sep=;\n")
        writer = csv.writer(f, delimiter=';')
        writer.writerow(['PatientName', 'PseudonymizedID'])
        for patient_name, pseudonym_id in pseudonym_map.items():
            clean_name = patient_name.replace('_', ' ')
            writer.writerow([clean_name, f'="{pseudonym_id}"'])


# Nomi cartelle

def generate_patient_folder_name(normalized_name, anonymization_type, key_id=None):
    """Genera il nome della cartella paziente in base al tipo di anonimizzazione."""
    if anonymization_type == 'irreversible':
        hashed = hash_value(normalized_name)
        return hashed[:16]
    elif anonymization_type == 'partial':
        if key_id is None:
            return None
        encrypted = encrypt_value_with_kms(normalized_name, key_id)
        if encrypted is None:
            return None
        return encrypted[:45]
    elif anonymization_type == 'clear':
        return normalized_name
    return None


# Anonimizzazione DICOM

def anonymize_dicom(dicom_file, patient_name, pseudonymized_id, key_id, anonymization_type):
    """Anonimizza un file DICOM in base al tipo specificato."""
    ds = pydicom.dcmread(dicom_file)
    sensitive_tags = cfg.SENSITIVE_DICOM_TAGS

    if anonymization_type == 'clear':
        return ds

    enable_encryption = 1

    def partial_anonymization(tag, value):
        if tag == 'PatientName' and value:
            ds.PatientName = encrypt_value_with_kms(str(value), key_id)
        elif tag == 'PatientID' and value:
            ds.PatientID = pseudonymized_id
        elif tag == 'PatientBirthDate' and value:
            ds.PatientBirthDate = f"{value[:4]}0101"
            encrypted_birth_date_hex = encrypt_value_with_kms(value, key_id)
            if encrypted_birth_date_hex is not None:
                encrypted_birth_date_bytes = bytes.fromhex(encrypted_birth_date_hex)
                encrypted_birth_date_base64 = base64.b64encode(encrypted_birth_date_bytes).decode('utf-8')
                ds.add_new((0x0011, 0x1010), 'LT', encrypted_birth_date_base64)
        elif tag in ['StudyDate', 'SeriesDate', 'AcquisitionDate', 'ContentDate', 'InstanceCreationDate'] and value:
            setattr(ds, tag, anonymize_date(value))
        elif tag in ['StudyTime', 'SeriesTime', 'AcquisitionTime', 'ContentTime'] and value:
            setattr(ds, tag, anonymize_time(value))
        elif tag == 'AccessionNumber' and value:
            ds.AccessionNumber = encrypt_value_with_kms(value, key_id)
        elif tag == 'InstitutionName' and value:
            if enable_encryption == 1:
                ds.InstitutionName = partially_encrypt_institution_name_with_kms(value, key_id)
            else:
                ds.InstitutionName = value
        elif tag == 'InstanceCreationTime' and value:
            ds.InstanceCreationTime = anonymize_time(value)
        elif tag in ['InstitutionAddress', 'ReferringPhysicianName', 'OtherPatientIDs',
                      'IssuerOfPatientID', 'PatientAddress', 'DeviceSerialNumber',
                      'AdmissionID', 'StudyID', 'PatientComments', 'ImageComments'] and value:
            setattr(ds, tag, encrypt_value_with_kms(str(value), key_id))
        elif tag in ['SOPInstanceUID', 'StudyInstanceUID', 'SeriesInstanceUID'] and value:
            setattr(ds, tag, partially_encrypt_uid_with_kms(key_id, str(value)))
        elif tag == 'MediaStorageSOPInstanceUID' and value:
            ds.MediaStorageSOPInstanceUID = encrypt_value_with_kms(value, key_id)

    def irreversible_anonymization(tag, value):
        if tag == 'PatientName' and value:
            ds.PatientName = hash_value(patient_name)
        elif tag == 'PatientID' and value:
            ds.PatientID = pseudonymized_id
        elif tag == 'PatientBirthDate' and value:
            ds.PatientBirthDate = "19900101"
        elif tag == 'InstanceCreationDate' and value:
            ds.InstanceCreationDate = '19900101'
        elif tag == 'InstanceCreationTime' and value:
            ds.InstanceCreationTime = '000000'
        elif tag in ['StudyDate', 'SeriesDate', 'AcquisitionDate', 'ContentDate'] and value:
            setattr(ds, tag, '19900101')
        elif tag in ['StudyTime', 'SeriesTime', 'AcquisitionTime', 'ContentTime'] and value:
            setattr(ds, tag, '000000')
        elif tag in ['AccessionNumber', 'InstitutionName', 'InstitutionAddress',
                      'ReferringPhysicianName', 'OtherPatientIDs', 'IssuerOfPatientID',
                      'PatientAddress', 'DeviceSerialNumber', 'AdmissionID', 'StudyID',
                      'PatientComments', 'ImageComments'] and value:
            setattr(ds, tag, hash_value(str(value)))
        elif tag in ['SOPInstanceUID', 'StudyInstanceUID', 'SeriesInstanceUID'] and value:
            setattr(ds, tag, hash_value(value))
        elif tag == 'MediaStorageSOPInstanceUID' and value:
            ds.MediaStorageSOPInstanceUID = hash_value(value)

    for tag in sensitive_tags:
        value = getattr(ds, tag, None)
        if value:
            if anonymization_type == 'partial':
                partial_anonymization(tag, value)
            elif anonymization_type == 'irreversible':
                irreversible_anonymization(tag, value)

    anonymize_referenced_sop_instance_uid(ds, key_id, anonymization_type)
    if 'MediaStorageSOPInstanceUID' in ds.file_meta:
        ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
    
    # Rimuove Command Set elements (gruppo 0000) che pydicom 3.x rifiuta in save_as
    to_remove = [elem.tag for elem in ds if elem.tag.group == 0x0000]
    for tag in to_remove:
        del ds[tag]
    
    return ds


# Processing gerarchico

def process_instance(instance, study_uid, series_uid, series_folder,
                     patient_name, pseudonymized_id, key_id,
                     anonymization_type, patient_id_mapping):
    """Scarica e anonimizza una singola istanza DICOM."""
    sop_instance_uid = instance['00080018']['Value'][0]

    if anonymization_type == 'clear':
        instance_file_name = f"{sop_instance_uid}.dcm"
    elif anonymization_type == 'irreversible':
        if len(sop_instance_uid) > 30:
            clear_part = sop_instance_uid[:30]
            hashed_part = hash_value(sop_instance_uid[30:])
            instance_file_name = f"{clear_part}{hashed_part[:10]}.dcm"
        else:
            instance_file_name = f"{hash_value(sop_instance_uid)[:30]}.dcm"
    elif anonymization_type == 'partial':
        encrypted_uid = partially_encrypt_uid_with_kms(key_id, sop_instance_uid)
        instance_file_name = f"{encrypted_uid[:45]}.dcm"
    else:
        return

    output_path = os.path.join(series_folder, instance_file_name)

    if anonymization_type == 'partial':
        original_output_path = output_path
        counter = 1
        while os.path.exists(output_path):
            output_path = f"{os.path.splitext(original_output_path)[0]}_{counter}.dcm"
            counter += 1

    temp_path = os.path.join(series_folder, f"temp_{instance_file_name}")

    try:
        if anonymization_type == 'clear':
            download_instance(study_uid, series_uid, sop_instance_uid, output_path)
            # Rimuove Command Set elements per compatibilità pydicom 3.x
            ds = pydicom.dcmread(output_path)
            to_remove = [elem.tag for elem in ds if elem.tag.group == 0x0000]
            if to_remove:
                for tag in to_remove:
                    del ds[tag]
                ds.save_as(output_path)
            return

        download_instance(study_uid, series_uid, sop_instance_uid, temp_path)

        anonymized_ds = anonymize_dicom(temp_path, patient_name, pseudonymized_id,
                                         key_id, anonymization_type)
        anonymized_ds.save_as(output_path)

        if anonymization_type == 'partial':
            decrypted_values = decrypt_fields(anonymized_ds, patient_id_mapping)

            if 'PatientBirthDate' in anonymized_ds and anonymized_ds.get((0x0011, 0x1010)):
                anonymized_ds.PatientBirthDate = decrypt_base64_value(
                    anonymized_ds[(0x0011, 0x1010)].value
                )

            if ('MediaStorageSOPInstanceUID' in anonymized_ds.file_meta
                    and anonymized_ds.file_meta.MediaStorageSOPInstanceUID):
                decrypted_media_sop_uid = partially_decrypt_uid(
                    anonymized_ds.file_meta.MediaStorageSOPInstanceUID
                )
                if decrypted_media_sop_uid:
                    anonymized_ds.file_meta.MediaStorageSOPInstanceUID = decrypted_media_sop_uid

            for field, decrypted_value in decrypted_values.items():
                if decrypted_value:
                    setattr(anonymized_ds, field, decrypted_value)

            decrypted_output_path = os.path.join(series_folder, f"decrypted_{instance_file_name}")
            if anonymization_type == 'partial':
                original_decrypted_output_path = decrypted_output_path
                counter = 1
                while os.path.exists(decrypted_output_path):
                    decrypted_output_path = f"{os.path.splitext(original_decrypted_output_path)[0]}_{counter}.dcm"
                    counter += 1
            try:
                anonymized_ds.save_as(decrypted_output_path)
            except Exception:
                pass

    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def process_series(series, study_uid, study_folder, instances_url,
                   patient_name, pseudonymized_id, key_id,
                   anonymization_type, patient_id_mapping):
    """Processa una serie DICOM."""
    series_uid = series['0020000E']['Value'][0]

    if anonymization_type == 'partial':
        encrypted = partially_encrypt_uid_with_kms(key_id, series_uid)
        series_folder_name = encrypted[:45]
    elif anonymization_type == 'irreversible':
        series_folder_name = hash_value(series_uid)[:30]
    elif anonymization_type == 'clear':
        series_folder_name = series_uid
    else:
        return

    series_folder = os.path.join(study_folder, series_folder_name)
    if anonymization_type == 'partial':
        original = series_folder
        counter = 1
        while os.path.exists(series_folder):
            series_folder = f"{original}_{counter}"
            counter += 1

    os.makedirs(series_folder, exist_ok=True)

    try:
        instances = get_instances(study_uid, series_uid, instances_url)
    except Exception:
        return

    for instance in instances:
        process_instance(instance, study_uid, series_uid, series_folder,
                         patient_name, pseudonymized_id, key_id,
                         anonymization_type, patient_id_mapping)


def process_study(study, patient_folder, series_url, instances_url,
                  patient_name, pseudonymized_id, key_id,
                  anonymization_type, patient_id_mapping):
    """Elabora uno studio DICOM."""
    study_uid = study['0020000D']['Value'][0]

    if anonymization_type == 'partial':
        encrypted = partially_encrypt_uid_with_kms(key_id, study_uid)
        study_folder_name = encrypted[:45]
    elif anonymization_type == 'irreversible':
        study_folder_name = hash_value(study_uid)[:45]
    elif anonymization_type == 'clear':
        study_folder_name = study_uid
    else:
        return

    study_folder = os.path.join(patient_folder, study_folder_name)
    if anonymization_type == 'partial':
        counter = 1
        original = study_folder
        while os.path.exists(study_folder):
            study_folder = f"{original}_{counter}"
            counter += 1

    os.makedirs(study_folder, exist_ok=True)

    try:
        series_list = get_series(study_uid, series_url)
    except Exception:
        return

    for series in series_list:
        process_series(series, study_uid, study_folder, instances_url,
                       patient_name, pseudonymized_id, key_id,
                       anonymization_type, patient_id_mapping)


def process_patient(patient_name, original_id, studies_url, series_url,
                    instances_url, pseudonymized_id, key_id,
                    anonymization_type, general_folder, patient_id_mapping):
    """Elabora un singolo paziente."""
    patient_folder_name = generate_patient_folder_name(
        patient_name, anonymization_type, key_id
    )
    if not patient_folder_name:
        return

    patient_folder = os.path.join(general_folder, patient_folder_name)
    if anonymization_type == 'partial':
        original = patient_folder
        counter = 1
        while os.path.exists(patient_folder):
            patient_folder = f"{original}_{counter}"
            counter += 1

    os.makedirs(patient_folder, exist_ok=True)

    try:
        studies = get_studies(original_id, studies_url)
    except Exception:
        return

    for study in studies:
        process_study(study, patient_folder, series_url, instances_url,
                      patient_name, pseudonymized_id, key_id,
                      anonymization_type, patient_id_mapping)


# Funzione principale

def process_patient_list_from_file(csv_path, anonymization_type, output_dir):
    """
    Elabora un file CSV contenente nomi di pazienti.
    Versione standalone che legge il file dal filesystem.

    Args:
        csv_path: Percorso del file CSV
        anonymization_type: 'clear' | 'partial' | 'irreversible'
        output_dir: Directory di output per i file DICOM

    Returns:
        dict con found_patients, not_found_patients, dicom_save_path, pseudonym_map_path
    """
    patients_url = cfg.PACS_PATIENTS_URL
    studies_url = cfg.PACS_STUDIES_URL
    series_url = cfg.PACS_SERIES_URL
    instances_url = cfg.PACS_INSTANCES_URL

    dicom_save_path = os.path.abspath(output_dir)
    os.makedirs(dicom_save_path, exist_ok=True)

    # Leggi il CSV
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f, delimiter=',')

        # Trova la colonna PatientName (case-insensitive)
        fieldnames = [field.strip() for field in reader.fieldnames]
        fieldnames_lower = [f.lower() for f in fieldnames]

        if 'patientname' not in fieldnames_lower:
            raise ValueError(
                f"Il CSV deve contenere una colonna 'PatientName'. "
                f"Colonne trovate: {fieldnames}"
            )

        patient_name_col = fieldnames[fieldnames_lower.index('patientname')]

        found_patients = []
        not_found_patients = []
        patient_data = {}

        for row in reader:
            patient_name = row.get(patient_name_col, '').strip()
            if not patient_name:
                continue

            formatted_name = format_patient_name(patient_name)

            try:
                patient_id = get_patient_id(patient_name, patients_url)
                if patient_id:
                    found_patients.append(formatted_name)
                    patient_data[formatted_name] = patient_id
                    print(f"  [OK] {mask_name(patient_name)}")
                else:
                    not_found_patients.append(formatted_name)
                    print(f"  [NOT FOUND] {mask_name(patient_name)}")
            except Exception as e:
                not_found_patients.append(formatted_name)
                print(f"  [ERROR] {mask_name(patient_name)}: {e}")

    if not found_patients:
        print("\n[ERROR] Nessun paziente trovato sul PACS.")
        return {
            "found_patients": [],
            "not_found_patients": not_found_patients,
            "dicom_save_path": dicom_save_path,
            "pseudonym_map_path": None,
        }

    # Generazione pseudonimi
    pseudonym_map = {}
    patient_id_mapping = {}
    pseudonym_map_path = None

    if anonymization_type != 'clear':
        pseudonym_map, patient_id_mapping = generate_pseudonymized_ids(
            found_patients, patient_data
        )
        pseudonym_map_path = os.path.join(dicom_save_path, "pseudonym_map.csv")
        save_pseudonym_map(pseudonym_map, pseudonym_map_path)
        print(f"\n[INFO] Mappa pseudonimi salvata in: {pseudonym_map_path}")
    else:
        patient_id_mapping = {name: data for name, data in patient_data.items()}

    # Download e anonimizzazione
    key_id = cfg.AWS_KMS_KEY_ID if anonymization_type != 'clear' else None
    total = len(patient_data)

    print(f"\n{'='*60}")
    print(f"Inizio download DICOM per {total} pazienti...")
    print(f"Modalità: {anonymization_type}")
    print(f"Output: {dicom_save_path}")
    print(f"{'='*60}\n")

    for i, (patient_name, patient_id) in enumerate(patient_data.items(), 1):
        pseudonymized_id = pseudonym_map.get(patient_name, patient_id) \
            if anonymization_type != 'clear' else patient_id

        print(f"[{i}/{total}] Processando paziente {mask_name(patient_name)}...")

        process_patient(
            patient_name,
            patient_id,
            studies_url,
            series_url,
            instances_url,
            pseudonymized_id,
            key_id,
            anonymization_type,
            dicom_save_path,
            patient_id_mapping,
        )

    print(f"\n[DONE] Estrazione completata!")
    print(f"  Pazienti trovati: {len(found_patients)}")
    print(f"  Pazienti non trovati: {len(not_found_patients)}")
    print(f"  File salvati in: {dicom_save_path}")

    return {
        "found_patients": found_patients,
        "not_found_patients": not_found_patients,
        "dicom_save_path": dicom_save_path,
        "pseudonym_map_path": pseudonym_map_path,
    }


# Entrypoint CLI

def main():
    if len(sys.argv) != 4:
        print("Uso: python3 extract_dicom.py <csv_file> <anonymization_type> <output_dir>")
        print("  anonymization_type: clear | partial | irreversible")
        sys.exit(1)

    csv_file = sys.argv[1]
    anonymization_type = sys.argv[2]
    output_dir = sys.argv[3]

    if anonymization_type not in ('clear', 'partial', 'irreversible'):
        print(f"[ERROR] Tipo di anonimizzazione non valido: {anonymization_type}")
        print("  Valori validi: clear, partial, irreversible")
        sys.exit(1)

    if not os.path.isfile(csv_file):
        print(f"[ERROR] File CSV non trovato: {csv_file}")
        sys.exit(1)

    # Verifica credenziali AWS se partial
    if anonymization_type == 'partial':
        if not cfg.AWS_KMS_KEY_ID or not cfg.AWS_REGION:
            print("[ERROR] Per la modalità 'partial' è necessario configurare")
            print("  AWS_KMS_KEY_ID e AWS_REGION nel file .env")
            sys.exit(1)

    print(f"\n{'='*60}")
    print(f"ESTRAZIONE DICOM DAL PACS")
    print(f"{'='*60}")
    print(f"CSV:              {csv_file}")
    print(f"Anonimizzazione:  {anonymization_type}")
    print(f"Output:           {output_dir}")
    print(f"PACS URL:         {cfg.PACS_BASE_URL}")
    print(f"{'='*60}\n")

    print("Ricerca pazienti sul PACS...")
    result = process_patient_list_from_file(csv_file, anonymization_type, output_dir)

    # Salva una copia permanente dei file estratti in /app/extractions
    import shutil
    from datetime import datetime

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    extraction_name = f"Extraction_{timestamp}_{anonymization_type}"
    extractions_base = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "extractions")
    extraction_dest = os.path.join(extractions_base, extraction_name)

    if os.path.exists(output_dir) and os.listdir(output_dir):
        shutil.copytree(output_dir, extraction_dest)
        print(f"\n[INFO] Copia permanente salvata in: {extraction_dest}")

    # Scrivi un file di riepilogo per il coordinamento con Nextflow
    summary_path = "extraction_summary.txt"
    with open(summary_path, 'w') as f:
        f.write(f"found={len(result['found_patients'])}\n")
        f.write(f"not_found={len(result['not_found_patients'])}\n")
        if result['not_found_patients']:
            for name in result['not_found_patients']:
                f.write(f"not_found_name={name}\n")
        f.write(f"output_dir={result['dicom_save_path']}\n")
        if result['pseudonym_map_path']:
            f.write(f"pseudonym_map={result['pseudonym_map_path']}\n")


if __name__ == '__main__':
    main()
