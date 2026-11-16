# Documentation claim auditor

An offline static auditor comparing documentation promises with listed source patterns. It reads root README.md and Markdown files under any docs path component. Source is parsed with the standard library and never executed. Runtime uses no network, telemetry, third-party dependencies or file writes.

## Usage

```sh
python3 -m pip install .
pdf-generation-claim-audit audit . --json
python3 -m pdf_generation_claim_audit audit . --verbose
pdf-generation-claim-audit audit . --fail-on medium --ignore vendor --ignore generated
pdf-generation-claim-audit --version
```

The subcommand defaults to the current directory. Each ignore option accepts one relative POSIX path prefix and can be repeated. The default threshold is high; medium also fails on test-only findings. Exit codes are 0 for PASS, 2 for findings meeting the threshold, and 1 for usage or I/O errors. A PASS may contain a medium finding. JSON contains verdict, findings (rule, severity, message, locations), claims, production_evidence and test_evidence. Verbose text includes claims and evidence locations.

## Matching

Blank lines delimit paragraphs. Backtick and tilde fences with up to three leading spaces are excluded; inline code counts. Text is lowercased, contractions expanded, hyphens replaced with spaces, and whitespace collapsed. Exact phrases match at word boundaries, longest first with alphabetical ties. Denial spans are removed before positive matching. There is at most one finding per claim family.

Import aliases resolve; local function, method and class definitions shadow route names. Assignments, annotated assignments and context-manager bindings shadow imported names. Attribute assignments do not shadow a base import. Syntax-invalid files and symlinks provide no evidence. Files under fixtures, docs and examples are excluded; files under tests or named test_*.py or *_test.py are tracked separately. A positive statement without source fails; a denial without source passes.

```text
documented-pdf-generation-claim-false HIGH (MEDIUM when evidence is test-only)
documented-no-pdf-generation-claim-false HIGH
```

## Evidence and scope

The checked capability produces a PDF document from code, data, HTML or Markdown. All constructor/write pairs must appear within a single module. Matching does not require object identity or call order. The accepted routes are:

```text
reportlab.pdfgen.canvas.Canvas / reportlab.Canvas + .save()
reportlab.platypus.SimpleDocTemplate / BaseDocTemplate + .build()
fpdf.FPDF (fpdf2 distribution) + .output()
weasyprint.HTML + .write_pdf()
pypdf.PdfWriter / PyPDF2.PdfWriter / PyPDF2.PdfFileWriter + .write()
fitz.open / fitz.Document + .save()
xhtml2pdf.pisa.CreatePDF (single call)
```

Each constructor alone is insufficient: a canvas without a save call writes no completed file; opening an existing document may only read it. The other paired constructors likewise require their respective write calls in the same module. Generic attribute calls count on any base; bare names require an import resolving to a listed name. Definitions with the same name shadow these routes.

```text
generate_pdf generate_pdfs create_pdf create_pdfs export_pdf
export_to_pdf export_as_pdf write_pdf save_pdf save_as_pdf
build_pdf render_pdf make_pdf generate_pdf_report create_pdf_report
export_pdf_report write_pdf_file convert_to_pdf html_to_pdf
markdown_to_pdf text_to_pdf pdf_export pdf_generator create_pdf_document
```

## Limitations

Static matching is not semantic judgement. Dead code counts; unsupported alias chains are missed. Exact phrases only are recognized, and denial handling depends on the fixed list. Calls split across modules are missed. File content, destination extensions and successful execution are not verified.

Ambiguous wording can describe an empty document shell, a menu that downloads a file made elsewhere, a report delivered from another service, conversion delegated to an external program, or a graphical print dialog. Other wording may describe a reader wrapper or job title, rendering an existing page as an image, assembling pre-rendered pages, or building a tool itself. These meanings still match the listed phrases; only code patterns decide whether a finding follows.

Reading documents, extracting text or tables, console printing, and saving text, HTML, Markdown or images do not count. Bare imports, strings, filenames, extensions and comments do not count. Deliberately unsupported operations include:

```text
pypdf / PyPDF2 PdfReader
pdfplumber / fitz / pdfminer extract_text
camelot / tabula read_pdf or convert_into
pdfplumber extract_table / extract_tables
pytesseract image_to_string
print(), open(..., 'w').write(), Path.write_text(), Image.save()
pdfkit from_string / from_file / from_url; wkhtmltopdf
matplotlib PdfPages / savefig, including a .pdf destination
borb / pikepdf / pdfrw writes
```

The plotting backend and unlisted libraries above are missed even when they produce valid documents. External binaries and all subprocess CLI calls are excluded by design, including conversion programs and the extraction vendor CLI. Manual assembly of raw document syntax and bytes without a listed call is also missed.

Extraction services do not supply a route for the checked operation. No product, model or processor identifier changes this. Opaque identifiers and dashboard-configured uploads are unsupported. This applies to:

```text
mindee parse with any product
Azure begin_analyze_document / begin_analyze_document_from_url with any model id
veryfi calls of any kind
Google Document AI process_document / batch_process_documents with any processor
Eden AI universal-ai with any model id
Textract calls of any kind
LlamaParse calls
Nanonets / Docsumo / ABBYY Vantage / Rossum / Klippa / Parseur / Extend
```

Adjacent extraction, recognition, page-grouping and cropping claims are outside this vocabulary. These include invoices, receipts, passports and other identity documents, bank checks and statements, tax forms, pay stubs, health insurance cards, business cards, credit cards, contracts, mortgages, resumes, bills of lading, delivery notes, carte grises, energy bills, marriage certificates, bank account details, nutrition labels, material certificates, US mail, invoice splitting, multiple-receipt detection, French health cards, Indian passports, driver licenses, vaccination cards and document cropping.

## Development

```sh
python3 -m unittest discover
python3 -m build
```

Both distributions include the regression suite and a fixed-literal vocabulary oracle. The exact vocabulary is listed below. The project is MIT licensed.

## Positive phrases

```text
pdf generation
generate pdf
generates pdf
generating pdf
generate pdfs
generates pdfs
generating pdfs
create pdf
creates pdf
creating pdf
create pdfs
creates pdfs
creating pdfs
export pdf
exports pdf
exporting pdf
export to pdf
exports to pdf
exporting to pdf
export as pdf
exports as pdf
exporting as pdf
pdf export
pdf exports
pdf exporter
pdf report generation
generate pdf report
generates pdf report
generating pdf report
generate pdf reports
create pdf report
creates pdf report
write pdf
writes pdf
writing pdf
save as pdf
saves as pdf
save to pdf
saves to pdf
pdf writer
pdf writing
build pdf
builds pdf
building pdf
render pdf
renders pdf
rendering pdf
convert to pdf
converts to pdf
converting to pdf
```

## Denial phrases

```text
no pdf generation
does not generate pdf
does not generate pdfs
does not support pdf generation
without pdf generation
no pdf export
does not export pdf
does not export to pdf
does not create pdf
does not create pdfs
no pdf writer
does not write pdf
does not save as pdf
no pdf report generation
does not generate pdf reports
does not build pdf
does not render pdf
does not convert to pdf
pdf generation not supported
no pdf generation support
without pdf export
does not support pdf export
no pdf exporter
does not generate pdf report
```
