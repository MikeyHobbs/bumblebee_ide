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

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

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
            break;
          case "node:pulse": {
            const nodeId =
              typeof wsEvent.payload["node_id"] === "string"
                ? wsEvent.payload["node_id"]
                : null;
            if (nodeId !== null) {
              options?.onNodePulse?.(nodeId);
            }
            break;
          }
          case "index:progress": {
            const progress =
              typeof wsEvent.payload["progress"] === "number"
                ? wsEvent.payload["progress"]
                : 0;
            const status =
              typeof wsEvent.payload["status"] === "string"
                ? wsEvent.payload["status"]
                : "";
            options?.onIndexProgress?.(progress, status);
            break;
          }
        }
      } catch {
        // Ignore parse errors
      }
    };

    ws.onclose = () => {
      // Reconnect after delay
      reconnectTimer.current = setTimeout(() => {
        connect();
      }, 3000);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [queryClient, options]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimer.current) {
        clearTimeout(reconnectTimer.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [connect]);
}
