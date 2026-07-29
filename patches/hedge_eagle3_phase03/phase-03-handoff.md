# Eagle3 HEDGE Phase 03 handoff

## Status

`FINAL_CANDIDATE_FROZEN`

Phase 03 executor has completed the pure-core import, reproducible SGLang
injection, Eagle3 adapter/control/runner integration, source freeze, clean
replay, and CPU-only regressions. It did not commit or push and did not enter
Phase 04.

No GPU command, model service, or keepalive pause/replacement was performed.
The last independently reviewed operational state remains worker `4099544`,
8×H20, keepalive owner `315671`, with 8×10 one-second samples at 100% per GPU.

## Provenance

- HEDGE source:
  `9fb903d676254ea5f5d171051fb15c54f331111c`
- DSpark pure-core publisher:
  `4d96f44065c07030ede67484a262006ec149626a`
- Eagle3 byte-identical pure-core import:
  `4cefd0a36ea254e4c14a83f35dc8db15b37a3384`
- SGLang fixed base:
  `fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1`
- SGLang final commit:
  `90c8558721de37ed0dc12802f29253ba52b873bc`
- DeepSpec Phase 03 integration commit:
  `d8ec6fcb9d90e57a9b5f8804c084a18b57bd60dd`
- four-file injected core aggregate:
  `53ce6f3a4bb8d2ac6cc6a531f565455e15a7021fc2cce0a446ef3c1e7352a815`
- complete 13-file candidate patch:
  `13fb7cedb5f87c8e912c77501139f7c9092b039294cd0213b0be340272d73945`
- uv lock:
  `b4c369d005163398e823c3a5eba939d913098a7242ddf16591c89857be7db946`

The 10 canonical pure-core files are byte-identical between the DSpark
publisher commit, the Eagle3 import commit, and this worktree. The four
runtime core files injected into SGLang are byte-identical to both canonical
commits.

## Implemented contract

- Fixed greedy Eagle3 top-k-one proposal width 3 and verify width 4.
- Explicit `disabled`, `b0`, and `enabled` modes.
- Disabled mode delegates native verification without allocating or mutating
  risk state.
- B0 uses `B=0,g=0,m=1`; positive mode uses `B=g>0,m=1`.
- Request budget survives blocks and follows pool-slot reorder, reuse, natural
  finish, cancellation, and abort without leaking across requests.
- Rank 0 alone owns a bounded device trace ring; TP ranks 1–7 use static
  capacity-zero early return.
- One proposal schema records aligned IDs/logits, regret/value, strict and
  HEDGE acceptance, commit length, first strict barrier, and budget state.
- `/set_internal_state` clears the Eagle3 trace and `/server_info` drains it;
  non-Eagle3/missing-hook calls fail closed.
- The client clears before every generation attempt, drains after success,
  retries trace operations without resending a successful generation, and
  binds rows to exact `response.id == choices[0].meta_info.id`.
- Formal timing begins at the first actual generation request and ends after
  the final request reaches terminal state, including final drain/retry time.
- Native/B0/B+ resolved configs have identical decode-affecting fields and
  differ only in HEDGE mode/config and the corresponding enable/B/g values.

## Verification

- Canonical pure core: 33/33 PASS.
- SGLang current source: aux 11/11 and HEDGE 21/21 PASS.
- SGLang clean fixed-base replay: `git apply --check`, `git diff --check`,
  aux 11/11, HEDGE 21/21, and regenerated patch hash all PASS.
- DeepSpec: Phase 03 15/15, Phase 01B tools 6/6, Phase 01C 3/3, Phase 02
  safety 14/14, plus pure core 33/33; 71/71 total PASS.
- Final 10-warmup + 500-formal mock runner fixture: 500/500 terminal success,
  five generation retries, maximum in-flight one, PASS.
- SGLang base-to-final `git diff --check`: PASS.
- DeepSpec staged code/docs check excluding
  `patches/hedge_eagle3_phase03/sglang-final-candidate.patch`: PASS. The full
  outer staged check emits exactly 20 expected mechanical warnings because
  blank context markers inside the immutable nested unified patch appear as
  `+ ` in the outer added-file diff. This is not a SGLang source whitespace
  defect; canonical patch SHA `13fb7ced…3945` remains unchanged.
- Phase 03 Python `py_compile`: PASS.
- Frozen-state correction: pending-to-frozen and same-SHA idempotence fixtures
  PASS; another SHA is rejected before writes. Replaying the complete
  finalizer with `90c8558721de37ed0dc12802f29253ba52b873bc` preserved the
  original finalization timestamp and every local authority hash.
- The main Agent independently replayed the same 13-file patch: patch hash,
  injected-core aggregate, uv-lock hash, apply/diff checks, and 11+21 tests
  all matched. The independent replay log hash differs only because test
  warnings contain a different temporary worktree path.

The Phase 02 backend-routing test now supplies its already reviewed Phase 02
`source_identity` fixture so Phase 03's legitimate file additions do not
trigger that orthogonal historical gate. The resolver, `assert_source_state`,
and independent source-drift negative tests are unchanged and still pass.

## Finalization result

SGLang final SHA `90c8558721de37ed0dc12802f29253ba52b873bc` is committed and clean. The identity finalizer verified the
13-file patch hash, file set, injected core aggregate, and uv lock, then updated
all local and HDFS authority fields. Phase 03 source is frozen and PASS; after
the main Agent's final review, the Phase 04 gate is open. The Phase 02 three-request
smoke remains bring-up evidence and is not a native baseline.
