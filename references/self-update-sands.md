# Self-Update (`sands.update`)

`references/self-update-sands.md` documents how `sands.update` pulls the latest
skill from its GitHub source. This skill ships **no `scripts/update.sh`** — the
pull is done by the platform's self-update path, so do not invoke a shell
script that isn't in the tree.

## What survives an update

The source repo holds code and docs only. All runtime state lives **outside**
the skill directory and is never touched by a pull:

| Path | Contents |
|---|---|
| `{agent_root}/commons/data/ocas-sands/config.json` | Calendar ids, timezone, `auth_status`, `last_*` timestamps |
| `{agent_root}/commons/data/ocas-sands/evidence.jsonl` | Per-run evidence records (append-only) |
| `{agent_root}/commons/data/ocas-sands/decisions.jsonl` | Material decisions (conflicts resolved, travel inserted) |
| `{agent_root}/commons/data/ocas-sands/events.jsonl` | Event interaction history |
| `{agent_root}/commons/data/ocas-sands/intents.jsonl` | Recorded intents |
| `{agent_root}/commons/journals/ocas-sands/{action,observation}.jsonl` | Journals |

## Before pulling

- [ ] `git status` in the skill repo is clean, or the pull is `--ff-only`
- [ ] No uncommitted local edits to SKILL.md / templates that a merge would clobber
- [ ] Remember to re-check the Support File Map afterwards — a new reference may be added, and a renamed one will silently dangle

## After pulling

- [ ] `python3 scripts/append_jsonl.py --help` exits 0 (proves the guard survived the merge, not that the script works)
- [ ] Re-read the Support File Map and confirm every listed path exists
- [ ] Record the version bump in `CHANGELOG.md` and bump `metadata.version` in SKILL.md frontmatter

## Why `--ff-only`

A fast-forward-only pull refuses to construct a merge commit. On a dirty
worktree or with diverged local history, a plain `git pull` will happily merge —
and, in a skill that other skills read by path, a half-merged SKILL.md fails
silently at the next load. Refusing is the safe default; `--force` overrides only
when the operator has confirmed the local edits are disposable.
