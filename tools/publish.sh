#!/usr/bin/env bash
# Publish a finished GPU job (Modal or Kaggle): GitHub Release + review issue.  usage: publish.sh ID OUTDIR "runner line"
e=$1; O=$2; RUN=$3
TAG="$e-$(date -u +%m%d-%H%M)"
note() { echo; echo "$RUN"; }
if [ -f $O/report.json ] && [ -f songs/$e.json ]; then
  # every version: lyrics all sung? male voice throughout? (CPU, this runner) - before anyone listens
  ( sudo apt-get -qq update >/dev/null && sudo apt-get -qq install -y ffmpeg >/dev/null
    pip install -q torch==2.5.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cpu
    pip install -q demucs faster-whisper librosa soundfile && python tools/song_check.py songs/$e.json $O ) || echo "song check failed"
  gh release create "$TAG" $O/*.mp3 $(ls $O/*.wav 2>/dev/null) $O/report.json $(ls $O/modal.json 2>/dev/null) --title "$e song versions" \
    --notes "Listen on your phone, then answer in the review issue."
  { python tools/song_body.py $O/report.json $REPO $TAG; note; } > body.md
  gh issue create --title "Review: $e" --body-file body.md
elif [ -f $O/report.json ] && [ -f episodes/$e.json ] && ls $O/keys/*.png >/dev/null 2>&1 && ! ls $O/*.mp4 >/dev/null 2>&1 && grep -q '"keys_only": true' episodes/$e.json; then
  # keys-only preview: every keyframe as a release asset, looked at before any Wan GPU time
  mkdir -p keysout && for k in $O/keys/S*.png; do cp "$k" "keysout/key_$(basename $k)"; done
  gh release create "$TAG" keysout/*.png $O/report.json --title "$e keyframes" --notes "Keyframe preview (no animation yet)."
  { echo "## $e keyframes (preview, no animation yet)"; echo "https://github.com/$REPO/releases/tag/$TAG"; note; } > body.md
  gh issue create --title "Keys: $e" --body-file body.md
elif [ -f $O/report.json ] && [ -f episodes/$e.json ] && ! ls $O/*.mp4 >/dev/null 2>&1; then
  { echo "## $e: shots only (test run)"; echo '```json'; cat $O/report.json; echo '```'; note; } > body.md
  gh issue create --title "Test: $e" --body-file body.md
elif [ -f $O/report.json ] && [ -f episodes/$e.json ]; then
  gh release create "$TAG" $O/*.mp4 $(ls $O/thumb*.jpg $O/review.jpg 2>/dev/null) $O/report.json $(ls $O/modal.json 2>/dev/null) --title "$e" \
    --notes "Watch it on your phone, then answer in the review issue."
  { python tools/review_body.py $O/report.json $REPO $TAG; note; } > body.md
  gh issue create --title "Review: $e" --body-file body.md
elif [ -f $O/report.json ]; then
  gh release create "$TAG" $O/*.png $(ls $O/sheet_*.jpg 2>/dev/null) $O/report.json $(ls $O/modal.json 2>/dev/null) --title "$e candidates" \
    --notes "Design candidates. Pick in the review issue."
  { python tools/cast_body.py $O $REPO $TAG; note; } > body.md
  gh issue create --title "Review: $e" --body-file body.md
else
  { echo "## $e failed ($RUN)"; echo '```'; tail -c 3500 $O/run.log 2>/dev/null || tail -c 3500 $O/console.log 2>/dev/null; echo '```'; } > body.md
  gh issue create --title "Failed: $e" --body-file body.md
fi
