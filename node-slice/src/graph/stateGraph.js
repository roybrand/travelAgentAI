// Minimal state-graph orchestration engine.
//
// Mirrors the shape of LangGraph.js's StateGraph (addNode/addEdge/setEntryPoint/compile/invoke)
// so the node functions written against this engine can be rewired onto the real
// `@langchain/langgraph` package later with no changes to node logic — only the
// wiring in graph.js would change.

export const END = Symbol("END");

export class StateGraph {
  constructor() {
    this.nodes = new Map();
    this.edges = new Map();
    this.entry = null;
  }

  addNode(name, fn) {
    if (this.nodes.has(name)) {
      throw new Error(`Node "${name}" already registered`);
    }
    this.nodes.set(name, fn);
    return this;
  }

  addEdge(from, to) {
    this.edges.set(from, to);
    return this;
  }

  setEntryPoint(name) {
    this.entry = name;
    return this;
  }

  compile() {
    if (!this.entry) throw new Error("Graph has no entry point");
    for (const name of this.nodes.keys()) {
      if (!this.edges.has(name)) {
        throw new Error(`Node "${name}" has no outgoing edge (did you forget addEdge(..., END)?)`);
      }
    }
    return new CompiledGraph(this.nodes, this.edges, this.entry);
  }
}

class CompiledGraph {
  constructor(nodes, edges, entry) {
    this.nodes = nodes;
    this.edges = edges;
    this.entry = entry;
  }

  async invoke(initialState) {
    let state = { ...initialState };
    let current = this.entry;
    const trace = [];

    while (current && current !== END) {
      const fn = this.nodes.get(current);
      if (!fn) throw new Error(`Unknown node "${String(current)}"`);
      const partial = await fn(state);
      state = { ...state, ...partial };
      trace.push(current);
      current = this.edges.get(current);
    }

    return { state, trace };
  }
}
