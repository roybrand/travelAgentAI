import test from "node:test";
import assert from "node:assert/strict";
import { StateGraph, END } from "../src/graph/stateGraph.js";

test("runs nodes in edge order and merges partial state", async () => {
  const graph = new StateGraph()
    .addNode("addA", async (state) => ({ a: (state.a ?? 0) + 1 }))
    .addNode("addB", async (state) => ({ b: (state.a ?? 0) * 2 }))
    .setEntryPoint("addA")
    .addEdge("addA", "addB")
    .addEdge("addB", END)
    .compile();

  const { state, trace } = await graph.invoke({ a: 0 });

  assert.equal(state.a, 1);
  assert.equal(state.b, 2);
  assert.deepEqual(trace, ["addA", "addB"]);
});

test("throws when a node has no outgoing edge", () => {
  const graph = new StateGraph()
    .addNode("orphan", async (s) => s)
    .setEntryPoint("orphan");

  assert.throws(() => graph.compile(), /no outgoing edge/);
});

test("throws on invoke when a node references an unregistered next node", async () => {
  const graph = new StateGraph()
    .addNode("start", async (s) => s)
    .addEdge("start", "missing")
    .setEntryPoint("start")
    .compile();

  await assert.rejects(() => graph.invoke({}), /Unknown node "missing"/);
});
