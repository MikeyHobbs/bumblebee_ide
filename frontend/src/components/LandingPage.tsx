import { useState, useEffect, useCallback } from "react";
import { useIndexRepository } from "@/api/client";

const RECENT_REPOS_KEY = "bumblebee:recent-repos";

function getRecentRepos(): string[] {
  try {
    const raw = localStorage.getItem(RECENT_REPOS_KEY);
    if (raw) {
      const parsed: unknown = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        return parsed.filter((v): v is string => typeof v === "string");
      }
    }
  } catch {
    // ignore parse errors
  }
  return [];
}

function saveRecentRepo(path: string): void {
  const recent = getRecentRepos().filter((r) => r !== path);
  recent.unshift(path);
  localStorage.setItem(
    RECENT_REPOS_KEY,
    JSON.stringify(recent.slice(0, 10)),
  );
}

interface LandingPageProps {
  onIndexed: () => void;
}

function LandingPage({ onIndexed }: LandingPageProps) {
  const [repoPath, setRepoPath] = useState("");
  const [recentRepos, setRecentRepos] = useState<string[]>([]);
  const indexMutation = useIndexRepository();

  useEffect(() => {
    setRecentRepos(getRecentRepos());
  }, []);

  const handleSubmit = useCallback(
    (path: string) => {
      if (!path.trim()) return;
      indexMutation.mutate(path.trim(), {
        onSuccess: () => {
          saveRecentRepo(path.trim());
          onIndexed();
        },
      });
    },
    [indexMutation, onIndexed],
  );

  const handleFormSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      handleSubmit(repoPath);
    },
    [repoPath, handleSubmit],
  );

  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--bg-primary)]">
      <div className="w-full max-w-md px-6">
        <h1
          className="text-2xl font-semibold text-center mb-1"
          style={{ color: "var(--text-primary)" }}
        >
          Bumblebee IDE
        </h1>
        <p
          className="text-sm text-center mb-8"
          style={{ color: "var(--text-secondary)" }}
        >
          Visual Logic Engine
        </p>

        <form onSubmit={handleFormSubmit} className="space-y-3">
          <input
            type="text"
            value={repoPath}
            onChange={(e) => setRepoPath(e.target.value)}
            placeholder="/path/to/repository"
            className="w-full px-3 py-2 text-sm font-mono border outline-none"
            style={{
              background: "var(--bg-secondary)",
              borderColor: "var(--border)",
              color: "var(--text-primary)",
            }}
            onFocus={(e) => {
              e.currentTarget.style.borderColor = "var(--border-focus)";
            }}
            onBlur={(e) => {
              e.currentTarget.style.borderColor = "var(--border)";
            }}
          />
          <button
            type="submit"
            disabled={indexMutation.isPending || !repoPath.trim()}
            className="w-full px-3 py-2 text-sm font-mono border"
            style={{
              background:
                indexMutation.isPending || !repoPath.trim()
                  ? "var(--bg-tertiary)"
                  : "var(--node-function)",
              borderColor: "var(--node-function)",
              color:
                indexMutation.isPending || !repoPath.trim()
                  ? "var(--text-muted)"
                  : "var(--bg-primary)",
              cursor:
                indexMutation.isPending || !repoPath.trim()
                  ? "not-allowed"
                  : "pointer",
            }}
          >
            {indexMutation.isPending ? "Indexing..." : "Index Repository"}
          </button>
        </form>

        {indexMutation.isError && (
          <p
            className="mt-3 text-sm"
            style={{ color: "var(--error)" }}
          >
            {indexMutation.error instanceof Error
              ? indexMutation.error.message
              : "Failed to index repository"}
          </p>
        )}

        {recentRepos.length > 0 && (
          <div className="mt-6">
            <p
              className="text-xs mb-2"
              style={{ color: "var(--text-secondary)" }}
            >
              Recent repositories
            </p>
            <div className="space-y-1">
              {recentRepos.map((repo) => (
                <button
                  key={repo}
                  onClick={() => {
                    setRepoPath(repo);
                    handleSubmit(repo);
                  }}
                  className="block w-full text-left px-2 py-1 text-sm font-mono border"
                  style={{
                    background: "var(--bg-secondary)",
                    borderColor: "var(--border)",
                    color: "var(--text-primary)",
                    cursor: "pointer",
                  }}
                >
                  {repo}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default LandingPage;
