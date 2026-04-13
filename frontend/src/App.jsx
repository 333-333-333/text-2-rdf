import { useState, useRef, useCallback, useEffect } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { parseRdfToGraph, buildForceGraphData } from './rdfParser';
import './App.css';

// RDF format options mapped to MIME types the n3 parser understands
const RDF_FORMATS = {
  turtle: 'text/turtle',
  xml: 'application/rdf+xml',
  n3: 'text/n3',
  nt: 'application/n-triples',
};

const API_ENDPOINT = '/v1/to-rdf';
const FETCH_TIMEOUT_MS = 120_000;

function App() {
  const [inputText, setInputText] = useState('');
  const [rdfFormat, setRdfFormat] = useState('turtle');
  const [complexity, setComplexity] = useState('3');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [graphData, setGraphData] = useState(null);
  const [rawRdf, setRawRdf] = useState('');
  const [showRaw, setShowRaw] = useState(false);
  const [selectedNode, setSelectedNode] = useState(null);

  const graphRef = useRef(null);
  const firstRender = useRef(true);

  // Zoom to fit when graph data first appears
  useEffect(() => {
    if (graphData && graphRef.current && firstRender.current) {
      const timer = setTimeout(() => {
        graphRef.current.zoomToFit(400, 60);
        firstRender.current = false;
      }, 600);
      return () => clearTimeout(timer);
    }
    if (!graphData) {
      firstRender.current = true;
    }
  }, [graphData]);

  const handleSubmit = useCallback(async (e) => {
    e.preventDefault();
    setError(null);
    setGraphData(null);
    setRawRdf('');
    setSelectedNode(null);
    firstRender.current = true;

    if (!inputText.trim()) {
      setError('Please enter some text to convert.');
      return;
    }

    setLoading(true);

    try {
      // POST to API with timeout — UC Main Flow Step 2
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);

      const response = await fetch(API_ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: inputText.trim(),
          format: rdfFormat,
          level: parseInt(complexity, 10),
        }),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        let message = `Server error (${response.status})`;
        try {
          const body = await response.json();
          message = body.detail || message;
        } catch {
          /* body wasn't JSON */
        }
        throw new Error(message);
      }

      const rdfText = await response.text();
      setRawRdf(rdfText);

      // Parse RDF into triples and build graph data — UC Main Flow Step 3
      const triples = await parseRdfToGraph(rdfText, RDF_FORMATS[rdfFormat]);
      const data = buildForceGraphData(triples);
      setGraphData(data);
    } catch (err) {
      if (err.name === 'AbortError') {
        setError('Request timed out. The server took too long to respond. Please try again.');
      } else {
        setError(err.message || 'An unexpected error occurred.');
      }
    } finally {
      setLoading(false);
    }
  }, [inputText, rdfFormat, complexity]);

  // --- Node interaction callbacks ---

  const handleNodeClick = useCallback((node) => {
    setSelectedNode(node);
    graphRef.current?.centerAt(node.x, node.y, 600);
    graphRef.current?.zoom(2, 600);
  }, []);

  const handleBackgroundClick = useCallback(() => {
    setSelectedNode(null);
  }, []);

  // --- Render helpers ---

  const renderGraphLegend = () => (
    <div className="graph-legend">
      <span className="legend-title">Namespaces</span>
      {[
        ['fred', '#4CAF50', 'FRED'],
        ['framester', '#2196F3', 'Framester'],
        ['schema', '#FF9800', 'Schema.org'],
        ['dul', '#F44336', 'DUL'],
        ['owl', '#00BCD4', 'OWL'],
        ['rdfs', '#795548', 'RDFS'],
        ['verbatlas', '#E91E63', 'VerbAtlas'],
      ].map(([ns, color, label]) => (
        <span key={ns} className="legend-item">
          <span className="legend-dot" style={{ backgroundColor: color }} />
          {label}
        </span>
      ))}
    </div>
  );

  return (
    <div className="app">
      {/* Header */}
      <header className="header">
        <h1 className="header-title">PRISMO</h1>
        <p className="header-subtitle">Text to RDF Ontology</p>
      </header>

      {/* Main layout: input form + graph */}
      <div className="main-layout">
        {/* Left panel: text input form */}
        <aside className="panel panel-input">
          <form onSubmit={handleSubmit} className="input-form">
            <label htmlFor="text-input" className="form-label">
              Input Text
            </label>
            <textarea
              id="text-input"
              className="form-textarea"
              placeholder="Enter text to convert to RDF ontology..."
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              rows={8}
              disabled={loading}
            />

            <div className="form-row">
              <div className="form-field">
                <label htmlFor="rdf-format" className="form-label-sm">RDF Format</label>
                <select
                  id="rdf-format"
                  value={rdfFormat}
                  onChange={(e) => setRdfFormat(e.target.value)}
                  disabled={loading}
                >
                  <option value="turtle">Turtle</option>
                  <option value="xml">RDF/XML</option>
                  <option value="n3">N3</option>
                  <option value="nt">N-Triples</option>
                </select>
              </div>
              <div className="form-field">
                <label htmlFor="complexity" className="form-label-sm">Complexity</label>
                <select
                  id="complexity"
                  value={complexity}
                  onChange={(e) => setComplexity(e.target.value)}
                  disabled={loading}
                >
                  <option value="1">1 — Simple</option>
                  <option value="2">2 — Intermediate</option>
                  <option value="3">3 — Complete</option>
                </select>
              </div>
            </div>

            <button
              type="submit"
              className="btn-submit"
              disabled={loading || !inputText.trim()}
            >
              {loading ? (
                <>
                  <span className="spinner" />
                  Processing…
                </>
              ) : (
                'Generate Ontology'
              )}
            </button>
          </form>

          {/* Error display */}
          {error && (
            <div className="error-banner">
              <strong>Error:</strong> {error}
            </div>
          )}

          {/* Selected node detail */}
          {selectedNode && (
            <div className="node-detail">
              <h3 className="node-detail-title">{selectedNode.name}</h3>
              <p className="node-detail-uri" title={selectedNode.fullUri}>{selectedNode.fullUri}</p>
              {selectedNode.literals?.length > 0 && (
                <ul className="node-detail-literals">
                  {selectedNode.literals.map((lit, i) => (
                    <li key={i}>
                      <strong>{lit.predicate}:</strong> {lit.value}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </aside>

        {/* Right panel: graph visualisation */}
        <section className="panel panel-graph">
          {renderGraphLegend()}

          {graphData ? (
            <ForceGraph2D
              ref={graphRef}
              graphData={graphData}
              nodeId="id"
              nodeLabel="fullUri"
              nodeColor="color"
              nodeVal={() => 6}
              nodeCanvasObject={(node, ctx, globalScale) => {
                const label = node.name;
                const fontSize = 12 / globalScale;
                ctx.font = `${fontSize}px Inter, sans-serif`;
                const textWidth = ctx.measureText(label).width;
                const bgWidth = textWidth + 6;
                const bgHeight = fontSize + 4;

                // Label background pill
                const x = node.x - bgWidth / 2;
                const y = node.y - bgHeight / 2;
                ctx.fillStyle = 'rgba(30, 30, 46, 0.85)';
                ctx.beginPath();
                ctx.roundRect(x, y, bgWidth, bgHeight, 3);
                ctx.fill();

                // Label text
                ctx.fillStyle = node.color;
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.fillText(label, node.x, node.y + 1);
              }}
              nodeCanvasObjectMode={() => 'replace'}
              linkDirectionalArrowLength={4}
              linkDirectionalArrowRelPos={0.9}
              linkColor={() => 'rgba(255, 255, 255, 0.15)'}
              linkWidth={1}
              backgroundColor="#1e1e2e"
              onNodeClick={handleNodeClick}
              onBackgroundClick={handleBackgroundClick}
              enableNodeDrag={true}
              cooldownTicks={200}
              warmupTicks={50}
            />
          ) : (
            <div className="empty-state">
              {loading ? (
                <>
                  <span className="spinner spinner-lg" />
                  <p>Generating ontology… this may take a moment.</p>
                </>
              ) : (
                <p>Enter text and click <strong>Generate</strong> to visualize the ontology.</p>
              )}
            </div>
          )}

          {/* Collapsible raw RDF output */}
          {rawRdf && (
            <div className="raw-output-section">
              <button
                type="button"
                className="btn-toggle-raw"
                onClick={() => setShowRaw((v) => !v)}
              >
                {showRaw ? '▾ Hide Raw RDF' : '▸ Show Raw RDF'}
              </button>
              {showRaw && (
                <pre className="raw-rdf">{rawRdf}</pre>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

export default App;
