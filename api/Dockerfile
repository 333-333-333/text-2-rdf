FROM python:3.13-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Python deps (pipeline + API)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api/requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

# spaCy model
RUN python -m spacy download en_core_web_sm

# NLTK data
RUN python -c "import nltk; nltk.download('wordnet'); nltk.download('omw-1.4')"

# Application code
COPY src/ /app/src/
COPY api/ /app/api/

# Pre-download wikimapper DB (py-amr2fred needs it)
# This is ~832MB compressed, triggers on first use
RUN python -c "import sys; sys.path.insert(0, '/app/src'); from text2rdf import load_models; print('Loading models to trigger wikimapper download...'); load_models('turtle'); print('Models loaded successfully.')"

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
