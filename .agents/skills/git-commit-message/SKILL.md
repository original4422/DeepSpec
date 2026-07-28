---
name: git-commit-message
description: >-
  Draft Conventional Commit messages from staged changes only, with concise
  range-based sections and categorized bullet bodies. Use when the user asks
  for a commit message, git message, or message based on index/staged state.
---

# Git Commit Message

## Workflow

1. Run in parallel: `git status`, `git diff --cached`, `git log -5 --oneline`
2. **Only describe staged files** — ignore unstaged/untracked unless noting exclusions
3. Do **not** commit unless the user explicitly asks

## Title

```
<type>[(<scope>)][!]: <summary>
```

- Language: **English**
- Default types: `feat`, `fix`, `refactor`, `perf`, `docs`, `test`, `build`, `ci`, `chore`, `style`, `revert`
- Scope: optional; use a clear primary method or module, and omit it for cross-cutting changes
- Summary: one line, focus on **why / what delivered**, not file list
- Match recent repo style from `git log`

Choose one type by the primary intent:

1. Undo an existing change → `revert`
2. Add usable behavior, capability, or a public interface → `feat`
3. Correct faulty behavior or a vulnerability → `fix`
4. Preserve behavior while improving performance → `perf`
5. Preserve behavior while restructuring internals → `refactor`
6. Change only docs, tests, build/dependencies, CI, or formatting → `docs`, `test`, `build`, `ci`, or `style`
7. Perform other repository maintenance without changing product behavior → `chore`

Rules:

- Use one primary type; if staged changes contain independent primary intents, suggest splitting the commit
- Supporting tests, docs, or config do not change the primary type
- `style` means formatting, whitespace, semicolons, or import ordering — not UI/CSS changes
- Use `build` for build systems and dependency-only updates unless the primary intent is a feature or fix
- A repository may explicitly replace or extend the default type set in this file; define when each custom type applies
- Do not redefine the standard meaning of `feat`, `fix`, or breaking changes
- For an incompatible change, add `!` and append a `BREAKING CHANGE: ...` footer with impact or migration guidance

## Body

Use `-` bullet lists grouped by Section. A Section identifies **where the change lands**; its bullets explain **what changed and why it matters**.

### Repository-specific Section mappings

These explicit mappings are shared by contributors to this repository. A mapping may match either a path or a clear primary-role semantic signal.

| Section | Path or primary-role signal |
|---------|-----------------------------|
| `pipeline:` | `pipeline/*/generate.py`; generator implementations and CLI command definitions whose primary role is invoking them |
| `demo:` | `pipeline/*/demo.py`; files or changed blocks whose primary role is defining runnable demo cases |

Semantic signals must describe the primary role of a file or changed block. Do not use broad relations such as `related changes` or `CLI wiring`.

### Section selection

Classify each logical change with this precedence:

1. Explicit path mapping
2. Explicit primary-role semantic mapping
3. Built-in virtual Section
4. Adaptive path Section

For overlapping explicit paths, use the most specific path, then declaration order. For multiple semantic matches, use declaration order. To make a semantic rule override a path rule, add that path to the semantic rule.

Built-in virtual Sections:

- `tests`: test files, including colocated tests
- `docs`: README, CHANGELOG, and documentation files
- `deps`: dependency declarations and lockfile changes
- `build`: compilation, packaging, and release-build changes
- `ci`: CI/CD workflows
- `config`: configuration not covered by build or CI

For adaptive path Sections:

- Use one meaningful path-segment name that best compresses the affected range
- Preserve the path segment's original spelling, such as `edge_assets` or `payment-sdk`
- Ignore low-information containers such as `src`, `lib`, `app`, `apps`, `package`, `packages`, `module`, `modules`, `feature`, and `features`
- Adjust granularity to the staged change: use a specific area for focused changes and a meaningful common area for related broader changes
- If unrelated paths share a basename, use the nearest distinguishing single-segment ancestor; if that is still ambiguous, add an explicit mapping
- Do not invent path-like or compound names such as `apps/web` or `example-web`

Additional rules:

- One bullet = one logical change; merge trivial edits
- The same file may contribute to multiple Sections when it contains distinct logical changes
- Describe each logical change in exactly one Section
- Do not use `chore`, `repo`, or `misc` as catch-all Sections
- Do not impose a Section count limit or hide broad changes under a generic parent; suggest splitting when many Sections represent independent changes
- Order explicitly mapped Sections by declaration, adaptive Sections by name, then virtual Sections as `tests → docs → deps → build → ci → config`
- Omit empty Sections

## Template

```
<type>[(<scope>)][!]: <summary>

<section>:
- ...

[BREAKING CHANGE: <impact and migration guidance>]
```

## Output

Return the message in a fenced code block, ready to copy.

- If unstaged/untracked files exist, add a one-line note after the block listing what was excluded
- If staged changes contain many independent scopes or intents, add a one-line suggestion to split the commit

## Example

```
feat(irregular_grid): integrate edge assets and enrich QA generation

pipeline:
- Add --edge-assets CLI group and wire catalog through generate flow

demo:
- Add six edge-asset showcase cases covering pens, wood, and mixed modes

irregular_grid:
- Add EdgeAssetConfig, edge_assignment, and renderer compositing
- Enrich QA templates with context notes and rationale builders

tests:
- Add test_edge_assignment and extend renderer compositing tests
```
