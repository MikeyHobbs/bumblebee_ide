import type * as Monaco from "monaco-editor";

const models = new Map<string, Monaco.editor.ITextModel>();

function getLanguageFromPath(path: string): string {
  const ext = path.split(".").pop()?.toLowerCase();
  switch (ext) {
    case "ts":
    case "tsx":
      return "typescript";
    case "js":
    case "jsx":
      return "javascript";
    case "py":
      return "python";
    case "json":
      return "json";
    case "css":
      return "css";
    case "html":
      return "html";
    case "md":
      return "markdown";
    case "yaml":
    case "yml":
      return "yaml";
    case "toml":
      return "toml";
    case "rs":
      return "rust";
    case "go":
      return "go";
    case "java":
      return "java";
    default:
      return "plaintext";
  }
}

export function getOrCreateModel(
  monaco: typeof Monaco,
  path: string,
  content: string,
): Monaco.editor.ITextModel {
  const existing = models.get(path);
  if (existing && !existing.isDisposed()) {
    return existing;
  }

  const uri = monaco.Uri.parse(`file://${path}`);
  const existingByUri = monaco.editor.getModel(uri);
  if (existingByUri) {
    models.set(path, existingByUri);
    return existingByUri;
  }

  const language = getLanguageFromPath(path);
  const model = monaco.editor.createModel(content, language, uri);
  models.set(path, model);
  return model;
}

const nodeModels = new Map<string, Monaco.editor.ITextModel>();

export function getOrCreateNodeModel(
  monaco: typeof Monaco,
  nodeId: string,
  sourceText: string,
  modulePath: string,
): Monaco.editor.ITextModel {
  const existing = nodeModels.get(nodeId);
  if (existing && !existing.isDisposed()) {
    // Update content if it changed
    if (existing.getValue() !== sourceText) {
      existing.setValue(sourceText);
    }
    return existing;
  }

  const uri = monaco.Uri.parse(`bumblebee://node/${nodeId}`);
  const existingByUri = monaco.editor.getModel(uri);
  if (existingByUri) {
    nodeModels.set(nodeId, existingByUri);
    return existingByUri;
  }

  const language = getLanguageFromPath(modulePath);
  const model = monaco.editor.createModel(sourceText, language, uri);
  nodeModels.set(nodeId, model);
  return model;
}

export function disposeNodeModel(nodeId: string): void {
  const model = nodeModels.get(nodeId);
  if (model && !model.isDisposed()) {
    model.dispose();
  }
  nodeModels.delete(nodeId);
}

export function disposeModel(path: string): void {
  const model = models.get(path);
  if (model && !model.isDisposed()) {
    model.dispose();
  }
  models.delete(path);
}

export function disposeAllModels(): void {
  for (const [key, model] of models) {
    if (!model.isDisposed()) {
      model.dispose();
    }
    models.delete(key);
  }
}
