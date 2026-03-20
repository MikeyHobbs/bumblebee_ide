# Metrics Reference

## Scoring Functions

### exact_match

The model's answer must be structurally identical to the gold answer.
- Dicts: same keys and values (order-independent)
- Lists: same elements (order-dependent unless specified)
- Scalars: equality check
- Strings: stripped and lowercased before comparison

### contains

The model's answer must contain all key-value pairs from the gold answer,
but may include additional fields. Useful when the exact output format may vary
but the critical information must be present.

### type_match

The model's answer must have the same structure as the gold answer:
- Same dict keys (values can differ)
- Same list length
- Same types for each field
- Useful for "does it return the right shape?" questions

### human_rated

A human reviews the answer and rates it on a scale:
- **correct** — fully answers the question
- **partial** — captures some but not all of the answer
- **incorrect** — wrong answer or didn't answer
- **error** — code failed to execute

## Composite Scores

### Task Score (per task)

```
task_score = correctness * 1.0
           + execution_success * 0.0  # prerequisite, not bonus
           + retrieval_precision * 0.0  # diagnostic only
```

Correctness is the only thing that matters for the headline number.
Other metrics explain *why* one method beats another.

### Efficiency Score (per task)

```
efficiency = correctness / max(steps, 1)
```

A method that gets the right answer in 1 step scores higher than one that
takes 5 steps. This captures the "graph context saves exploration time" story.

### Token Efficiency (per task)

```
token_efficiency = correctness / max(total_tokens / 1000, 0.1)
```

Correct answers with less token consumption score higher. Graph RAG should
produce compact, targeted context vs file RAG's bulk retrieval.

## Reporting

### Per-Category Breakdown

The primary results table groups tasks by category and shows:

| Category | N | Graph RAG Correct | File RAG Correct | No Retrieval Correct | p-value |
|----------|---|-------------------|------------------|---------------------|---------|
| direct | 10 | 9/10 | 8/10 | 6/10 | ... |
| composition | 10 | 8/10 | 4/10 | 1/10 | ... |
| ... | | | | | |

### Efficiency Charts

1. **Steps to answer** — grouped bar chart by category, 3 bars per group
2. **Tokens consumed** — same layout
3. **Correctness vs difficulty** — line chart showing divergence on harder tasks

### Statistical Tests

For each metric, report:
- Paired difference (Graph RAG - File RAG) with 95% CI
- p-value from appropriate test (McNemar for binary, Wilcoxon for continuous)
- Effect size (Cohen's d or odds ratio)
