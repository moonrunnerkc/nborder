# Generating README screenshots

The README screenshots come from a deterministic capture pipeline. This page covers how to regenerate them when a future release changes user-visible behavior.

## What the pipeline produces

| Image | Source | Renderer |
|-------|--------|----------|
| Terminal output (`nborder check`, `nborder rule`, `--select`) | Captured stdout to a `.txt` log | Pillow ANSI-aware renderer |
| Notebook screenshots (cell layouts, NameError tracebacks) | `.ipynb` file | `jupyter nbconvert --to html` plus headless Chromium via Playwright |

Two renderers, one tool each. Terminal output is text; the Pillow path renders it directly. Notebook output needs Jupyter's actual stylesheet (cell prompts, syntax highlighting, the red-tinted error block) so a hand-rolled layout looks fake to anyone who has used Jupyter; the headless Chromium path uses the real CSS.

## Pillow ANSI-to-PNG renderer

A ~140-line script (`tools/render_text_png.py` in the evidence bundle) that takes a text file, strips ANSI escapes, and renders to a Tokyo Night Storm PNG with a faux terminal chrome (three colored dots, centered title bar). Word-boundary wrap with a 2-space hanging indent on continuation lines. Default width 1400 pixels, which fits a 145-character `nborder` diagnostic line on one row.

```bash
python tools/render_text_png.py logs/01_nb101_check.txt screenshots/01_nb101_terminal.png \
    --title "nborder check"
```

Dependencies: `Pillow`. No system fonts beyond DejaVu Sans Mono, which Ubuntu and most distros ship by default. The renderer falls back to PIL's bitmap font if DejaVu is missing.

## Notebook screenshots via Playwright

`tools/render_notebook_html.py` runs `jupyter nbconvert --to html` against the input notebook, opens the generated HTML in headless Chromium at `device_scale_factor=2`, queries `document.body.scrollHeight`, resizes the viewport to fit, and screenshots the visible region. The `body.scrollHeight` step matters; `documentElement.scrollHeight` clamps to the viewport height and produces tall PNGs with empty trailing whitespace.

```bash
playwright install chromium  # one-time setup
python tools/render_notebook_html.py notebooks/_executed_NB201.ipynb \
    screenshots/02_nb201_nameerror.png
```

For NameError screenshots that need to match Restart-and-Run-All semantics (failing cell shows `In [N]:`, subsequent cells show `In [ ]:`), execute the notebook with `nbclient.NotebookClient(allow_errors=False)` after clearing all execution counts and outputs. `jupyter nbconvert --execute --allow-errors` continues past errors and assigns counts to subsequent cells, which is not what RRA actually does.

Dependencies: `jupyter`, `nbconvert`, `playwright` plus its bundled Chromium (~150 MB). The Chromium download is one-time; subsequent runs reuse the cached binary.

## Why not charmbracelet/freeze

`charmbracelet/freeze` v0.2.0 segfaults reliably on Ubuntu 24.04 with kernel 6.17.0 in the Go runtime memory allocator. No diagnostic, just a SIGSEGV with no useful stack. Pinned older releases may work but are not maintained, and pinning to an upstream version that has been deprecated is a maintenance trap. The Pillow path produces equivalent output with no native dependencies.

## Reproducing the README screenshots

The full evidence-capture pipeline lives outside the repo at `~/nborder-evidence/` and runs against the locally installed wheel. To regenerate one screenshot:

1. Capture the source: terminal output to a `.txt` log, or save the notebook with the right execution state.
2. Run the appropriate renderer with the destination path under `docs/images/`.
3. Stage and commit the PNG; the README references it by path.

The renderers themselves are intentionally not bundled with nborder; they are developer tools, not runtime surface.
