# Project memory (RAG) — what to deposit and what to withhold

This project uses a companion RAG memory. These notes are about **what is safe to put in it**,
and how to retrieve reliably. They are deliberately written without naming anything private.

## 1. Do not deposit identifying information

The live instance is a family home and this repository is public. Design notes, review artifacts
and incident records are all worth keeping — **but the same anonymisation that applies to repo
exports applies to anything deposited into project memory**, because:

- recalled chunks are quoted back into future sessions and can be copied into a commit;
- review workflows ingest their own output automatically, so an artifact containing a real name
  propagates without anyone deciding to publish it;
- RAG has no retraction: a chunk can be *refuted*, but the text stays.

Before depositing: apply the same word/token-anchored substitution used for exports, run the
canary check, and grep for zero hits. Never deposit the substitution map itself.

## 2. Reviews ingest themselves — write prompts accordingly

Architectural-review artifacts land in project memory automatically. A delegation prompt is
therefore also a deposit. Keep real names out of prompts, and describe rooms by role
("the two children's bedrooms") rather than by name.

## 3. Ingestion is append-only

Re-ingesting an updated document does **not** replace the previous chunks — both sets coexist and
compete at retrieval. Two consequences:

- After re-ingesting a revised document, **refute the chunks it supersedes**, naming what changed.
  Otherwise the index holds two contradictory answers and ranking decides which one a future
  session believes.
- Prefer fewer, larger ingests to many small ones.

## 4. Stale design records outrank new ones surprisingly often

A superseded design note that calls itself "authoritative" will keep winning natural-language
queries against its replacement. When a design is revised:

1. ingest the new version;
2. **recall the obvious question** a future session would ask ("how does X work?") and look at
   what actually ranks first;
3. refute the stale chunks explicitly, listing the renames and the behaviour that changed.

Step 2 is the one that gets skipped. Ingesting is not the same as being findable.

## 5. Keep a status index

With many review rounds, the index fills with *findings* — most of them long since fixed. A
query phrased as a problem surfaces critique rather than current design, so a future session can
"discover" a bug that was closed weeks ago, or reason from deleted code.

Maintain a short, high-signal index of which findings are open and which are closed, ingest it,
and keep it current. See `docs/climate-finding-status.md`.

## 6. Verify before trusting a recalled fact

RAG freezes facts at write time. If a recalled note names an entity, a helper or a flag, check it
still exists before acting on it. Treat design/decision-class chunks as the design record; treat
everything else as a hypothesis.
