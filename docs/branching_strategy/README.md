# Branching strategy

- `main` — the stable, always-working branch. Only updated by merging in
  from `default` once changes have been tested locally.
- `default` — the shared working branch. All three of us commit and push
  directly here as we build.
- Commit messages: short, describes what changed (`Add TripDetailView`,
  `Fix trip_list.html empty state`) — not `fix`, `update`, `wip`.

## Workflow

1. Pull `default` before starting any new work: `git pull origin default`.
2. Make changes, commit, push to `default`.
3. Once everything's tested and working, merge `default` into `main`:
```
   git checkout main
   git pull
   git merge default
   git push
```