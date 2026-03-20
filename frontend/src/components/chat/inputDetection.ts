export const CYPHER_KEYWORDS = /^\s*(MATCH|RETURN|CREATE|MERGE|DELETE|DETACH|SET|REMOVE|WITH|UNWIND|CALL|OPTIONAL)\b/i;
export const VFS_CYPHER_PREFIX = /^\s*vfs\s+/i;
export const VFS_NL_PREFIX = /^\s*vfs\s*\?\s*/i;
export const NL_PREFIX = /^\s*(\?|ask\s)/i;
export const CLI_COMMANDS = /^\s*(ls|cd|pwd|cat|tree|find|info|help)\b/i;

export function inputMode(text: string): "cypher" | "cypher_vfs" | "nl" | "nl_vfs" | "cli" {
  const t = text.trim();
  if (VFS_NL_PREFIX.test(t)) return "nl_vfs";
  if (VFS_CYPHER_PREFIX.test(t)) return "cypher_vfs";
  if (CYPHER_KEYWORDS.test(t)) return "cypher";
  if (NL_PREFIX.test(t)) return "nl";
  if (CLI_COMMANDS.test(t)) return "cli";
  // Default: if it looks like a path or short word, treat as cli; otherwise nl
  return "cli";
}

export function stripNlPrefix(text: string): string {
  return text.trim().replace(/^\?\s*/, "").replace(/^ask\s+/i, "");
}
