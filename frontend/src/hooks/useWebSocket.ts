import { useEffect, useRef, useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";

type WebSocketEventType = "graph:updated" | "node:pulse" | "index:progress";

interface WebSocketEvent {
  type: WebSocketEventType;
  payload: Record<string, unknown>;
}

interface UseWebSocketOptions {
  onNodePulse?: (nodeId: string) => void;
  onIndexProgress?: (progress: number, status: string) => void;
}

export function useWebSocket(options?: UseWebSocketOptions) {
  const queryClient = useQueryClient();
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const optionsRef = useRef(options);
  const closedIntentionally = useRef(false);
  optionsRef.current = options;

  const connect = useCallback(() => {
    if (
      wsRef.current?.readyState === WebSocket.OPEN ||
      wsRef.current?.readyState === WebSocket.CONNECTING
    ) {
      return;
    }

    closedIntentionally.current = false;
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${protocol}//${window.location.host}/ws/graph`);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      try {
        const data: unknown = JSON.parse(String(event.data));
        if (
          data === null ||
          typeof data !== "object" ||
          !("type" in data) ||
          !("payload" in data)
        ) {
          return;
        }
        const wsEvent = data as WebSocketEvent;

        switch (wsEvent.type) {
          case "graph:updated":
            void queryClient.invalidateQueries({
              queryKey: ["graph-nodes"],
            });
            void queryClient.invalidateQueries({
              queryKey: ["logic-pack"],
            });
            void queryClient.invalidateQueries({
              queryKey: ["logic-nodes"],
            });
            void queryClient.invalidateQueries({
              queryKey: ["all-edges"],
            });
            break;
          case "node:pulse": {
            const nodeId =
              typeof wsEvent.payload["node_id"] === "string"
                ? wsEvent.payload["node_id"]
                : null;
            if (nodeId !== null) {
              optionsRef.current?.onNodePulse?.(nodeId);
            }
            break;
          }
          case "index:progress": {
            const done =
              typeof wsEvent.payload["done"] === "number"
                ? wsEvent.payload["done"]
                : 0;
            const total =
              typeof wsEvent.payload["total"] === "number"
                ? wsEvent.payload["total"]
                : 1;
            const file =
              typeof wsEvent.payload["file"] === "string"
                ? wsEvent.payload["file"]
                : "";
            const progress = total > 0 ? done / total : 0;
            const status = `${done}/${total} ${file}`;
            optionsRef.current?.onIndexProgress?.(progress, status);
            break;
          }
        }
      } catch {
        // Ignore parse errors
      }
    };

    ws.onclose = () => {
      wsRef.current = null;
      if (!closedIntentionally.current) {
        reconnectTimer.current = setTimeout(() => {
          connect();
        }, 3000);
      }
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [queryClient]);

  useEffect(() => {
    connect();
    return () => {
      closedIntentionally.current = true;
      if (reconnectTimer.current) {
        clearTimeout(reconnectTimer.current);
        reconnectTimer.current = null;
      }
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect]);
}
