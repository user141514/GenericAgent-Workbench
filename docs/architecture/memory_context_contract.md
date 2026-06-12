# Memory / Context Contract

This contract keeps the current hybrid memory design explicit without forcing
an early merge of the text memory system and the SQLite store.

## Ownership

- `core/context/memory_reader.py` owns all L1/L2 text reads.
  It reads `memory/global_mem_insight.txt` and `memory/global_mem.txt`, then
  exposes raw strings or `MemoryBlock` objects.
- `core/context/context_builder.py` is a pure representation builder.
  It consumes a prebuilt `MemoryBundle` and formats a `ContextPacket`; it must
  not read L1/L2 files, import `MemoryStore`, or query SQLite directly.
- `core/memory/store.py` owns SQLite CRUD, evidence chunks, candidates, and
  durable memory write gates. It is a storage engine, not a prompt formatter.
- Frontends may display memory, but L1/L2 display must go through
  `MemoryReader`. Frontends may still read `history_memory_inbox.md` directly
  because it is an operator inbox, not canonical prompt memory.

## Source Priority

- Text L1/L2 remains the canonical prompt input.
- SQLite structured memory is supplementary evidence.
- Session/task state is volatile runtime context.
- The reader chooses sources and priority; the builder only trims and renders.

## Migration Rule

Do not collapse the two memory systems until a migration maps text semantics,
manual editability, prompt formatting, and downstream interoperability. Until
then, new read paths should depend on `MemoryReader`, and new write paths should
depend on the existing `MemoryStore` / write-gate APIs.
