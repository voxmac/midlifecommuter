#!/usr/bin/env bash
# Start a job on Kaggle (free T4). usage: kaggle_push.sh ID SPEC.json  -> exit 0 = running (state/pending/ID), 1 = not started
e=$1; f=$2; U=$KAGGLE_USERNAME
if ! command -v kaggle >/dev/null; then pip install -q kaggle six >/dev/null; fi
if [ ! -f ~/.kaggle/kaggle.json ] && [ ! -f ~/.kaggle/access_token ]; then
  mkdir -p ~/.kaggle
  if echo "$KAGGLE_KEY" | grep -Eq '^[0-9a-f]{32}$'; then printf '{"username":"%s","key":"%s"}' "$U" "$KAGGLE_KEY" > ~/.kaggle/kaggle.json
  else printf '%s' "$KAGGLE_KEY" > ~/.kaggle/access_token; export KAGGLE_API_TOKEN=$KAGGLE_KEY; fi
  chmod 600 ~/.kaggle/*
fi
kaggle datasets list --mine > /dev/null || { echo "::warning::Kaggle auth failed"; exit 1; }
# assets dataset (characters, songs, fonts): new version only when the files changed
if [ ! -f /tmp/assets_synced ]; then
  echo "{\"title\": \"midlife-assets\", \"id\": \"$U/midlife-assets\", \"licenses\": [{\"name\": \"other\"}]}" > assets/dataset-metadata.json
  H=$(cd assets && ls | grep -v dataset-metadata | xargs sha1sum | sha1sum | cut -c1-12)
  if kaggle datasets status $U/midlife-assets >/dev/null 2>&1; then
    [ "$H" = "$(cat state/assets_hash 2>/dev/null)" ] || kaggle datasets version -p assets -m "sync $H" -q --dir-mode zip
  else kaggle datasets create -p assets -q --dir-mode zip; fi
  rm -f assets/dataset-metadata.json; mkdir -p state && echo "$H" > state/assets_hash
  for i in $(seq 1 40); do st=$(kaggle datasets status $U/midlife-assets 2>/dev/null | tr 'A-Z' 'a-z'); echo "assets: $st"; case "$st" in *ready*) break;; esac; sleep 30; done
  touch /tmp/assets_synced
fi
d=$(KERNEL_PREFIX=midlife KERNEL_DATASET=midlife-assets python tools/build_kernel.py $f $U) || exit 1
out=$(kaggle kernels push -p "$d" --accelerator NvidiaTeslaT4 2>&1); echo "$out"
echo "$out" | grep -qi "successfully pushed" || { echo "::warning::Kaggle did not take $e (quota or busy) -> Modal"; exit 1; }
mkdir -p state/pending && date -u +%FT%TZ > state/pending/$e
