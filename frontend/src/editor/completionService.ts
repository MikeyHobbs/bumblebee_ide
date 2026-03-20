/**
 * Graph-aware completion service for Monaco.
 *
 * Handles context detection, caching, and Monaco type mapping.
 */

import type * as Monaco from "monaco-editor";
import { fetchCompletions, type GraphCompletionItem } from "@/api/suggestions";
import { useEditorStore } from "@/store/editorStore";

// --- Cache ---

interface CacheEntry {
  items: GraphCompletionItem[];
  timestamp: number;
}

const CACHE_TTL_MS = 30_000;
const cache = new Map<string, CacheEntry>();

function getCached(key: string): GraphCompletionItem[] | null {
  const entry = cache.get(key);
  if (!entry) return null;
  if (Date.now() - entry.timestamp > CACHE_TTL_MS) {
    cache.delete(key);
    return null;
  }
  return entry.items;
}

function setCache(key: string, items: GraphCompletionItem[]): void {
  cache.set(key, { items, timestamp: Date.now() });
  // Evict old entries if cache grows too large
  if (cache.size > 100) {
    const oldest = [...cache.entries()].sort((a, b) => a[1].timestamp - b[1].timestamp);
    for (let i = 0; i < 20; i++) {
      cache.delete(oldest[i]![0]);
    }
  }
}

// --- In-flight request tracking ---

let currentAbort: AbortController | null = null;

// --- Context detection ---

interface DetectedContext {
  trigger: string;
  params: Record<string, unknown>;
  cacheKey: string;
}

function detectContext(
  model: Monaco.editor.ITextModel,
  position: Monaco.Position,
): DetectedContext | null {
  const lineContent = model.getLineContent(position.lineNumber);
  const textBeforeCursor = lineContent.substring(0, position.column - 1);

  // 1. Dot access: `something.`
  const dotMatch = textBeforeCursor.match(/(\w+)\.\s*(\w*)$/);
  if (dotMatch) {
    const objectName = dotMatch[1]!;
    return {
      trigger: "member_access",
      params: { object_name: objectName },
      cacheKey: `member_access:${objectName}`,
    };
  }

  // 2. Import: `from xxx import` or `import xxx`
  const fromImportMatch = textBeforeCursor.match(/from\s+([\w.]+)\s+import\s*(\w*)$/);
  if (fromImportMatch) {
    const prefix = fromImportMatch[1]!;
    return {
      trigger: "import",
      params: { module_prefix: prefix },
      cacheKey: `import:${prefix}`,
    };
  }
  const importMatch = textBeforeCursor.match(/import\s+([\w.]+)$/);
  if (importMatch) {
    const prefix = importMatch[1]!;
    return {
      trigger: "import",
      params: { module_prefix: prefix },
      cacheKey: `import:${prefix}`,
    };
  }

  // 3. Variable consumer: inside function call parens with a variable name
  // e.g. `func(existing_var` or `func(a, existing_var`
  const callMatch = textBeforeCursor.match(/\w+\([^)]*?(\w{3,})$/);
  if (callMatch) {
    const varName = callMatch[1]!;
    return {
      trigger: "variable_consumer",
      params: { variable_name: varName },
      cacheKey: `variable_consumer:${varName}`,
    };
  }

  // 4. General: bare word >= 3 chars
  const wordMatch = textBeforeCursor.match(/(\w{3,})$/);
  if (wordMatch) {
    const query = wordMatch[1]!;
    return {
      trigger: "general",
      params: { query },
      cacheKey: `general:${query}`,
    };
  }

  return null;
}

// --- Monaco mapping ---

function mapKind(kind: string, monaco: typeof Monaco): Monaco.languages.CompletionItemKind {
  switch (kind) {
    case "function":
      return monaco.languages.CompletionItemKind.Function;
    case "method":
      return monaco.languages.CompletionItemKind.Method;
    case "class":
      return monaco.languages.CompletionItemKind.Class;
    default:
      return monaco.languages.CompletionItemKind.Function;
  }
}

function toMonacoItems(
  items: GraphCompletionItem[],
  range: Monaco.IRange,
  monaco: typeof Monaco,
): Monaco.languages.CompletionItem[] {
  return items.map((item) => ({
    label: item.label,
    kind: mapKind(item.kind, monaco),
    detail: item.detail,
    documentation: {
      value: item.documentation,
      isTrusted: true,
    },
    insertText: item.insert_text,
    ...(item.insert_text.includes("${")
      ? { insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet }
      : {}),
    sortText: item.sort_key,
    range,
  }));
}

// --- Public API ---

