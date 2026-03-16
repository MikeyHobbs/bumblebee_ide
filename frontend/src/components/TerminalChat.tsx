import { useState, useRef, useEffect, useCallback } from "react";
import { Send } from "lucide-react";

interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system" | "tool_call" | "tool_result";
  content: string;
  timestamp: number;
}

function TerminalChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const sendMessage = useCallback(
    async (text: string) => {
      if (!text.trim() || isStreaming) return;

      const userMsg: ChatMessage = {
        id: `user-${Date.now()}`,
        role: "user",
        content: text.trim(),
        timestamp: Date.now(),
      };

      setMessages((prev) => [...prev, userMsg]);
      setInput("");
      setIsStreaming(true);

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const res = await fetch("/api/v1/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            messages: [{ role: "user", content: text.trim() }],
          }),
          signal: controller.signal,
        });

        if (!res.ok) {
          const errText = await res.text().catch(() => "Unknown error");
          setMessages((prev) => [
            ...prev,
            {
              id: `error-${Date.now()}`,
              role: "system",
              content: `Error: ${errText}`,
              timestamp: Date.now(),
            },
          ]);
          setIsStreaming(false);
          return;
        }

        const reader = res.body?.getReader();
        if (!reader) {
          setIsStreaming(false);
          return;
        }

        const decoder = new TextDecoder();
        let assistantContent = "";
        const assistantId = `assistant-${Date.now()}`;

        setMessages((prev) => [
          ...prev,
          {
            id: assistantId,
            role: "assistant",
            content: "",
            timestamp: Date.now(),
          },
        ]);

        let done = false;
        while (!done) {
          const result = await reader.read();
          done = result.done;
          if (result.value) {
            const chunk = decoder.decode(result.value, { stream: true });
            const lines = chunk.split("\n");
            for (const line of lines) {
              if (line.startsWith("data: ")) {
                const data = line.slice(6);
                if (data === "[DONE]") {
                  done = true;
                  break;
                }
                try {
                  const parsed: unknown = JSON.parse(data);
                  if (
                    parsed !== null &&
                    typeof parsed === "object" &&
                    "type" in parsed
                  ) {
                    const typedParsed = parsed as Record<string, unknown>;
                    const eventType = typedParsed["type"];
                    const eventContent =
                      typeof typedParsed["content"] === "string"
                        ? typedParsed["content"]
                        : "";

                    if (eventType === "content") {
                      assistantContent += eventContent;
                      setMessages((prev) =>
                        prev.map((m) =>
                          m.id === assistantId
                            ? { ...m, content: assistantContent }
                            : m,
                        ),
                      );
                    } else if (eventType === "tool_call") {
                      const toolName =
                        typeof typedParsed["name"] === "string"
                          ? typedParsed["name"]
                          : "unknown";
                      setMessages((prev) => [
                        ...prev,
                        {
                          id: `tool-call-${Date.now()}`,
                          role: "tool_call",
                          content: `${toolName}: ${eventContent}`,
                          timestamp: Date.now(),
                        },
                      ]);
                    } else if (eventType === "tool_result") {
                      setMessages((prev) => [
                        ...prev,
                        {
                          id: `tool-result-${Date.now()}`,
                          role: "tool_result",
                          content: eventContent,
                          timestamp: Date.now(),
                        },
                      ]);
                    }
                  }
                } catch {
                  // Skip unparseable SSE lines
                }
              }
            }
          }
        }
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") {
          // User cancelled
        } else {
          setMessages((prev) => [
            ...prev,
            {
              id: `error-${Date.now()}`,
              role: "system",
              content:
                err instanceof Error ? err.message : "Connection failed",
              timestamp: Date.now(),
            },
          ]);
        }
      } finally {
        setIsStreaming(false);
        abortRef.current = null;
      }
    },
    [isStreaming],
  );

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      void sendMessage(input);
    },
    [input, sendMessage],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        void sendMessage(input);
      }
    },
    [input, sendMessage],
  );

  const getRoleStyle = (role: ChatMessage["role"]): { color: string; prefix: string } => {
    switch (role) {
      case "user":
        return { color: "var(--prompt)", prefix: "> " };
      case "assistant":
        return { color: "var(--text-primary)", prefix: "" };
      case "system":
        return { color: "var(--system)", prefix: "[system] " };
      case "tool_call":
        return { color: "var(--tool-call)", prefix: "[tool] " };
      case "tool_result":
        return { color: "var(--tool-result)", prefix: "[result] " };
    }
  };

  return (
    <div
      className="flex flex-col h-full"
      style={{ background: "var(--bg-secondary)" }}
    >
      <div
        className="h-8 flex items-center px-3 text-xs font-semibold border-b flex-shrink-0"
        style={{
          color: "var(--text-secondary)",
          borderColor: "var(--border)",
        }}
      >
        Terminal
      </div>

      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto p-3 space-y-2"
      >
        {messages.length === 0 && (
          <div
            className="text-xs"
            style={{ color: "var(--text-muted)" }}
          >
            Ask questions about the codebase...
          </div>
        )}
        {messages.map((msg) => {
          const style = getRoleStyle(msg.role);
          return (
            <div
              key={msg.id}
              className="text-xs font-mono whitespace-pre-wrap break-words"
              style={{ color: style.color }}
            >
              <span style={{ opacity: 0.7 }}>{style.prefix}</span>
              {msg.content}
              {msg.role === "assistant" && isStreaming && msg.content === "" && (
                <span
                  className="inline-block w-2 h-3 ml-0.5"
                  style={{
                    background: "var(--prompt)",
                    animation: "pulse 1s ease-in-out infinite",
                  }}
                />
              )}
            </div>
          );
        })}
      </div>

      <form
        onSubmit={handleSubmit}
        className="flex items-center border-t px-3 py-2 gap-2 flex-shrink-0"
        style={{ borderColor: "var(--border)" }}
      >
        <span className="text-xs" style={{ color: "var(--prompt)" }}>
          &gt;
        </span>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={isStreaming ? "Streaming..." : "Type a message"}
          disabled={isStreaming}
          className="flex-1 text-xs font-mono outline-none bg-transparent"
          style={{ color: "var(--text-primary)" }}
        />
        <button
          type="submit"
          disabled={isStreaming || !input.trim()}
          style={{
            background: "none",
            border: "none",
            cursor:
              isStreaming || !input.trim() ? "not-allowed" : "pointer",
            color:
              isStreaming || !input.trim()
                ? "var(--text-muted)"
                : "var(--prompt)",
          }}
        >
          <Send size={14} />
        </button>
      </form>
    </div>
  );
}

export default TerminalChat;
