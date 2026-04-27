# Generating screenshots for nborder docs

Some marketing material and rule docs benefit from a static rendering of the CLI output. The recommended path is a small Pillow renderer; `charmbracelet/freeze` is intentionally avoided.

## Recommended: Pillow ANSI-to-PNG renderer

A ~50-line script that converts ANSI text to a dark-themed monospace PNG covers every screenshot use case in this repo. Capture the output to a file with `nborder check ... > out.txt 2>&1`, strip ANSI escapes, render onto a Pillow `Image` with a monospace font, and write a PNG. No subprocess kernel state, no flaky text rendering, no GPU dependency.

The renderer requires only `Pillow` from the dev environment; nothing new lands on `dev` extras.

## Why not `charmbracelet/freeze`

`charmbracelet/freeze` v0.2.0 segfaults reliably on Ubuntu 24.04 with kernel 6.17.0 inside the Go runtime memory allocator. It produces no diagnostic, just a SIGSEGV with no useful stack. Pinned older releases (v0.1.x) may still work but are not maintained, and pinning to an upstream version that has been deprecated is a maintenance trap.

If you are running this on a different platform and want to use `freeze` anyway, validate first by running it once on a known-good input. If it segfaults, fall back to the Pillow path; do not spend time bisecting upstream Go runtime issues.

## Why not headless browser screenshotting

Spinning up a real terminal in `xvfb`, configuring `fontconfig`, and screenshotting the output works but adds significant CI weight: a half-gigabyte of fonts and a Chromium download for what amounts to rendering text. The Pillow path is faster and more deterministic.

## Reproducing a screenshot

1. Capture the CLI output: `nborder check tests/fixtures/NB103/numpy_unseeded.ipynb > /tmp/example.txt 2>&1`.
2. Run the Pillow renderer against `/tmp/example.txt`.
3. Drop the resulting PNG into `docs/screenshots/`.

The renderer script is not bundled with `nborder` itself; it is a developer-only tool kept out of the runtime surface.
