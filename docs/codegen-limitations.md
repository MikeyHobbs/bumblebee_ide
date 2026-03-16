# Code Generation Limitations

This document describes the known limitations of the Graph-to-Python code generator
(`backend/app/services/code_generator.py`).

## Comments are lost

Tree-sitter does not preserve comments in named AST nodes by default. When the
AST parser extracts structural and statement nodes, comments are not captured as
separate nodes. As a result, any comments in the original source code (line
comments, inline comments, block comments) will not appear in the generated
output.

**Impact:** All `# comment` lines and inline comments are dropped during
round-trip generation.

**Workaround:** For unmodified functions, the generator returns the original
`source_text` property directly, which includes comments. Comments are only
lost when a function's statements have been edited at the graph level.

## Blank lines between statements may differ

The statement extractor records individual statements with their `seq` ordering
but does not track blank lines between statements. The generator emits
statements sequentially without preserving the original blank line spacing.

**Impact:** Functions that had blank lines separating logical groups of
statements will have those blank lines removed or altered.

## Formatting may differ from original

Indentation is reconstructed based on nesting depth (4 spaces per level) rather
than being preserved byte-for-byte from the original source. While the
structural indentation is correct, minor formatting differences may occur:

- Original tabs are converted to spaces
- Trailing whitespace is stripped
- Alignment of multi-line expressions may differ
- Line continuations (backslash) may be reformatted

## Decorator order is preserved but formatting may vary

Decorators are preserved in their original order. However, the exact formatting
of decorator arguments may differ slightly from the original source. For
example, spacing within decorator argument lists may be normalized.

## Import statements

Module-level import statements are preserved only if they were captured by the
statement extractor at the module scope. Since the current statement extractor
focuses on function bodies, top-level imports may need to be handled separately
in future versions.

## String quote style

The generator preserves string content from `source_text` properties, so quote
styles (single vs double, triple-quoted) are maintained for unmodified
statements. However, reconstructed code uses whatever was in the original
`source_text` of each statement node.

## match/case statements (Python 3.10+)

Structural pattern matching (`match`/`case`) is handled by tree-sitter as a
control flow structure. The generator preserves these blocks through the
`source_text` of the ControlFlow node, but statement-level editing within
`case` branches may have limited support since the branch extraction for
`match`/`case` is still evolving.
