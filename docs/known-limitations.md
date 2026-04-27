# Known limitations

## Cell-relative line numbers in GitHub annotations

`nborder` reports line and column positions inside the source code of the offending notebook cell, not against the line offset of the cell within the raw `.ipynb` JSON. GitHub's annotation system displays these line numbers verbatim against the rendered `.ipynb` view, so the marker may land on the cell-relative line rather than the JSON-source line.

This is fine for the common review workflow (annotations point at the right cell, and the line number refers to a position inside the cell's source), but it does mean a click-through to a `code=` snippet view will not match the JSON line. Tracking notebook-wide line offsets is a v0.2 item; the JSON line numbers in `.ipynb` files are not stable across editors anyway, so the cell-relative form is a reasonable trade-off.

## Multi-language kernels

v0.1 supports Python kernels only. R and Julia notebooks are accepted at parse time but produce no diagnostics. Multi-language support is reserved for a future release.

## Magic-only cells

A code cell whose entire body is a cell magic (`%%bash`, `%%capture`, etc.) is treated as opaque after the magic is stripped. Any bindings the magic creates are recorded when the registry knows about them (currently `%%capture <name>`); other cell magics produce no graph edges. False negatives are possible for unusual magics that introduce names.