export async function provideCompletionItems(
  model: Monaco.editor.ITextModel,
  position: Monaco.Position,
  _context: Monaco.languages.CompletionContext,
  _token: Monaco.CancellationToken,
  monaco: typeof Monaco,
): Promise<Monaco.languages.CompletionList> {
  const ctx = detectContext(model, position);
  if (!ctx) {
    return { suggestions: [] };
  }

  // Build suggestion context for graph autocomplete mode
  const suggestionContext = buildSuggestionContext(ctx, model, position);

  // Check cache first
  const cached = getCached(ctx.cacheKey);
  if (cached) {
    broadcastToGraph(cached, suggestionContext);
    const word = model.getWordUntilPosition(position);
    const range: Monaco.IRange = {
      startLineNumber: position.lineNumber,
      startColumn: word.startColumn,
      endLineNumber: position.lineNumber,
      endColumn: word.endColumn,
    };
    return { suggestions: toMonacoItems(cached, range, monaco) };
  }

  // Cancel any in-flight request
  if (currentAbort) {
    currentAbort.abort();
  }
  currentAbort = new AbortController();

  try {
    const items = await fetchCompletions(ctx.trigger, ctx.params, currentAbort.signal);
    setCache(ctx.cacheKey, items);
    broadcastToGraph(items, suggestionContext);

    const word = model.getWordUntilPosition(position);
    const range: Monaco.IRange = {
      startLineNumber: position.lineNumber,
      startColumn: word.startColumn,
      endLineNumber: position.lineNumber,
      endColumn: word.endColumn,
    };
    return { suggestions: toMonacoItems(items, range, monaco) };
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      return { suggestions: [] };
    }
    console.warn("Graph completion failed:", err);
    return { suggestions: [] };
  } finally {
    currentAbort = null;
  }
}

// --- Graph autocomplete broadcast ---

function buildSuggestionContext(
  ctx: DetectedContext,
  model: Monaco.editor.ITextModel,
  position: Monaco.Position,
): { variableName: string; trigger: string } | null {
  // Extract the variable name from context for insertion later
  let variableName = "";
  if (ctx.trigger === "variable_consumer") {
    variableName = (ctx.params["variable_name"] as string) ?? "";
  } else if (ctx.trigger === "general") {
    variableName = (ctx.params["query"] as string) ?? "";
  } else if (ctx.trigger === "member_access") {
    variableName = (ctx.params["object_name"] as string) ?? "";
  }
  // Also try to detect the variable on the current line (e.g. `x = ` or bare `my_var`)
  if (!variableName) {
    const lineContent = model.getLineContent(position.lineNumber);
    const assignMatch = lineContent.match(/(\w+)\s*=\s*$/);
    if (assignMatch) {
      variableName = assignMatch[1]!;
    }
  }
  return { variableName, trigger: ctx.trigger };
}

function broadcastToGraph(
  items: GraphCompletionItem[],
  context: { variableName: string; trigger: string } | null,
): void {
  const store = useEditorStore.getState();
  if (store.graphAutoComplete) {
    store.setPendingSuggestions(items, context);
  }
}

/**
 * Build a call expression for inserting a suggestion node into the editor.
 * Given a suggestion item and a variable name, produces code like:
 *   `result = authenticate(user_email, password)`
 */
export function buildCallInsertion(
  item: GraphCompletionItem,
  variableName: string,
): string {
  // Parse the insert_text snippet to get the function name and param names
  // insert_text looks like: "authenticate(${1:email}, ${2:password})"
  const fnMatch = item.insert_text.match(/^(\w+)\((.*)\)$/s);
  if (!fnMatch) {
    // Not a function call snippet — just return the label
    return item.insert_text.replace(/\$\{\d+:([^}]+)\}/g, "$1");
  }

  const fnName = fnMatch[1]!;
  const snippetBody = fnMatch[2]!;

  // Extract param names from snippet placeholders
  const paramNames: string[] = [];
  const placeholderRe = /\$\{(\d+):([^}]+)\}/g;
  let match: RegExpExecArray | null;
  while ((match = placeholderRe.exec(snippetBody)) !== null) {
    paramNames.push(match[2]!);
  }

  // Try to slot the variable into a matching param position
  const args = paramNames.map((p) => {
    if (variableName && p.toLowerCase() === variableName.toLowerCase()) {
      return variableName;
    }
    return p;
  });

  // If no param matched by name but we have a variable, use it as the first arg
  if (variableName && !args.includes(variableName) && args.length > 0) {
    args[0] = variableName;
  }

  const callExpr = `${fnName}(${args.join(", ")})`;

  // Add a return variable assignment
  const returnName = item.label.includes("_")
    ? `${item.label}_result`
    : "result";

  return `${returnName} = ${callExpr}`;
}
