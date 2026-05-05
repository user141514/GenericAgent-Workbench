# Test Matrix: Context Boundary Enforcement

> What tests exist, what tests will exist, and the migration test plan.
> Phase 1: architecture boundary tests only. Phase 2+: integration + E2E.

## Phase 1: Architecture Boundary Tests (Current)

| # | Test | File | What It Checks | Priority |
|---|------|------|----------------|----------|
| T1 | `test_no_direct_l1_read` | `tests/architecture/test_context_boundaries.py` | No module except `MemoryReader` reads `memory/global_mem_insight.txt` | **P0** |
| T2 | `test_no_direct_l2_read` | `tests/architecture/test_context_boundaries.py` | No module except `MemoryReader` reads `memory/global_mem.txt` | **P0** |
| T3 | `test_no_new_context_builders` | `tests/architecture/test_context_boundaries.py` | Only `ContextBuilder` assembles multi-source context packets | **P1** |
| T4 | `test_no_handrolled_openai_context` | `tests/architecture/test_context_boundaries.py` | `openai_agentmain.py` does not have new string-literal context blocks appended to `inputs` | **P1** |
| T5 | `test_no_assistant_as_fact` | `tests/architecture/test_context_boundaries.py` | `<summary>` extraction does not write directly to L1/L2 without cross-reference | **P1** |

## Phase 2: Integration Tests (Future)

| # | Test | What It Checks |
|---|------|----------------|
| I1 | `test_context_builder_output` | `ContextBuilder.build()` returns valid `ContextPacket` with correct block ordering |
| I2 | `test_reader_consistency` | `MemoryReader` returns same L1/L2 content as `read_legacy_l1_l2()` (parity check) |
| I3 | `test_context_size_budget` | `ContextPacket` stays within `max_tokens` budget |
| I4 | `test_dual_path_parity` | New pipeline produces context that matches old pipeline byte-for-byte |
| I5 | `test_memory_write_locking` | Concurrent `save_distilled_memory()` calls do not produce data loss |
| I6 | `test_context_marker_presence` | All injected context blocks have structural markers |

## Phase 3: Migration E2E Tests (Future)

| # | Test | What It Checks |
|---|------|----------------|
| E1 | `test_classic_path_migration` | Classic `agentmain.py` uses `ClassicContextAdapter` without behavior change |
| E2 | `test_openai_path_migration` | OpenAI path uses `OpenAIContextAdapter` without behavior change |
| E3 | `test_deprecated_path_warning` | Deprecated read paths emit warnings when called |
| E4 | `test_deprecated_path_no_new_callers` | No new callers added to deprecated paths after deprecation date |

## Test Environment

- **Framework:** `pytest`
- **Location:** `tests/architecture/` for architecture tests, `tests/integration/` for integration tests
- **CI Gate:** Architecture tests run on every PR. Integration tests run on merge to `main`.
- **Baseline:** Architecture tests are read-only — they assert code structure, not runtime behavior.

## Current Test Coverage

| Layer | Tests | Coverage |
|---|---|---|
| Architecture boundaries | 5 | Context read/write paths |
| Integration | 0 | — |
| E2E migration | 0 | — |
| Regression | 0 (existing test suite in `tests/`) | — |

---

*Matrix: 2026-05-05. Expand as phases progress.*
