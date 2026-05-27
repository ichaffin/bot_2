#!/bin/bash
cd "$(dirname "$0")"
git add bot.log
git diff --cached --quiet && exit 0
git commit -m "log: auto update $(date '+%Y-%m-%d %H:%M')"
git push
