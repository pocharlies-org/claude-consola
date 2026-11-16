// The Claude Code transcript read for the one thing the console client needs: the last real model the session used. A message
// counts only if it has content under the flattening the Paseo plugin uses — a tool call becomes one line about it, its result
// becomes its text, thinking is dropped. Pure: strings in, model out, no Node.
// Moved from paseo-sugiere `shared/transcript.ts` (only what the console client reads; the message list and `forService` stay with the plugin).

type Block = { type: "text"; text: string };

function blocks(content: unknown): Block[] {
  if (typeof content === "string") return content.trim() ? [{ type: "text", text: content }] : [];
  if (!Array.isArray(content)) return [];
  const out: Block[] = [];
  for (const part of content) {
    if (part?.type === "text" && typeof part.text === "string" && part.text.trim()) out.push({ type: "text", text: part.text });
    else if (part?.type === "tool_use" && typeof part.name === "string") out.push({ type: "text", text: `[called ${part.name}]` });
    else if (part?.type === "tool_result") {
      const text =
        typeof part.content === "string"
          ? part.content
          : Array.isArray(part.content)
            ? part.content.map((c: any) => (c?.type === "text" ? c.text : "")).join("")
            : "";
      if (text.trim()) out.push({ type: "text", text: `[tool result] ${text.slice(0, 2_000)}` });
    }
    // thinking and redacted_thinking are dropped: they are signed for the model that wrote them and this call has no tools.
  }
  return out;
}

/** The last real model the session used since the transcript's last compaction (null if none: no assistant yet, or only synthetic ones). */
export function lastRealModel(lines: string[]): string | null {
  const start = lines.findLastIndex((l) => l.includes('"compact_boundary"')) + 1;
  let model: string | null = null;
  for (const line of lines.slice(start)) {
    let entry: any;
    try {
      entry = JSON.parse(line);
    } catch {
      continue; // a line cut by a write in progress
    }
    if (entry?.message?.role !== "assistant" || !blocks(entry.message.content).length) continue;
    // "<synthetic>" is what Claude Code writes on messages it made up itself (errors, interruptions): not a model anyone can call.
    const used = entry.message.model;
    if (typeof used === "string" && used.trim() && used !== "<synthetic>") model = used;
  }
  return model;
}
