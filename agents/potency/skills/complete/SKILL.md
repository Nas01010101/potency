---
name: complete
description: After editing, lists up to 5 files linked to the edited files by imports, shared commit history, or the issue text, which the fix may also need to change.
---
Run `scripts/complete.py` with `run_skill_script` after your edit and before `submit_patch`, passing the issue's key terms as `args`. Example: `run_skill_script(skill_name="complete", file_path="scripts/complete.py", args=["coordinate", "transform", "ITRS", "observed"])`.

Output: the files you edited, then up to 5 other files, each tagged with the signals that linked it (`imports`, `co-change`, `issue`). Test files are excluded. Open each listed file that calls or defines what you changed and decide whether it needs the same change; it is fine to change none of them. In replay on 17 SWE-bench harnesses, the list held a gold file the agent had missed on about 55% of incomplete multi-file patches.
