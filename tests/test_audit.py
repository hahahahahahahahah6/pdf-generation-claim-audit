"""Fixed specification oracles and behavioral regressions; no external services."""
import ast
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from pdf_generation_claim_audit import phrases
from pdf_generation_claim_audit.audit import audit, module_evidence, normalize, paragraphs, matches
from pdf_generation_claim_audit.__main__ import main

# Independently transcribed specification literals; never read the external spec.
EXPECTED_YES = '''pdf generation
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
converting to pdf'''.splitlines()
EXPECTED_NO = '''no pdf generation
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
does not generate pdf report'''.splitlines()
EXPECTED_GENERIC = '''generate_pdf generate_pdfs create_pdf create_pdfs export_pdf
export_to_pdf export_as_pdf write_pdf save_pdf save_as_pdf build_pdf render_pdf
make_pdf generate_pdf_report create_pdf_report export_pdf_report write_pdf_file
convert_to_pdf html_to_pdf markdown_to_pdf text_to_pdf pdf_export pdf_generator
create_pdf_document'''.split()

CANVAS = 'from reportlab.pdfgen.canvas import Canvas\nc = Canvas("out.pdf")\nc.save()'
POSITIVE_RULE = 'documented-pdf-generation-claim-false'
NEGATIVE_RULE = 'documented-no-pdf-generation-claim-false'


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def put(self, path, content):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding='utf-8')

    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                status = main(list(args))
            except SystemExit as exc:
                status = exc.code
        return status, out.getvalue(), err.getvalue()

    def test_phrase_oracle(self):
        tree = ast.parse(Path(phrases.__file__).read_text(encoding='utf-8'))
        parsed = {n.targets[0].id: ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)}
        for key, expected, count in [('PDFGENERATION', EXPECTED_YES, 50), ('NOPDFGENERATION', EXPECTED_NO, 24), ('GENERIC_NAMES', EXPECTED_GENERIC, 24)]:
            self.assertEqual(parsed[key], tuple(expected))
            self.assertEqual(len(set(parsed[key])), count)
            if key != 'GENERIC_NAMES':
                self.assertEqual(list(parsed[key]), [normalize(p) for p in parsed[key]])

    def test_good(self):
        self.put('README.md', 'We generate PDF.')
        self.put('main.py', CANVAS)
        self.assertEqual(audit(self.root)['verdict'], 'PASS')
        self.assertEqual(self.cli('audit', str(self.root))[0], 0)

    def test_bad(self):
        self.put('README.md', 'PDF generation')
        code, out, _ = self.cli('audit', str(self.root), '--json')
        self.assertEqual(code, 2)
        result = json.loads(out)
        self.assertEqual(result['verdict'], 'FAIL')
        self.assertEqual(result['findings'][0]['rule'], POSITIVE_RULE)
        self.assertEqual(result['findings'][0]['severity'], 'HIGH')
        self.assertTrue(result['findings'][0]['message'])

    def test_test_only(self):
        self.put('README.md', 'generate pdf')
        self.put('tests/check.py', CANVAS)
        self.assertEqual(audit(self.root)['findings'][0]['severity'], 'MEDIUM')
        self.assertEqual(self.cli('audit', str(self.root))[0], 0)
        self.assertEqual(self.cli('audit', str(self.root), '--fail-on', 'medium')[0], 2)

    def test_denial_and_no_source(self):
        self.put('README.md', 'does not generate pdf')
        self.assertEqual(audit(self.root)['verdict'], 'PASS')
        self.put('main.py', CANVAS)
        result = audit(self.root)
        self.assertEqual(result['findings'][0]['rule'], NEGATIVE_RULE)
        self.assertEqual(result['findings'][0]['severity'], 'HIGH')
        self.assertFalse(result['claims']['positive'])
        self.assertEqual(self.cli('audit', str(self.root))[0], 2)

    def test_no_claim(self):
        self.put('README.md', 'Extract invoices; crop documents; recognize text.')
        self.put('main.py', CANVAS)
        self.assertEqual(audit(self.root)['verdict'], 'PASS')

    def test_all_phrases(self):
        for phrase in EXPECTED_YES:
            with self.subTest(phrase=phrase):
                self.put('README.md', phrase)
                self.assertTrue(audit(self.root)['claims']['positive'])
        for phrase in EXPECTED_NO:
            with self.subTest(phrase=phrase):
                self.put('README.md', phrase)
                result = audit(self.root)
                self.assertFalse(result['claims']['positive'])
                self.assertEqual([x['phrase'] for x in result['claims']['negative']], [phrase])

    def test_normalization_boundaries_and_order(self):
        self.assertEqual(normalize("DOESN'T  generate-PDF"), 'does not generate pdf')
        self.assertEqual(matches('generate pdf reports', EXPECTED_YES)[0], ['generate pdf reports'])
        self.assertFalse(matches('regenerate pdfsuffixed', EXPECTED_YES)[0])
        self.put('README.md', "doesn’t generate-PDF\n\nWe CREATE\nPDFs")
        result = audit(self.root)
        self.assertEqual(len(result['claims']['positive']), 1)
        self.assertEqual(len(result['claims']['negative']), 1)
        self.put('README.md', 'generate\n\npdf')
        self.assertFalse(audit(self.root)['claims']['positive'])

    def test_fences_and_inline(self):
        for fence in ('```', '~~~~'):
            for indent in ('', '   '):
                self.put('README.md', indent + fence + 'text\ngenerate pdf\n' + indent + fence)
                self.assertEqual(audit(self.root)['verdict'], 'PASS')
        self.put('README.md', '`generate pdf`')
        self.assertEqual(audit(self.root)['verdict'], 'FAIL')
        self.assertEqual(paragraphs('```\ngenerate pdf'), [])

    def test_docs_selection(self):
        self.put('other.md', 'generate pdf')
        self.assertEqual(audit(self.root)['verdict'], 'PASS')
        self.put('nested/docs/a.md', 'generate pdf')
        self.assertEqual(audit(self.root)['verdict'], 'FAIL')

    def test_excluded_paths(self):
        self.put('README.md', 'generate pdf')
        for path in ('fixtures/a.py', 'docs/a.py', 'examples/a.py', 'a/fixtures/b.py'):
            with self.subTest(path=path):
                self.put(path, CANVAS)
                result = audit(self.root)
                self.assertFalse(result['production_evidence'])
                self.assertFalse(result['test_evidence'])
        for path in ('tests/a.py', 'test_one.py', 'one_test.py', 'nested/tests/a.py'):
            with self.subTest(path=path):
                self.put(path, CANVAS)
                self.assertEqual(audit(self.root)['findings'][0]['severity'], 'MEDIUM')

    def test_symlinks(self):
        self.put('README.md', 'generate pdf')
        self.put('fixtures/real.py', CANVAS)
        (self.root / 'alias.py').symlink_to(self.root / 'fixtures/real.py')
        (self.root / 'linked').symlink_to(self.root / 'fixtures', target_is_directory=True)
        self.assertFalse(audit(self.root)['production_evidence'])
        (self.root / 'README.md').unlink()
        self.put('fixtures/readme.md', 'generate pdf')
        (self.root / 'README.md').symlink_to(self.root / 'fixtures/readme.md')
        self.assertFalse(audit(self.root)['claims']['positive'])

    def test_ignore_and_verbose(self):
        self.put('README.md', 'generate pdf')
        self.put('vendor/a.py', CANVAS)
        self.put('generated/a.py', CANVAS)
        status, out, _ = self.cli('audit', str(self.root), '--ignore', 'vendor', '--ignore', 'generated', '--verbose')
        self.assertEqual(status, 2)
        self.assertIn('claims', out)
        self.assertEqual(self.cli('audit', str(self.root), '--ignore', 'README.md')[0], 0)

    def test_usage_io_version_entry(self):
        for args in ([], ['audit', '/no/such/repository'], ['audit', '--fail-on', 'HIGH'], ['audit', '.', '--ignore', 'a', 'b'], ['wrong']):
            self.assertEqual(self.cli(*args)[0], 1)
        self.assertEqual(self.cli('--version')[:2], (0, '0.1.0\n'))
        proc = subprocess.run([sys.executable, '-m', 'pdf_generation_claim_audit', '--version'], capture_output=True, text=True)
        self.assertEqual((proc.returncode, proc.stdout), (0, '0.1.0\n'))
        self.put('README.md', 'generate pdf')
        self.put('bad.py', 'def invalid(:')
        self.assertEqual(audit(self.root)['verdict'], 'FAIL')
        self.put('README.md', '\udcff'.encode('utf-8', 'surrogatepass').decode('latin1'))
        (self.root / 'README.md').write_bytes(b'\xff')
        self.assertEqual(self.cli('audit', str(self.root))[0], 1)

    def test_split_modules(self):
        self.put('README.md', 'generate pdf')
        for constructor, writer in [('from reportlab.pdfgen.canvas import Canvas\nCanvas()', 'save'), ('from reportlab.platypus import SimpleDocTemplate\nSimpleDocTemplate()', 'build'), ('from fpdf import FPDF\nFPDF()', 'output'), ('from weasyprint import HTML\nHTML()', 'write'), ('from pypdf import PdfWriter\nPdfWriter()', 'write'), ('import fitz\nfitz.open()', 'save')]:
            self.put('a.py', constructor)
            self.put('b.py', 'x.' + writer + '()')
            self.assertFalse(audit(self.root)['production_evidence'])

    def test_readme_self_audit(self):
        root = Path(__file__).resolve().parents[1]
        result = audit(root, ignore=('.venv', 'venv', 'build', 'dist', '.verification'))
        self.assertEqual(result['verdict'], 'PASS')
        self.assertFalse(result['claims']['positive'])
        self.assertFalse(result['claims']['negative'])
        text = (root / 'README.md').read_text(encoding='utf-8')
        self.assertTrue(text.startswith('# Documentation claim auditor\n'))
        for p in paragraphs(text):
            self.assertFalse(matches(p, EXPECTED_YES + EXPECTED_NO)[0])


