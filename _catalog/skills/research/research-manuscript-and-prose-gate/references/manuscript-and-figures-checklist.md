# Scientific Manuscript & Publication Figures Checklist

## 1. Grounded Writing (`numbers.md` + `glossary.md`)
- Maintain a single `numbers.md` Markdown table (`| ID | Value | Source |`) generated directly from verified experiment scripts; `check_section.py --numbers numbers.md` reads verified numbers from column 2 and fails on any unverified figure in LaTeX prose.
- Maintain a `glossary.md` mapping canonical terms and banned synonyms (`Do not use`) so metrics, model names, and symbols never drift across sections.
- Run `check_section.py --final` before submission to fail on any leftover `[TODO]`, `[CITE:]`, `??`, or unresolved `\ref{}`.

## 2. Clear Human Scientific Prose (`stylometry.py`)
- Avoid hollow LLM fillers ("delve", "tapestry", "testament", "leveraging cutting-edge", "remarkable"). State exact mechanisms and measured effect sizes.
- Always run `stylometry.py compare <before> <after>` after editing prose to prove zero numbers, citations, or cross-references were dropped or altered.

## 3. Publication Figure Hygiene (`check_figure_pdf.py`)
- Save figures at exact venue physical dimensions (`ieee` 3.5 / 7.16 in, `neurips`/`iclr` 5.5 in, `icml` 3.25 / 6.75 in, `nature` 3.5 / 7.2 in) so LaTeX never rescales embedded font sizes.
- Configure `matplotlib.rcParams["pdf.fonttype"] = 42` to avoid bitmap Type 3 fonts.
- Encode series redundantly using both colour-blind safe palettes (e.g., Paul Tol / Okabe-Ito) and distinct line styles or markers so plots stay readable in greyscale print.
