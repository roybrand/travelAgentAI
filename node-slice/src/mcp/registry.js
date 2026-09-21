import { ToolRegistry } from "./toolRegistry.js";
import { flightsTool } from "./tools/flightsTool.js";
import { hotelsTool } from "./tools/hotelsTool.js";

export const registry = new ToolRegistry()
  .register(flightsTool)
  .register(hotelsTool);