# Generate separately counted regression cases from fixed route tables.
GOOD = [
    CANVAS,
    'import reportlab\nreportlab.pdfgen.canvas.Canvas().save()',
    'import reportlab.pdfgen as p\np.canvas.Canvas()\nx.save()',
    'from reportlab.pdfgen import canvas as c\nc.Canvas()\nx.save()',
    'from reportlab import Canvas as C\nC()\nx.save()',
    'from reportlab.platypus import SimpleDocTemplate\nSimpleDocTemplate().build([])',
    'from reportlab.platypus import BaseDocTemplate as B\nB().build([])',
    'import reportlab.platypus as p\np.BaseDocTemplate().build([])',
    'import reportlab\nreportlab.platypus.SimpleDocTemplate().build([])',
    'from fpdf import FPDF\nFPDF().output()',
    'import fpdf as f\nf.FPDF().output()',
    'from fpdf2 import FPDF as F\nF().output()',
    'from weasyprint import HTML as H\nH().write_pdf()',
    'import weasyprint as w\nw.HTML().write_pdf()',
    'from pypdf import PdfWriter\nPdfWriter().write()',
    'from PyPDF2 import PdfFileWriter as W\nW().write()',
    'from PyPDF2 import PdfWriter\nPdfWriter().write()',
    'import pypdf as p\np.PdfWriter().write()',
    'import PyPDF2\nPyPDF2.PdfFileWriter().write()',
    'import fitz\nfitz.open().save()',
    'import fitz as f\nf.Document().save()',
    'from fitz import open as op\nop().save()',
    'from fitz import Document as D\nD().save()',
    'from xhtml2pdf import pisa\npisa.CreatePDF("html")',
    'import xhtml2pdf\nxhtml2pdf.pisa.CreatePDF("html")',
    'import xhtml2pdf.pisa as p\np.CreatePDF("html")',
    'from xhtml2pdf.pisa import CreatePDF as C\nC("html")',
]
BAD = [
    'from reportlab.pdfgen.canvas import Canvas\nCanvas()',
    'from reportlab.platypus import SimpleDocTemplate\nSimpleDocTemplate()',
    'from reportlab.platypus import BaseDocTemplate\nBaseDocTemplate()',
    'from fpdf import FPDF\nFPDF()',
    'from weasyprint import HTML\nHTML()',
    'from pypdf import PdfWriter\nPdfWriter()',
    'from PyPDF2 import PdfFileWriter\nPdfFileWriter()',
    'import fitz\nfitz.open()', 'import fitz\nfitz.Document()',
    'from pypdf import PdfReader\nPdfReader("x.pdf")',
    'from PyPDF2 import PdfReader\nPdfReader("x.pdf")',
    'import pdfplumber\npdfplumber.open("x.pdf").pages[0].extract_text()',
    'import fitz\nfitz.open("x.pdf")[0].extract_text()',
    'from pdfminer.high_level import extract_text\nextract_text("x.pdf")',
    'import camelot\ncamelot.read_pdf("x.pdf")',
    'import tabula\ntabula.read_pdf("x.pdf")',
    'import tabula\ntabula.convert_into("x.pdf", "x.csv")',
    'x.extract_table()', 'x.extract_tables()',
    'import pytesseract\npytesseract.image_to_string(x)',
    'print("PDF")', 'open("x.txt", "w").write("text")',
    'from pathlib import Path\nPath("x.html").write_text("html")',
    'from PIL import Image\nImage.new("RGB", (1,1)).save("x.png")',
    'import pdfkit\npdfkit.from_string("html", "x.pdf")',
    'import pdfkit\npdfkit.from_file("x.html", "x.pdf")',
    'import pdfkit\npdfkit.from_url("local", "x.pdf")',
    'import subprocess\nsubprocess.run(["wkhtmltopdf", "x.html", "x.pdf"])',
    'from matplotlib.backends.backend_pdf import PdfPages\nPdfPages("x.pdf")',
    'import matplotlib.pyplot as plt\nplt.savefig("x.pdf")',
    'import borb\nborb.PDF.dumps(x,y)', 'import pikepdf\npikepdf.open("x.pdf").save("y.pdf")',
    'import pdfrw\npdfrw.PdfWriter().write("x.pdf")',
    'x = "PDF"', '# generate pdf\nx = "generate pdf"',
    'client.parse(InvoiceV4, x)', 'client.begin_analyze_document("prebuilt-layout", x)',
    'client.begin_analyze_document_from_url("prebuilt-read", x)',
    'import veryfi\nveryfi.Client()', 'documentai.process_document(x)',
    'documentai.batch_process_documents(x)', 'textract.analyze_document(x)',
    'eden.universal_ai(model_id="opaque")', 'LlamaParse().load_data(x)',
    'nanonets.OCR(model_id="opaque")', 'docsumo.upload(x)',
    'abbyy.process(x)', 'rossum.upload(x)', 'klippa.parse(x)', 'parseur.upload(x)', 'extend.process(x)',
    'generate_pdf()', 'from thing import generate_pdf\ndef generate_pdf(): pass\ngenerate_pdf()',
    'from thing import generate_pdf as g\ndef g(): pass\ng()',
    'class A:\n def generate_pdf(self): pass\nx.generate_pdf()',
    'from reportlab.pdfgen.canvas import Canvas\nclass Canvas: pass\nCanvas().save()',
    'import reportlab\nreportlab = other\nreportlab.Canvas().save()',
    'import fitz\nfitz: object = other\nfitz.open().save()',
    'import fitz\nwith something as fitz:\n fitz.open().save()',
    'import fitz\nasync def f():\n async with something as fitz:\n  fitz.open().save()',
    'from xhtml2pdf import pisa\ndef CreatePDF(): pass\npisa.CreatePDF()',
    'from reportlab.pdfgen.canvas import Canvas as C\ndef Canvas(): pass\nC().save()',
    'import random\nrandom.Canvas().save()', 'from random import Canvas\nCanvas().save()',
    'from thing import generate_pdf\ngenerate_pdf', 'def broken(:',
]
BAD += ['import ' + name for name in ('reportlab', 'fpdf', 'weasyprint', 'pypdf', 'PyPDF2', 'fitz', 'xhtml2pdf', 'pdfkit', 'matplotlib')]


def evidence_test(source, expected):
    def test(self):
        self.assertEqual(bool(module_evidence(source)), expected, source)
    return test


for index, source in enumerate(GOOD):
    setattr(AuditTests, 'test_route_%02d' % index, evidence_test(source, True))
for index, source in enumerate(BAD):
    setattr(AuditTests, 'test_reject_%02d' % index, evidence_test(source, False))
for index, name in enumerate(EXPECTED_GENERIC):
    for suffix, source, expected in (
        ('attribute', 'x.' + name + '()', True),
        ('import', 'from anything import ' + name + '\n' + name + '()', True),
        ('alias', 'from anything import ' + name + ' as g\ng()', True),
        ('bare', name + '()', False),
        ('shadow', 'class Local:\n def ' + name + '(self): pass\nx.' + name + '()', False),
    ):
        setattr(AuditTests, 'test_generic_%02d_%s' % (index, suffix), evidence_test(source, expected))


if __name__ == '__main__':
    unittest.main()
