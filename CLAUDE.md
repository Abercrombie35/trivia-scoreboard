# Trivia scoreboard: instructions for Claude

This repo is a live trivia-night scoreboard. GitHub Pages serves `index.html` from
`main` at https://abercrombie35.github.io/trivia-scoreboard/. Several co-hosts
record scores from their own Claude sessions at the same time.

## How to record scores

Always use `score.py`. It pulls the latest scores from GitHub, applies the change,
regenerates `index.html`, commits and pushes to `main`. If another co-host pushed
first, it re-applies the change on top of theirs automatically.

```
python3 score.py show                          # current standings (run this first)
python3 score.py teams "Name One" "Name Two"   # add teams -> T1, T2, ... plus initials (e.g. QB)
python3 score.py round 3 T1=8 SP=6.5 bears=7   # set round 3 scores; teams by T#, number, initials or part of the name
python3 score.py round 3 8 6.5 7 5 9 6         # set round 3 for every team, in T1..Tn order
python3 score.py adjust T4 -1 "phone use"      # bonus or penalty outside a round
python3 score.py rename T2 "New Name"
python3 score.py delround 3
python3 score.py title "Quiz Night"
python3 score.py undo                          # reverts the most recent change, whoever made it
```

## Rules

- Never edit `scores.json` or `index.html` by hand, and never force-push.
- Work directly on `main`. Do not create branches or pull requests: the page only publishes from `main`.
- `round N` **sets** scores for that round (it never adds), so fix a wrong score by re-running `round N` for that team.
- Before `undo`, run `show` and check that the most recent change is the one the user means: another co-host may have recorded something since.
- For a scoresheet photo, list the scores you read and get the user's OK before recording them.
- After every change, reply with the table the script prints and say the live page updates in about a minute.
- If the script reports `PUSH FAILED` or cannot pull, tell the user the scores were **not** published and show the error.
