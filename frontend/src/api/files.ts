import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "./client";

export function useFileContent(path: string | null) {
  return useQuery({
    queryKey: ["file-content", path],
    queryFn: () =>
      apiFetch<{ content: string; language: string }>(
        `/api/v1/file?path=${encodeURIComponent(path!)}`,
      ),
    enabled: path !== null,
  });
}
