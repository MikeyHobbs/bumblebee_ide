import { useState, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/api/client";
import {
  useCypherCompare,
  useRateEval,
  useEvalHistory,
  useEvalStats,
  type CompareResponse,
  type ModelResult,
} from "@/api/cypherEval";

function ModelResultPane({ label, result }: { label: string; result: ModelResult }) {
  return (
    <div className="flex-1 min-w-0 flex flex-col gap-2 p-3 rounded" style={{ background: "var(--bg-secondary, #111)" }}>
      <div className="text-xs font-semibold" style={{ color: "var(--text-muted, #888)" }}>
        {label}: {result.model}
      </div>
      <div className="text-xs" style={{ color: "var(--text-muted, #888)" }}>
        {result.row_count} rows &middot; {result.latency_ms.toFixed(0)}ms
        {result.error && <span className="text-red-400 ml-2">Error: {result.error}</span>}
      </div>
      <pre
        className="text-xs overflow-auto p-2 rounded whitespace-pre-wrap"
        style={{ background: "var(--bg-tertiary, #0a0a0a)", color: "var(--text-primary, #e0e0e0)", maxHeight: 120 }}
      >
        {result.cypher || "(no query generated)"}
      </pre>
      <div className="flex-1 min-h-0 overflow-auto" style={{ maxHeight: 200 }}>
        {result.results.length > 0 ? (
          <table className="w-full text-xs" style={{ color: "var(--text-primary, #e0e0e0)" }}>
            <thead>
              <tr>
                {Object.keys(result.results[0]!).map((col) => (
                  <th key={col} className="text-left px-1 py-0.5 border-b" style={{ borderColor: "#333" }}>
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {result.results.slice(0, 20).map((row, i) => (
                <tr key={i}>
                  {Object.values(row).map((val, j) => (
                    <td key={j} className="px-1 py-0.5 border-b" style={{ borderColor: "#222" }}>
                      {typeof val === "object" ? JSON.stringify(val) : String(val ?? "")}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="text-xs italic" style={{ color: "var(--text-muted, #666)" }}>No results</div>
        )}
      </div>
    </div>
  );
}

function StatsBar() {
  const { data: stats } = useEvalStats();
  if (!stats) return null;

  return (
    <div className="flex gap-4 text-xs" style={{ color: "var(--text-muted, #888)" }}>
      <span>Total: {stats.total}</span>
      <span>Rated: {stats.rated}</span>
      {Object.entries(stats.wins).map(([model, count]) => (
        <span key={model}>
          {model}: {count} wins
        </span>
      ))}
    </div>
  );
}

export default function CypherEvalPanel() {
  const [question, setQuestion] = useState("");
  const [modelA, setModelA] = useState("");
  const [modelB, setModelB] = useState("");
  const [comparison, setComparison] = useState<CompareResponse | null>(null);
  const [ratingNotes, setRatingNotes] = useState("");

  const { data: modelsData } = useQuery({
    queryKey: ["models"],
    queryFn: () => apiFetch<{ models: Array<{ name: string; description: string }> }>("/api/v1/models"),
  });

  const compareMutation = useCypherCompare();
  const rateMutation = useRateEval();
  const { data: history } = useEvalHistory(10);

  const models = modelsData?.models ?? [];

  // Auto-select first two models if not set
  if (models.length >= 2 && !modelA && !modelB) {
    const nonMock = models.filter((m) => m.name !== "mock");
    if (nonMock.length >= 2) {
      setModelA(nonMock[0]!.name);
      setModelB(nonMock[1]!.name);
    } else if (models.length >= 2) {
      setModelA(models[0]!.name);
      setModelB(models[1]!.name);
    }
  }

  const handleCompare = useCallback(() => {
    if (!question.trim() || !modelA || !modelB) return;
    compareMutation.mutate(
      { question: question.trim(), model_a: modelA, model_b: modelB },
      { onSuccess: (data) => setComparison(data) },
    );
  }, [question, modelA, modelB, compareMutation]);

  const handleRate = useCallback(
    (winner: string) => {
      if (!comparison) return;
      rateMutation.mutate(
        { eval_id: comparison.eval_id, winner, notes: ratingNotes },
        {
          onSuccess: () => {
            setRatingNotes("");
          },
        },
      );
    },
    [comparison, ratingNotes, rateMutation],
  );

  return (
    <div className="flex flex-col h-full p-4 gap-4 overflow-auto" style={{ background: "var(--bg-primary, #0a0a0a)" }}>
      {/* Header + stats */}
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-bold" style={{ color: "var(--text-primary, #e0e0e0)" }}>
          NL-to-Cypher Model Comparison
        </h2>
        <StatsBar />
      </div>

      {/* Question input */}
      <div className="flex gap-2">
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleCompare()}
          placeholder="Ask a natural language question about the codebase..."
          className="flex-1 px-3 py-1.5 rounded text-sm"
          style={{
            background: "var(--bg-secondary, #111)",
            color: "var(--text-primary, #e0e0e0)",
            border: "1px solid #333",
          }}
        />
        <button
          onClick={handleCompare}
          disabled={compareMutation.isPending || !question.trim() || !modelA || !modelB}
          className="px-4 py-1.5 rounded text-sm font-medium"
          style={{
            background: compareMutation.isPending ? "#333" : "var(--accent, #4ec990)",
            color: "#000",
            cursor: compareMutation.isPending ? "wait" : "pointer",
          }}
        >
          {compareMutation.isPending ? "Running..." : "Compare"}
        </button>
      </div>

      {/* Model selectors */}
      <div className="flex gap-4">
        <label className="flex items-center gap-2 text-xs" style={{ color: "var(--text-muted, #888)" }}>
          Model A:
          <select
            value={modelA}
            onChange={(e) => setModelA(e.target.value)}
            className="px-2 py-1 rounded text-xs"
            style={{ background: "var(--bg-secondary, #111)", color: "var(--text-primary, #e0e0e0)", border: "1px solid #333" }}
          >
            <option value="">Select...</option>
            {models.map((m) => (
              <option key={m.name} value={m.name}>
                {m.name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-xs" style={{ color: "var(--text-muted, #888)" }}>
          Model B:
          <select
            value={modelB}
            onChange={(e) => setModelB(e.target.value)}
            className="px-2 py-1 rounded text-xs"
            style={{ background: "var(--bg-secondary, #111)", color: "var(--text-primary, #e0e0e0)", border: "1px solid #333" }}
          >
            <option value="">Select...</option>
            {models.map((m) => (
              <option key={m.name} value={m.name}>
                {m.name}
              </option>
            ))}
          </select>
        </label>
      </div>

      {/* Side-by-side results */}
      {comparison && (
        <>
          <div className="flex gap-4">
            <ModelResultPane label="Model A" result={comparison.model_a} />
            <ModelResultPane label="Model B" result={comparison.model_b} />
          </div>

          {/* Rating controls */}
          <div className="flex items-center gap-3">
            <span className="text-xs" style={{ color: "var(--text-muted, #888)" }}>Rate:</span>
            {[
              { label: "A wins", value: "a" },
              { label: "B wins", value: "b" },
              { label: "Tie", value: "tie" },
              { label: "Both bad", value: "both_bad" },
            ].map((opt) => (
              <button
                key={opt.value}
                onClick={() => handleRate(opt.value)}
                disabled={rateMutation.isPending}
                className="px-3 py-1 rounded text-xs"
                style={{ background: "#222", color: "var(--text-primary, #e0e0e0)", border: "1px solid #444" }}
              >
                {opt.label}
              </button>
            ))}
            <input
              type="text"
              value={ratingNotes}
              onChange={(e) => setRatingNotes(e.target.value)}
              placeholder="Notes..."
              className="flex-1 px-2 py-1 rounded text-xs"
              style={{ background: "var(--bg-secondary, #111)", color: "var(--text-primary, #e0e0e0)", border: "1px solid #333" }}
            />
            {rateMutation.isSuccess && (
              <span className="text-xs text-green-400">Saved</span>
            )}
          </div>
        </>
      )}

      {/* Recent history */}
      {history && history.items.length > 0 && (
        <div className="mt-4">
          <h3 className="text-xs font-semibold mb-2" style={{ color: "var(--text-muted, #888)" }}>
            Recent Evaluations
          </h3>
          <div className="flex flex-col gap-1">
            {history.items.map((item) => (
              <div
                key={item.eval_id}
                className="flex items-center gap-3 px-2 py-1 rounded text-xs"
                style={{ background: "var(--bg-secondary, #111)", color: "var(--text-primary, #ccc)" }}
              >
                <span className="flex-1 truncate">{item.question}</span>
                <span style={{ color: "var(--text-muted, #666)" }}>
                  {item.model_a.model} vs {item.model_b.model}
                </span>
                <span style={{ color: item.rating ? "#4ec990" : "#666" }}>
                  {item.rating ? `Winner: ${item.rating.winner}` : "Unrated"}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
