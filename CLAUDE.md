# Project instructions

## Stacked/dependent PRs

This repo has `delete_branch_on_merge` **enabled** (GitHub repo setting). When opening multiple PRs that each depend on the previous one (PR B's base is PR A's branch, not `main`), rely on that setting rather than manually retargeting bases:

- GitHub only auto-retargets a dependent PR's base when the branch it points at is **deleted** - not merely merged. Deleting it (via the web UI's merge-button "Delete branch", which `delete_branch_on_merge` triggers automatically) is what makes GitHub notice "PR B's base is gone, and it was based on main's commit anyway" and repoint PR B's base to `main` for you.
- `gh pr merge --delete-branch` (CLI) does **not** trigger this retargeting - it closes dependent PRs instead of retargeting them. Merge stacked PRs through the GitHub web UI (or anything that performs an equivalent web-UI merge+delete), not the CLI, when a dependent PR exists.
- Merge strictly bottom-up: the PR whose base is `main` first, then the next one up the stack, letting each merge+delete trigger the next PR's auto-retarget before you merge it.
- If a stack gets merged out of order, or some head branches were left undeleted, don't assume content is lost - verify containment before any manual fix:
  ```
  git fetch origin <branch1> <branch2> ... main
  git merge-base --is-ancestor origin/<branch> origin/main && echo "safe to delete, fully in main"
  git diff origin/main origin/<branch> --stat   # confirms no unique content either way
  ```
  If some PR's content never reached `main` (each merge landed on its own stacked base instead), find the branch tip that cumulatively contains everything, verify a conflict-free merge locally (`git merge --no-commit --no-ff origin/<tip>` from a throwaway branch off `main`, then abort), and open one PR from that tip into `main`.
