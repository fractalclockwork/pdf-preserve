# pdf-preserve

Transcribe a scanned PDF into per-page Markdown. Prose stays text. Mathematics and tables are LaTeX. Figures are cropped images.

Run this on hellway. The converter uses Docling on a GPU. Do not run it on the laptop.

The labeled Chu scan in this directory is the validation set. The design is `scan_preservation_tool.plan.md`.

```bash
uv sync
uv run preserve score gold/chu
uv run preserve convert Digital_computer_design_fundamentals__Yaohan_Chu_1962_toc.pdf out --pages xi,1,6
```

`out/` is generated and gitignored. The first `score` run records `gold/chu/baseline.json`. Later runs fail if that baseline regresses.
# pdf-preserve
