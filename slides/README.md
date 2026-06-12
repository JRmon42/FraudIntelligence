# Capstone Presentation

`Heimdall_AMA_Capstone.pptx` is the 45-minute capstone deck for AMA Case Study 30, generated from the official template `Azure Master Architect_Prezo_Template_v01.pptx`.

To regenerate (e.g. after editing content), drop the template into `/tmp/slidebuild/template.pptx` and run:

```bash
python3 slides/build_deck.py
```

## Structure (22 slides, ~45 min including 10-min demo and 5-min Q&A)
1. Title
2. Agenda
3. Customer & problem
4. Business case
5. Target outcomes
6. Solution at a glance
7. Reference architecture (placeholder for the diagram from `docs/architecture.md`)
8. Hot path (<18 ms scoring)
9. Cold path (graph + analytics)
10. AI/ML strategy
11. Agentic AI
12. Compliance by design
13. Sovereignty
14. Security & DevSecOps
15. MLOps & responsible AI
16. Multi-region resilience
17. FinOps
18. Live demo
19. Key benefits & value
20. Risks & mitigations
21. Roadmap
22. Closing

Speaker notes are populated for every slide.
