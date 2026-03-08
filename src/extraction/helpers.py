import re
import unicodedata

def mask_name(name):
    """
    Maschera il nome del paziente sostituendo la parte visibile con iniziali.

    Rimuove gli eventuali underscore tra nome e cognome e restituisce
    una rappresentazione mascherata del nome. La parte visibile del nome
    è rappresentata dalla prima lettera maiuscola seguita da asterischi.

    Args:
        name (str): Il nome del paziente da mascherare.

    Returns:
        str: Il nome mascherato. Se il nome contiene due parti, verrà
        restituita la forma, ad esempio, 'N* C*'. Se il nome ha una sola parte,
        verrà restituita, ad esempio, la forma 'N*'.
    """
    if not isinstance(name, str):
        raise ValueError("Il nome deve essere una stringa")
    # Rimuove gli eventuali underscore tra nome e cognome
    name = name.replace('_', ' ')
    parts = name.split()
    if len(parts) == 2:  # nome e cognome
        first_initial = parts[0][0].upper() + '*' * (len(parts[0]) - 1)
        last_initial = parts[1][0].upper() + '*' * (len(parts[1]) - 1)
        return f"{first_initial} {last_initial}"
    else:
        return name[0].upper() + '*' * (len(name) - 1)

def format_patient_name(name):
    """
    Normalizzazione nome del paziente per una gestione coerente.

    Rimuove caratteri non validi e normalizza il nome per evitare
    problemi di formattazione. Sostituisce gli spazi con underscore
    e rimuove accenti e caratteri speciali.

    Args:
        name (str): Il nome del paziente da formattare.

    Returns:
        str: Il nome formattato, con gli spazi sostituiti da underscore,
        caratteri speciali rimossi e normalizzato per garantire coerenza.
    """
    # Rimuove eventuali caratteri '^' e spazi multipli, quindi sostituisce con un underscore
    formatted_name = name.replace('^', ' ').strip()
    
    # Normalizza il testo per rimuovere accenti e caratteri speciali
    formatted_name = unicodedata.normalize('NFD', formatted_name)
    formatted_name = re.sub(r"[\u0300-\u036f]", "", formatted_name)  # Rimuove gli accenti
    
    # Rimuove apostrofi e accenti
    formatted_name = formatted_name.replace("'", "").replace("’", "").replace("`", "")
    
    # Sostituisce gli spazi con underscore
    formatted_name = '_'.join(formatted_name.split())
    return formatted_name

