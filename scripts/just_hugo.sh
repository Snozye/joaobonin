#!/bin/bash
cd /Users/joao/Desktop/joaobonin.com
/opt/homebrew/bin/hugo --buildDrafts --noBuildLock > /tmp/hugo_all.txt 2>&1
echo "exitcode:$?" > /tmp/hugo_exit.txt
