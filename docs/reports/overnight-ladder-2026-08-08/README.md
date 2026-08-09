# Overnight ladder proof archive — 2026-08-08

Raw artifacts from the model-strength ladder on vuln_app_hard (full stack:
substrate fix + coverage gate + REPL + replan). Each model directory holds
`matrix.json` (graded 3x3 cells) plus surviving raw RGI cell reports.

## nemotron-3-nano_4b
- matrix.json: rgi 0.733 / fixed 0.489 / single 0.200 (mean recall)
- rgi_cell_1.json (29 calls), rgi_cell_2.json (14 calls): genuine 4b cells.
- CELL 0 LOST: overwritten by a pytest mock eval before archiving (cause:
  CWD-relative cell path in eval.py; fixed in the same commit that added
  this archive). The graded numbers for all 3 cells survive in matrix.json.

Later models (coder-7b, 1.5b, 9b) archived as they land.
