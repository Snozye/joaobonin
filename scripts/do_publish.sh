#!/bin/bash
REPO="$HOME/Desktop/joaobonin.com"
MSG="write-ups: add htb-monteverde and htb-sauna"
rm -f "$REPO/.git/index.lock"
cd "$REPO"
/usr/bin/git add content/posts/ static/images/ scripts/ inputs_posts/.pending-commit 2>&1
/usr/bin/git commit -m "$MSG" 2>&1
/usr/bin/git push origin main 2>&1
echo "DONE"
