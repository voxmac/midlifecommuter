#!/usr/bin/env bash
# Publish a finished GPU job (Modal or Kaggle): GitHub Release + review issue.  usage: publish.sh ID OUTDIR "runner line"
e=$1; O=$2; RUN=$3
TAG="$e-$(date -u +%m%d-%H%M)"
note() { echo; echo "$RUN"; }
if [ -f $O/report.json ] && [ -f songs/$e.json ]; then
  gh release create "$TAG" $O/*.mp3 $(ls $O/*.wav 2>/dev/null) $O/report.json $(ls $O/modal.json 2>/dev/null) --title "$e song versions" \
    --notes "Listen on your phone, then answer in the review issue."
  { python tools/song_body.py $O/report.json $REPO $TAG; note; } > body.md
  gh issue create --title "Review: $e" --body-file body.md
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
