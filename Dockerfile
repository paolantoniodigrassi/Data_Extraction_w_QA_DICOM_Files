FROM python:3.11-slim

# Installa Java (per Nextflow) e dipendenze di sistema
RUN apt-get update && apt-get install -y \
    openjdk-21-jdk \
    curl \
    bash \
    && rm -rf /var/lib/apt/lists/*

# Installa Nextflow
RUN curl -s https://get.nextflow.io | bash && \
    mv nextflow /usr/local/bin/ && \
    chmod +x /usr/local/bin/nextflow

# Working directory
WORKDIR /app

# Installa dipendenze Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia il progetto
COPY . .

# Rende eseguibile lo script CLI
RUN chmod +x run_pipeline.sh

# Directory di default per dati e output
RUN mkdir -p /app/data /app/output

# Comando di default: script interattivo
CMD ["bash", "run_pipeline.sh"]
