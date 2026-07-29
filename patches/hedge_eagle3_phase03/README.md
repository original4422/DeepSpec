# Eagle3 HEDGE Phase 03 final-source candidate

This directory freezes the complete SGLang candidate relative to
`fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1`. It contains the previously
accepted DeepSeek-V4/Eagle3 native adaptation, the byte-identical injected
pure HEDGE core, the Eagle3-specific adapter and control-plane wiring, and
their source tests.

Provenance is deliberately split:

- HEDGE source: `9fb903d676254ea5f5d171051fb15c54f331111c`
- DSpark published pure core:
  `4d96f44065c07030ede67484a262006ec149626a`
- Eagle3 byte-identical import:
  `4cefd0a36ea254e4c14a83f35dc8db15b37a3384`
- SGLang fixed base:
  `fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1`
- injected four-file aggregate:
  `53ce6f3a4bb8d2ac6cc6a531f565455e15a7021fc2cce0a446ef3c1e7352a815`
- complete candidate patch:
  `13fb7cedb5f87c8e912c77501139f7c9092b039294cd0213b0be340272d73945`
- SGLang final commit:
  `90c8558721de37ed0dc12802f29253ba52b873bc`

`manifest.json` records every changed file, the uv lock identity, and the
clean-base replay evidence. The committed SGLang tree was verified against
all recorded identities; the final SHA above and manifest status are frozen.

Identity finalizer invocation used for this commit:

```bash
/home/tiger/venvs/deepspec-hedge-v4-eagle3/bin/python \
  scripts/hedge_eagle3_phase03_finalize_identity.py \
  --sglang-final-sha 90c8558721de37ed0dc12802f29253ba52b873bc
```

DeepSpec whitespace-check scope:

- `git diff --cached --check -- . ':(exclude)patches/hedge_eagle3_phase03/sglang-final-candidate.patch'`
  passes.
- The full outer DeepSpec staged check reports exactly 20 mechanical
  trailing-whitespace warnings from this immutable nested unified patch. Its
  blank context-marker lines are one space in canonical patch syntax, which
  the outer added-file diff displays as `+ `.
- The SGLang source diff from fixed base to final commit passes
  `git diff --check`; these warnings are not SGLang source whitespace defects.
  The canonical patch bytes and SHA must not be normalized.

Replay:

```bash
git -C /path/to/clean-sglang checkout \
  fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1
git -C /path/to/clean-sglang apply --check \
  /path/to/DeepSpec-hedge-v4-eagle3/patches/hedge_eagle3_phase03/sglang-final-candidate.patch
git -C /path/to/clean-sglang apply \
  /path/to/DeepSpec-hedge-v4-eagle3/patches/hedge_eagle3_phase03/sglang-final-candidate.patch
PYTHONPATH=/path/to/clean-sglang/python \
  /home/tiger/venvs/deepspec-hedge-v4-eagle3/bin/python \
  /path/to/clean-sglang/test/registered/unit/models/test_deepseek_v4_eagle3_aux.py -v
PYTHONPATH=/path/to/clean-sglang/python \
  /home/tiger/venvs/deepspec-hedge-v4-eagle3/bin/python \
  /path/to/clean-sglang/test/registered/unit/speculative/test_eagle3_hedge.py -v
```
