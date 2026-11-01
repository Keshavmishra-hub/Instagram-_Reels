---
name: reel-make
description: Produce a complete Instagram Reel end-to-end with ReelForge in Claude Code mode (research, script, storyboard, render, QC). Use when the user asks Claude Code to make a reel about a topic.
---

# Make a reel end-to-end (Claude Code mode)

1. `python -m reelforge new "<topic>" --style <style> --duration 45 --lang en` (prints the project id).
   Styles: documentary, explainer, mystery, historical, business, agriculture, science, current_affairs, facts, human_stories.
2. Follow the `reel-research` skill. Stop and tell the user if the research is insufficient.
3. Show the user the research summary; approve only with their consent (`python -m reelforge approve research <id>`).
4. Follow `reel-script`; show the script; approve with consent (`python -m reelforge approve script <id>`).
5. Follow `reel-storyboard`.
6. `python -m reelforge produce <id>` (voice -> stock media -> render -> caption -> QC). Exit code 2 = QC failed.
7. Read `projects/<id>/output/qc_report.md`. Fix every critical failure (never mark a reel complete with one) and
   re-run the affected stage. Deliverables are in `projects/<id>/output/`.
