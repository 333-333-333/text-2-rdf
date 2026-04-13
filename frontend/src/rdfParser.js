import { Parser } from 'n3';

/**
 * Parse an RDF string (Turtle, N-Triples, N3, etc.) into an array of triple objects.
 * @param {string} rdfString - The RDF serialization to parse.
 * @param {string} format - The MIME type of the format (default: text/turtle).
 * @returns {Promise<Array<{subject: string, predicate: string, object: string}>>}
 */
export async function parseRdfToGraph(rdfString, format = 'text/turtle') {
  const parser = new Parser({ format });
  const triples = [];

  // n3 Parser.parse is callback-based: it calls back for each quad, then with null/error at the end
  await new Promise((resolve, reject) => {
    parser.parse(rdfString, (error, quad) => {
      if (error) {
        reject(error);
        return;
      }
      if (quad) {
        triples.push({
          subject: quad.subject.value,
          predicate: quad.predicate.value,
          object: quad.object.value,
        });
      } else {
        // quad is null → end of stream
        resolve();
      }
    });
  });

  return triples;
}

/**
 * Convert an array of RDF triples into the node-link data format expected by react-force-graph-2d.
 * Literal objects are stored as metadata on the subject node rather than rendered as separate nodes.
 */
export function buildForceGraphData(triples) {
  const nodes = new Map();
  const links = [];

  triples.forEach(({ subject, predicate, object }) => {
    if (!nodes.has(subject)) {
      nodes.set(subject, createNode(subject));
    }

    const isObjectUri = object.startsWith('http://') || object.startsWith('https://');
    if (isObjectUri) {
      if (!nodes.has(object)) {
        nodes.set(object, createNode(object));
      }
      links.push({
        source: subject,
        target: object,
        label: shortLabel(predicate),
      });
    } else {
      // Literal — attach to the subject node for tooltip display
      const node = nodes.get(subject);
      if (!node.literals) node.literals = [];
      node.literals.push({ predicate: shortLabel(predicate), value: object });
    }
  });

  return {
    nodes: Array.from(nodes.values()),
    links,
  };
}

// --- Helpers ---

function createNode(uri) {
  return {
    id: uri,
    name: shortLabel(uri),
    color: getColorForNamespace(uri),
    fullUri: uri,
  };
}

/**
 * Extract a human-readable short label from a URI.
 * Tries the fragment identifier first (#), then the last path segment.
 */
export function shortLabel(uri) {
  try {
    const hash = uri.indexOf('#');
    if (hash !== -1) return uri.substring(hash + 1);
    const slash = uri.lastIndexOf('/');
    if (slash !== -1) return uri.substring(slash + 1);
    return uri;
  } catch {
    return uri;
  }
}

/**
 * Return a colour keyed by the namespace that the URI belongs to.
 */
export function getColorForNamespace(uri) {
  const colors = {
    'fred': '#4CAF50',       // FRED domain ontology
    'framester': '#2196F3',   // Framester / PropBank rolesets
    'schema': '#FF9800',      // schema.org
    'wikidata': '#9C27B0',    // Wikidata
    'dul': '#F44336',         // DUL (Dolce Ultra Light)
    'rdf': '#607D8B',         // RDF core vocabulary
    'rdfs': '#795548',        // RDFS vocabulary
    'owl': '#00BCD4',         // OWL vocabulary
    'verbatlas': '#E91E63',   // VerbAtlas frames
    'boxer': '#8BC34A',       // Boxer / Boxing ontology
    'vnrole': '#FF5722',      // VerbNet roles
  };

  const lower = uri.toLowerCase();
  for (const [ns, color] of Object.entries(colors)) {
    if (lower.includes(ns)) return color;
  }
  return '#9E9E9E'; // default grey for unknown namespaces
}
