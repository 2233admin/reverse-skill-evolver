# AIGX bootstrap

This repository uses AIGX as its canonical agent-context format. Read `.aigx/protocol.aigx` first, then the concern files touched by the task. For every indexed non-genome file you edit, resolve its entry in `.aigx/files.aigx`, obey its critical forbids and gotcha, and verify every listed check before finishing. Genome edits are governed by official lint.

`RULES.md` and `skills/**/SKILL.md` are workflow entry points after the AIGX context gate; they are not competing sources of project rules.
