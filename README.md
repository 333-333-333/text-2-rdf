# text-2-rdf

Pipeline local para la extracción automática de conocimiento estructurado a partir de texto en lenguaje natural, produciendo grafos de conocimiento RDF/OWL compatibles con los estándares de la Semantic Web.

## Fundamentos teóricos

### Abstract Meaning Representation (AMR)

AMR es un formalismo de representación semántica que codifica el significado de una oración como un grafo dirigido y acíclico (DAG), de naturaleza agnóstica respecto a la sintaxis superficial. Los nodos representan conceptos (instancias de predicados o entidades) y los arcos representan relaciones semánticas entre ellos, expresadas mediante roles del esquema PropBank.

Una propiedad central de AMR es su invarianza ante transformaciones sintácticas: oraciones en voz activa, pasiva o nominalizaciones del mismo evento producen representaciones isomorfas. Esto la convierte en una representación adecuada como paso intermedio hacia la formalización semántica.

### FRED y los Ontology Design Patterns

FRED (*Formal Reading for the Semantic Web*) es un método de machine reading que transforma grafos AMR en grafos RDF/OWL mediante la aplicación sistemática de Ontology Design Patterns (ODP). El proceso sigue la semántica formal de la Discourse Representation Theory (DRT) y el modelo neo-davidsoniano de eventos, enriqueciendo las instancias extraídas con vínculos a recursos léxicos y ontológicos externos:

- **PropBank** — frames de eventos y asignación de roles semánticos (ARG0, ARG1, …)
- **FrameNet / VerbAtlas** — semántica léxica basada en marcos
- **WordNet** — desambiguación del sentido de las palabras (WSD)
- **DUL (DOLCE+DnS Ultralite)** — ontología de alto nivel para la representación de eventos, roles y participantes
- **Wikidata / DBpedia** — resolución de entidades nombradas a URIs canónicas

El resultado es un grafo OWL-compliant, consultable mediante SPARQL y alineado con los principios de Linked Open Data.

## Arquitectura del pipeline

```
Texto en lenguaje natural
        │
        ▼
┌───────────────────┐
│  Sentence Split   │  spaCy — parser estadístico
└───────────────────┘
        │  Lista de oraciones
        ▼
┌───────────────────┐
│   AMR Parsing     │  BART fine-tuneado (amrlib)
│   texto → AMR     │  Transformer seq2seq supervisado
└───────────────────┘
        │  Grafos AMR en notación PENMAN
        ▼
┌───────────────────┐
│  AMR → RDF/OWL    │  py-amr2fred
│  (semántica FRED) │  Reglas formales + ODPs + WSD
└───────────────────┘
        │  Triples RDF
        ▼
┌───────────────────┐
│  Serialización    │  rdflib
│  Turtle / OWL-XML │
└───────────────────┘
        │
        ▼
  output.rdf / .ttl
```

## Naturaleza de los componentes

Este pipeline **no emplea modelos de lenguaje de gran escala (LLMs) de propósito general**. Todos los componentes son sistemas NLP de propósito específico con comportamiento determinista.

| Componente | Modelo | Naturaleza |
|---|---|---|
| Sentence splitting | spaCy `en_core_web_sm` | Parser estadístico basado en reglas y perceptrón (~12 MB) |
| Texto → AMR | BART fine-tuneado (amrlib) | Transformer seq2seq supervisado, especializado exclusivamente en AMR parsing |
| AMR → RDF/OWL | py-amr2fred | Pipeline determinista: mapeo por reglas formales sobre ODPs y ontologías estándar |
| Serialización | rdflib | Librería de manipulación de grafos RDF, sin componente de aprendizaje |

### BART como parser AMR

BART (*Bidirectional and Auto-Regressive Transformer*) es un modelo seq2seq con encoder bidireccional y decoder autoregresivo, publicado por Meta AI en 2019. En su versión base, se pre-entrena sobre texto general mediante denoising: el modelo aprende a reconstruir secuencias corrompidas, adquiriendo representaciones lingüísticas de propósito general.

amrlib aplica fine-tuning supervisado sobre el corpus LDC2020T02 (AMR 3.0), convirtiendo BART en un parser especializado cuya única función es mapear oraciones en inglés a grafos AMR en notación PENMAN. A diferencia de los LLMs generativos, este modelo no genera texto libre ni responde instrucciones: su espacio de salida está restringido a la gramática formal de AMR.

