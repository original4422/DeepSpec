# Phase 02 DeepSeek-V4 + EAGLE3 runtime adapter

This directory is the canonical, small-file archive of the Phase 02
SGLang integration.  It is intentionally separate from the HDFS run
artifacts and does not make the DeepSpec commit a parent of the SGLang
base commit.

The patch applies to the fixed SGLang base
`fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1`.  It adds explicit EAGLE3
capability validation and the DeepSeek-V4 mHC auxiliary-state adapter.
The source-side test is archived separately because it was untracked in
the live SGLang worktree when the runtime patch was captured.

To reproduce from a clean SGLang checkout:

```bash
DEEPSPEC_ROOT=/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-v4-eagle3
SGLANG_ROOT=/home/tiger/src/sglang-hedge-v4-eagle3
REPLAY_ROOT="$(mktemp -d /tmp/deepspec-eagle3-phase02-replay.XXXXXX)"

git -C "${SGLANG_ROOT}" worktree add --detach \
  "${REPLAY_ROOT}" fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1
git -C "${REPLAY_ROOT}" apply --check \
  "${DEEPSPEC_ROOT}/patches/hedge_eagle3_phase02/sglang-eagle3-deepseek-v4.patch"
git -C "${REPLAY_ROOT}" apply \
  "${DEEPSPEC_ROOT}/patches/hedge_eagle3_phase02/sglang-eagle3-deepseek-v4.patch"
install -D -m 0644 \
  "${DEEPSPEC_ROOT}/patches/hedge_eagle3_phase02/test_deepseek_v4_eagle3_aux.py" \
  "${REPLAY_ROOT}/test/registered/unit/models/test_deepseek_v4_eagle3_aux.py"

CUDA_VISIBLE_DEVICES="" \
PYTHONPATH="${REPLAY_ROOT}/python" \
/home/tiger/venvs/deepspec-hedge-v4-eagle3/bin/python \
  "${REPLAY_ROOT}/test/registered/unit/models/test_deepseek_v4_eagle3_aux.py" -v

git -C "${SGLANG_ROOT}" worktree remove --force "${REPLAY_ROOT}"
```

Before applying, verify the byte counts and SHA-256 values in
`manifest.json`.  The live TP=8 smoke evidence is recorded under
`20260729T012234Z-phase-02-native-smoke-02`; replaying the unit test does
not replace that hardware evidence.
