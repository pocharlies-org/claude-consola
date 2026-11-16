import assert from "node:assert/strict";
import { test } from "node:test";
import { lastRealModel } from "../console/transcript.ts";

const line = (o: unknown) => JSON.stringify(o);

test("un turno solo de tool call cuenta y el último modelo real gana a <synthetic>", () => {
  const model = lastRealModel([
    line({ message: { role: "user", content: "hola" } }),
    line({ message: { role: "assistant", model: "claude-test", content: [{ type: "tool_use", name: "Bash" }] } }),
    line({ message: { role: "user", content: [{ type: "tool_result", content: "42" }] } }),
    line({ message: { role: "assistant", model: "<synthetic>", content: [{ type: "text", text: "fin" }] } }),
  ]);
  assert.equal(model, "claude-test");
});

test("sin turno del asistente no hay modelo", () => {
  assert.equal(lastRealModel([line({ message: { role: "user", content: "solo esto" } })]), null);
});
