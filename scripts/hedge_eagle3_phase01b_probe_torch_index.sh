#!/usr/bin/env bash
# Read-only bounded connectivity probe for the pinned PyTorch CUDA 13 index.

set -euo pipefail

curl \
  --fail \
  --location \
  --max-time 30 \
  --silent \
  --show-error \
  --output /dev/null \
  --write-out 'http_code=%{http_code} remote_ip=%{remote_ip} bytes=%{size_download} seconds=%{time_total}\n' \
  https://download.pytorch.org/whl/cu130/torch/
