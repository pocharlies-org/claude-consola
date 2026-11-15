import assert from "node:assert/strict";
import { test } from "node:test";
import { transcriptMessages } from "../console/transcript.ts";

const line = (o: unknown) => JSON.stringify(o);

test("aplana tool calls y conserva el último modelo real", () => {
  const { messages, model } = transcriptMessages([
    line({ message: { role: "user", content: "hola" } }),
    line({ message: { role: "assistant", model: "claude-test", content: [{ type: "tool_use", name: "Bash" }] } }),
    line({ message: { role: "user", content: [{ type: "tool_result", content: "42" }] } }),
    line({ message: { role: "assistant", model: "<synthetic>", content: [{ type: "text", text: "fin" }] } }),
  ]);
  assert.equal(model, "claude-test");
  assert.deepEqual(messages.map((m) => m.content.map((b) => b.text).join("|")), ["hola", "[called Bash]", "[tool result] 42", "fin"]);
});

test("sin turno del asistente no hay modelo", () => {
  assert.equal(transcriptMessages([line({ message: { role: "user", content: "solo esto" } })]).model, null);
});
