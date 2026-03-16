import { useState, useCallback } from "react";
import LandingPage from "@/components/LandingPage";
import Layout from "@/components/Layout";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useGraphStore } from "@/store/graphStore";

function App() {
  const [indexed, setIndexed] = useState(false);
  const indexing = useGraphStore((s) => s.indexing);
  const setIndexing = useGraphStore((s) => s.setIndexing);
  const [progress, setProgress] = useState(0);
  const [progressStatus, setProgressStatus] = useState("");

  useWebSocket({
    onIndexProgress: (p, status) => {
      setProgress(p);
      setProgressStatus(status);
      if (p >= 1) {
        setIndexing(false);
      }
    },
  });

  const handleIndexed = useCallback(() => {
    setIndexed(true);
    setIndexing(true);
  }, [setIndexing]);

  if (!indexed) {
    return <LandingPage onIndexed={handleIndexed} />;
  }

  return (
    <div className="relative h-screen w-screen">
      {indexing && (
        <div
          className="absolute top-0 left-0 right-0 z-50 flex items-center gap-2 px-3 py-1 text-xs font-mono"
          style={{
            background: "var(--bg-tertiary)",
            color: "var(--text-secondary)",
            borderBottom: "1px solid var(--border)",
          }}
        >
          <div
            className="h-1 rounded"
            style={{
              width: `${Math.min(progress * 100, 100)}%`,
              background: "var(--node-function)",
              transition: "width 0.3s ease",
              minWidth: "2px",
            }}
          />
          <span className="whitespace-nowrap">
            {progressStatus
              ? progressStatus
              : "Indexing..."}
          </span>
        </div>
      )}
      <Layout />
    </div>
  );
}

export default App;