| Dimensión | BART fine-tuneado (AMR parser) | LLM generativo |
|---|---|---|
| Tarea | AMR parsing (única) | Instrucción general (abierta) |
| Tipo de output | Grafo estructurado (PENMAN) | Texto libre |
| Tamaño | ~400 MB – 1.4 GB | 7 GB – cientos de GB |
| Entrenamiento | Supervisado con corpus anotado | Pre-entrenamiento masivo + RLHF |
| Determinismo | Alto | Bajo (temperatura, sampling) |
| Interpretabilidad | Alta (output formal verificable) | Baja (caja negra) |

## Stack tecnológico

| Librería | Versión mínima | Rol |
|---|---|---|
| `amrlib` | 0.8.0 | AMR parsing |
| `py-amr2fred` | 0.2.3 | AMR → RDF/OWL |
| `rdflib` | 7.1.1 | Manipulación y serialización de grafos RDF |
| `spacy` | 3.0 | Tokenización y sentence splitting |
| `transformers` | 4.16 | Backend de inferencia para BART |
| `torch` | 1.6 | Framework de deep learning |
| `penman` | 1.1.0 | Parsing de grafos AMR en notación PENMAN |
| `nltk` | 3.9.1 | Recursos léxicos (WordNet) |

## Requisitos del sistema

- Python 3.11+
- ~2 GB de espacio en disco (modelo AMR + base de datos wikimapper opcional)
- CPU suficiente para inferencia (GPU opcional, mejora velocidad)

## Instalación

### 1. Entorno virtual

```fish
python3.11 -m venv venv
source venv/bin/activate.fish
```

### 2. Dependencias

```fish
pip install -r requirements.txt
python -m spacy download en_core_web_sm
python -c "import nltk; nltk.download('wordnet'); nltk.download('omw-1.4')"
```

### 3. Modelo AMR

Descargar desde [amrlib-models releases](https://github.com/bjascob/amrlib-models/releases):

| Modelo | Tamaño | SMATCH |
|---|---|---|
| `model_parse_xfm_bart_large-v0_1_0` | 1.4 GB | 83.7 |
| `model_parse_xfm_bart_base-v0_1_0` | ~400 MB | 82.3 |

```fish
tar -xzf ~/Downloads/model_parse_xfm_bart_base-v0_1_0.tar.gz \
    -C venv/lib/python3.XX/site-packages/amrlib/data/

mv venv/lib/python3.XX/site-packages/amrlib/data/model_parse_xfm_bart_base-v0_1_0 \
   venv/lib/python3.XX/site-packages/amrlib/data/model_stog
```

> Reemplazar `3.XX` con la versión de Python del entorno (ej. `3.13`).

## Uso

```fish
# Conversión básica (output: input.rdf)
python text2rdf.py input.txt

# Output explícito
python text2rdf.py input.txt output.rdf

# Formato de serialización
python text2rdf.py input.txt --format xml   # RDF/XML — OWL compatible
python text2rdf.py input.txt --format n3    # Notation3
python text2rdf.py input.txt --format nt    # N-Triples

# Sin enriquecimiento Wikidata (omite descarga de ~832 MB)
python text2rdf.py input.txt --no-postprocess
```

## Formatos de salida

| Flag | Formato | Uso recomendado |
|---|---|---|
| `turtle` (default) | Turtle | Legibilidad, depuración |
| `xml` | RDF/XML | Compatibilidad con herramientas OWL (Protégé, HermiT) |
| `n3` | Notation3 | Interoperabilidad con razonadores N3 |
| `nt` | N-Triples | Ingesta en triplestores (Apache Jena, Blazegraph) |

## Limitaciones

- El parser AMR está entrenado exclusivamente en inglés (corpus LDC2020T02). Para otros idiomas, py-amr2fred ofrece el parámetro `multilingual=True`, que delega el parsing a la API pública USeA del CNR Italia, requiriendo conectividad de red.
- La calidad del grafo RDF está acotada por la calidad del AMR generado. Oraciones largas, con sintaxis compleja o jerga técnica pueden producir grafos AMR subóptimos.
- La resolución de entidades nombradas a URIs de Wikidata/DBpedia requiere la descarga de `index_enwiki-latest.db` (~832 MB comprimido) en la primera ejecución con post-procesamiento habilitado.
