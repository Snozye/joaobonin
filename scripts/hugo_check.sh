#!/bin/bash
cd "$HOME/Desktop/joaobonin.com"
/opt/homebrew/bin/hugo --buildDrafts 2>&1 | grep -E "ERROR|WARN|Built in|pages"
echo "exit:${PIPESTATUS[0]}"
