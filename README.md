# PRISMO — text-2-rdf

Pipeline para la extracción automática de conocimiento estructurado a partir de texto en lenguaje natural, produciendo grafos de conocimiento RDF/OWL compatibles con los estándares de la Semantic Web.

Incluye una **API HTTP** (FastAPI) y un **frontend web** (React) para convertir texto a ontologías RDF y visualizarlas interactivamente.

## Quickstart con Docker

```bash
podman compose up --build
```

- **Frontend**: http://localhost/prismo
- **API**: http://localhost:8080/v1/to-rdf
- **API docs**: http://localhost:8080/docs
- **Health**: http://localhost:8080/health

> El primer build tarda 10-30 min (descarga y compila modelos de ML ~4 GB). Las siguientes veces usan cache de Podman.

## Uso de la API

```bash
curl -X POST http://localhost:8080/v1/to-rdf \
  -H "Content-Type: application/json" \
  -d '{"text": "Mary runs to the store.", "format": "turtle", "level": 3}'
```

**Parámetros:**

| Campo | Tipo | Default | Descripción |
|---|---|---|---|
| `text` | string (requerido, max 5000 chars) | — | Texto a convertir |
| `format` | `"turtle"` \| `"xml"` \| `"n3"` \| `"nt"` | `"turtle"` | Formato de serialización RDF |
| `level` | `1` \| `2` \| `3` | `3` | Nivel de complejidad (1=simple, 2=intermedio, 3=completo) |

## Arquitectura

```
┌─────────────────────────────────────────────────────┐
│                   Podman Compose                     │
│                                                      │
│  ┌──────────────┐       ┌────────────────────────┐   │
│  │   Frontend   │       │         API            │   │
│  │  React+Vite  │──/v1──│  FastAPI + uvicorn     │   │
│  │  Nginx :80   │       │  :8000                 │   │
│  │              │       │                        │   │
│  │ /prismo      │       │  ┌──────────────────┐  │   │
│  │  - Form      │       │  │ PipelineService  │  │   │
│  │  - Graph     │       │  │ (thread-safe)    │  │   │
│  └──────────────┘       │  └────────┬─────────┘  │   │
│                          │           │            │   │
│                          │  ┌────────▼─────────┐  │   │
│                          │  │  text2rdf.py     │  │   │
│                          │  │  Text→AMR→RDF    │  │   │
│                          │  └──────────────────┘  │   │
│                          └────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

### Pipeline interno

```
Texto → spaCy (split) → BART (AMR) → py-amr2fred (RDF/OWL) → rdflib (serialize)
```

| Componente | Tecnología | Naturaleza |
|---|---|---|
| Sentence splitting | spaCy `en_core_web_sm` | Parser estadístico (~12 MB) |
| Texto → AMR | BART fine-tuneado (amrlib) | Transformer seq2seq (~558 MB) |
| AMR → RDF/OWL | py-amr2fred | Pipeline determinista: ODPs + WSD |
| Serialización | rdflib | Grafo RDF |

## Frontend

La UI en `/prismo` permite:

- Ingresar texto en un formulario
- Seleccionar formato RDF y nivel de complejidad
- Visualizar la ontología como un grafo interactivo (zoom, pan, click en nodos)
- Ver el RDF crudo en formato Turtle

El grafo se renderiza con `react-force-graph-2d` y los nodos se colorean por namespace (FRED, DUL, WordNet, Schema.org, etc.).

## Stack tecnológico

**Backend:** Python 3.13, FastAPI, uvicorn, amrlib, py-amr2fred, rdflib, spaCy, PyTorch

**Frontend:** React 19, Vite, react-force-graph-2d, n3.js

**Infra:** Podman, Podman Compose, Nginx

## Instalación local (sin Podman)

```bash
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r api/requirements-api.txt
python -m spacy download en_core_web_sm
python -c "import nltk; nltk.download('wordnet'); nltk.download('omw-1.4')"
```

Descargar modelo AMR desde [amrlib-models releases](https://github.com/bjascob/amrlib-models/releases) (`model_parse_xfm_bart_base-v0_1_0`) y ubicarlo en `venv/lib/python3.XX/site-packages/amrlib/data/model_stog`.

Luego correr:

```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

## Niveles de complejidad

| Nivel | Descripción | Triples aproximados |
|---|---|---|
| 1 — Simple | Núcleo esencial (DUL + FRED) | ~40% |
| 2 — Intermedio | Sin VerbAtlas ni Wikidata | ~75% |
| 3 — Completo | Todos los enriquecimientos | 100% |

## Formatos de salida

| Formato | Content-Type | Uso |
|---|---|---|
| `turtle` (default) | `text/turtle` | Legibilidad, depuración |
| `xml` | `application/rdf+xml` | OWL (Protégé, HermiT) |
| `n3` | `text/n3` | Razonadores N3 |
| `nt` | `text/plain` | Triplestores (Jena, Blazegraph) |

## Limitaciones

- Parser AMR entrenado en inglés (corpus LDC2020T02)
- Oraciones largas o con jerga técnica pueden producir grafos subóptimos
- Los servicios externos (WSD, Framester SPARQL) degradan gracefulmente si no hay red
- La pipeline no es thread-safe — las requests se serializan con un lock
