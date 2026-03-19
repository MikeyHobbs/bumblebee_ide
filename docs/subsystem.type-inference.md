# Type Inference Strategy for Bumblebee IDE

> **Problem:** Bumblebee's graph-based suggestion engine (TICKET-911) matches functions by `type_hint` on Variable nodes and `params`/`return_type` on LogicNodes. Without type annotations in the target codebase, matching degrades to name-only — much weaker. Most real-world Python codebases are partially or fully untyped.

---

## Why This Matters

The compose suggestion pipeline has three tiers:

| Tier | Query | Quality |
|------|-------|---------|
| 1. Exact type match | `FIND_NODES_BY_PARAM_TYPE`, `FIND_NODES_BY_RETURN_TYPE` | Best — deterministic, precise |
| 2. Partial type match | Params JSON contains type substring | Good — may have false positives |
| 3. Name match (fallback) | `FIND_NODES_BY_PARAM_NAME` | Weak — `data` matches everything |

Without type annotations, **every variable falls to Tier 3**. The entire suggestion system becomes a name-grep.

---

## Tool Assessment

### Runtime Collection (Dynamic)

These tools run the target code and record observed types at each call site.

#### RightTyper (Recommended runtime tool)

- **How:** Instruments function calls, collects argument/return types with self-profiling to control overhead.
- **Overhead:** ~20% (vs MonkeyType's 37x on `black`).
- **Accuracy:** 76.8% TypeSim, 67.5% exact match, 89.8% coverage — best among runtime tools.
- **Output:** Annotations inserted directly into source or as stubs.
- **Tensor support:** Infers NumPy/PyTorch/JAX tensor shapes (jaxtyping-compatible).
- **Maturity:** Active development, newer than MonkeyType.
- **Limitation:** Requires running the code — needs a test suite or exercise script. Types reflect runtime paths only.

#### MonkeyType (Instagram/Meta)

- **How:** Logs all function calls to SQLite, generates annotations from recorded types.
- **Overhead:** Up to 270x slowdown, gigabytes of disk per second on large codebases.
- **Output:** Stub files or direct source annotation.
- **Limitation:** Generates overly concrete types (`List[str]` where `Sequence[str]` would be correct). Extreme resource usage makes it impractical for large repos.
- **Verdict:** Superseded by RightTyper for most use cases.

#### PyAnnotate (Dropbox)

- **How:** Runtime collection with sampling to reduce overhead.
- **Limitation:** Biased samples — records limited calls per function, inspects only first 4 elements of containers. Annotations may not reflect typical behavior.
- **Verdict:** Largely unmaintained. Not recommended for new projects.

### Static Inference (No execution required)

#### Pytype (Google) — SUNSETTING

- **How:** Static analysis with flow-based type inference. Generates `.pyi` stub files, then `merge-pyi` inserts annotations into source.
- **Strength:** No test suite needed. Infers types from code flow.
- **Critical issue:** Google announced Python 3.12 will be the last supported version. Not a viable long-term investment.
- **Verdict:** Avoid for new adoption.

#### Pyright (Microsoft)

- **How:** Full static type checker with sophisticated inference (call-site return type inference, control flow narrowing).
- **Strength:** Best-in-class static inference. Already the standard in VS Code / Pylance.
- **Limitation:** No built-in "export inferred types to source" feature. Pyright infers types internally for checking but doesn't write annotations back. Would need custom LSP client to extract inferred types.
- **Verdict:** Excellent for checking, not directly useful for annotation generation without tooling work.

### LLM-Assisted

#### Custom (Bumblebee-native)

- **How:** Feed function source + call context (from graph edges) to LLM, ask it to infer types.
- **Strength:** Can use graph context (callers, callees, variable flows) that no other tool has access to. The graph already knows who calls what with what values.
- **Limitation:** Non-deterministic, requires validation pass (mypy/pyright).
- **Verdict:** Most aligned with Bumblebee's architecture. Could be a Phase 2 feature.

---

## Recommendation: Layered Approach

### Layer 1: Static — Pyright pre-check (import time)

Run `pyright --outputjson` on the target repo during import. Parse the output to extract inferred types for parameters and return values where Pyright has high confidence. Store these as `inferred_type_hint` on Variable/LogicNode — separate from explicit `type_hint` so we know the provenance.

- **Cost:** Zero runtime overhead, fast, no test suite needed.
- **Coverage:** Moderate — Pyright can infer many return types and some parameter types from usage.
- **Integration point:** `import_pipeline.py` post-processing step.

### Layer 2: Runtime — RightTyper (opt-in, pre-import)

For repos with a test suite, offer a "deep typing" mode:

```
bumblebee import /path/to/repo --infer-types
```

This runs `righttyper` against the repo's test suite, applies annotations to a temp copy, then imports the annotated version. The user's original source is untouched.

- **Cost:** Requires test suite. Adds import time proportional to test runtime.
- **Coverage:** High for code paths exercised by tests.
- **Integration point:** CLI/UI option before `import_pipeline.py`.

### Layer 3: LLM — Graph-context inference (future)

Use the graph itself to infer types. When a Variable has no `type_hint`:

1. Follow CALLS edges to see what functions consume it — check their param types.
2. Follow RETURNS edges to see what functions produce it — check their return types.
3. Follow ASSIGNS/READS edges for data-flow propagation.
4. If ambiguous, ask the LLM with a Logic Pack containing the variable's neighborhood.

- **Cost:** Graph queries + optional LLM call.
- **Coverage:** Can fill gaps that static/runtime tools miss by leveraging cross-function context.
- **Integration point:** `suggestion_service.py` or a new `type_inference_service.py`.

---

## Implementation Priority

| Phase | Layer | Effort | Impact |
|-------|-------|--------|--------|
| Now | Harvest explicit annotations (already done) | Zero | Baseline |
| Next | Pyright static inference at import | Medium | Fills ~30-50% of missing types |
| Later | RightTyper opt-in for test-equipped repos | Medium | Fills ~60-80% of exercised paths |
| Future | LLM graph-context inference | High | Fills remaining gaps, highest quality |

---

## Integration with Existing Pipeline

```
Target repo
    │
    ▼
[tree-sitter parse] ← extracts explicit type_hint (current)
    │
    ▼
[pyright inference] ← adds inferred_type_hint where missing (Layer 1)
    │
    ▼
[import_pipeline]   ← stores both on Variable/LogicNode
    │
    ▼
[suggestion_service] ← uses type_hint || inferred_type_hint for matching
```

The key principle: **never overwrite explicit annotations**. Inferred types supplement, they don't replace. Store provenance (`explicit` vs `pyright_inferred` vs `runtime_inferred` vs `llm_inferred`) so the user and the system know confidence levels.

---

## References

- [RightTyper](https://github.com/RightTyper/RightTyper) — fast runtime type annotation
- [MonkeyType](https://github.com/Instagram/MonkeyType) — Meta's runtime type collection (high overhead)
- [Pyright type inference docs](https://github.com/microsoft/pyright/blob/main/docs/type-inference.md) — Microsoft's static inference
- [Pytype](https://google.github.io/pytype/) — Google's static analyzer (sunsetting after Python 3.12)
- [RightTyper paper](https://arxiv.org/html/2507.16051v1) — accuracy/performance benchmarks
