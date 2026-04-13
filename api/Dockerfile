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

# AMR BART model (~400MB) — required by amrlib.load_stog_model()
RUN python -c "import site,urllib.request,tarfile,os;url='https://github.com/bjascob/amrlib-models/releases/download/parse_xfm_bart_base-v0_1_0/model_parse_xfm_bart_base-v0_1_0.tar.gz';d=os.path.join(site.getsitepackages()[0],'amrlib','data','model_stog');os.makedirs(os.path.dirname(d),exist_ok=True);print('Downloading AMR BART model...');urllib.request.urlretrieve(url,'/tmp/model.tar.gz');print('Extracting...');t=tarfile.open('/tmp/model.tar.gz');t.extractall(path=os.path.dirname(d));t.close();os.rename(os.path.join(os.path.dirname(d),'model_parse_xfm_bart_base-v0_1_0'),d);os.remove('/tmp/model.tar.gz');print('AMR model ready at',d)"

# Pre-load models to trigger wikimapper DB download (~832MB)
RUN python -c "import sys; sys.path.insert(0, '/app/src'); from text2rdf import load_models; print('Loading models...'); load_models('turtle'); print('Models loaded successfully.')"

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
