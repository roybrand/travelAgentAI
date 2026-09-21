// Mock of the tool-contract shape used by the Model Context Protocol: each tool
// is registered with a name, description, and JSON-schema-like input contract,
// then invoked by name rather than imported and called directly.
//
// This is NOT the real MCP wire protocol (no transport, no JSON-RPC, no
// separate server process) — it exists so graph nodes call tools the same way
// they would through a real MCP client (`registry.call("searchFlights", input)`),
// making a later swap to `@modelcontextprotocol/sdk` a wiring change, not a
// rewrite of node logic.

export class ToolRegistry {
  constructor() {
    this.tools = new Map();
  }

  register({ name, description, inputSchema, handler }) {
    if (this.tools.has(name)) {
      throw new Error(`Tool "${name}" already registered`);
    }
    this.tools.set(name, { name, description, inputSchema, handler });
    return this;
  }

  list() {
    return [...this.tools.values()].map(({ handler, ...meta }) => meta);
  }

  async call(name, input) {
    const tool = this.tools.get(name);
    if (!tool) throw new Error(`Unknown tool "${name}"`);
    assertRequiredFields(tool.name, tool.inputSchema, input);
    return tool.handler(input);
  }
}

function assertRequiredFields(toolName, schema, input) {
  const required = schema?.required ?? [];
  const missing = required.filter((field) => input?.[field] === undefined || input[field] === null);
  if (missing.length > 0) {
    throw new Error(`Tool "${toolName}" missing required field(s): ${missing.join(", ")}`);
  }
}
