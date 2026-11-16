"""Read-only, module-local static claim analysis."""
import ast
import os
from pathlib import Path
import re

from .phrases import PDFGENERATION, NOPDFGENERATION, GENERIC_NAMES


def normalize(text):
    return ' '.join(text.lower().replace('’', "'").replace("n't", ' not').replace('-', ' ').split())


def matches(text, phrases):
    found = []
    for phrase in sorted(phrases, key=lambda p: (-len(p), p)):
        pattern = r'(?<!\w)' + re.escape(phrase) + r'(?!\w)'
        if re.search(pattern, text):
            found.append(phrase)
            text = re.sub(pattern, lambda m: ' ' * len(m.group()), text)
    return found, text


def paragraphs(text):
    lines = []
    fence = None
    for line in text.splitlines():
        if fence:
            if re.match(r'^ {0,3}' + re.escape(fence[0]) + '{' + str(fence[1]) + r',}\s*$', line):
                fence = None
            lines.append('')
            continue
        start = re.match(r'^ {0,3}(`{3,}|~{3,})', line)
        if start:
            fence = (start[1][0], len(start[1]))
            lines.append('')
        else:
            lines.append(line)
    return [normalize(p) for p in re.split(r'\n\s*\n', '\n'.join(lines)) if p.strip()]


# Attribute routes deliberately test the imported root, not object data flow.
ROUTES = (
    (('Canvas',), ('reportlab', 'reportlab.pdfgen', 'reportlab.pdfgen.canvas'),
     ('reportlab.Canvas', 'reportlab.pdfgen.canvas.Canvas'), 'save'),
    (('SimpleDocTemplate', 'BaseDocTemplate'), ('reportlab', 'reportlab.platypus'),
     ('reportlab.platypus.SimpleDocTemplate', 'reportlab.platypus.BaseDocTemplate'), 'build'),
    (('FPDF',), ('fpdf', 'fpdf2'), ('fpdf.FPDF', 'fpdf2.FPDF'), 'output'),
    (('HTML',), ('weasyprint',), ('weasyprint.HTML',), 'write_pdf'),
    (('PdfWriter', 'PdfFileWriter'), ('pypdf', 'PyPDF2'),
     ('pypdf.PdfWriter', 'PyPDF2.PdfWriter', 'PyPDF2.PdfFileWriter'), 'write'),
    (('open', 'Document'), ('fitz',), ('fitz.open', 'fitz.Document'), 'save'),
    (('CreatePDF',), ('xhtml2pdf', 'xhtml2pdf.pisa'), ('xhtml2pdf.pisa.CreatePDF',), None),
)


def module_evidence(source):
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []
    nodes = list(ast.walk(tree))
    imports = {}
    blocked = set()
    for node in nodes:
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports[alias.asname or alias.name.split('.')[0]] = alias.name if alias.asname else alias.name.split('.')[0]
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            for alias in node.names:
                imports[alias.asname or alias.name] = node.module + '.' + alias.name
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            blocked.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            blocked.add(node.id)
        elif isinstance(node, ast.arg):
            blocked.add(node.arg)
    imports = {k: v for k, v in imports.items() if k not in blocked}
    calls = [n for n in nodes if isinstance(n, ast.Call)]
    writes = {n.func.attr for n in calls if isinstance(n.func, ast.Attribute)}

    def root_binding(func):
        base = func.value
        while isinstance(base, ast.Attribute):
            base = base.value
        return imports.get(base.id) if isinstance(base, ast.Name) else None

    evidence = []
    for call in calls:
        func = call.func
        attr = func.attr if isinstance(func, ast.Attribute) else None
        resolved = imports.get(func.id) if isinstance(func, ast.Name) else None
        original = resolved.rsplit('.', 1)[-1] if resolved else None
        if ((attr in GENERIC_NAMES and attr not in blocked) or
                (original in GENERIC_NAMES and original not in blocked)):
            evidence.append({'line': call.lineno, 'route': 'generic'})
            continue
        for names, roots, fullnames, write in ROUTES:
            if write and write not in writes:
                continue
            if ((attr in names and attr not in blocked and root_binding(func) in roots) or
                    (resolved in fullnames and original not in blocked)):
                evidence.append({'line': call.lineno, 'route': names[0]})
                break
    return evidence


def audit(repo='.', ignore=(), fail_on='high'):
    root = Path(repo)
    if not root.is_dir() or root.is_symlink():
        raise OSError('Repository must be a readable, non-symlink directory')
    claims = {'positive': [], 'negative': []}
    production, tests = [], []
    prefixes = tuple(p.replace('\\', '/').removeprefix('./') for p in ignore)

    def ignored(relative):
        return any(relative.startswith(p) for p in prefixes)

    def walk_error(error):
        raise error

    for directory, dirs, files in os.walk(root, followlinks=False, onerror=walk_error):
        dirs[:] = sorted(d for d in dirs if not (Path(directory) / d).is_symlink()
                         and not ignored((Path(directory) / d).relative_to(root).as_posix()))
        for filename in sorted(files):
            path = Path(directory) / filename
            rel = path.relative_to(root)
            label = rel.as_posix()
            if path.is_symlink() or ignored(label):
                continue
            if label == 'README.md' or (path.suffix == '.md' and 'docs' in rel.parts[:-1]):
                for paragraph in paragraphs(path.read_text(encoding='utf-8')):
                    negative, remainder = matches(paragraph, NOPDFGENERATION)
                    positive, _ = matches(remainder, PDFGENERATION)
                    for kind, phrases in (('positive', positive), ('negative', negative)):
                        claims[kind].extend({'path': label, 'phrase': p} for p in phrases)
            if path.suffix != '.py' or set(rel.parts[:-1]) & {'fixtures', 'docs', 'examples'}:
                continue
            is_test = 'tests' in rel.parts[:-1] or filename.startswith('test_') or filename.endswith('_test.py')
            for evidence in module_evidence(path.read_text(encoding='utf-8')):
                evidence['path'] = label
                (tests if is_test else production).append(evidence)
    findings = []
    if claims['positive'] and not production:
        findings.append({'rule': 'documented-pdf-generation-claim-false',
                         'severity': 'MEDIUM' if tests else 'HIGH',
                         'message': 'Listed evidence exists only in tests.' if tests else 'No listed production evidence supports the claim.',
                         'locations': claims['positive']})
    if claims['negative'] and production:
        findings.append({'rule': 'documented-no-pdf-generation-claim-false', 'severity': 'HIGH',
                         'message': 'Listed production evidence contradicts the denial.',
                         'locations': claims['negative']})
    failed = any(f['severity'] == 'HIGH' or fail_on == 'medium' for f in findings)
    return {'verdict': 'FAIL' if failed else 'PASS', 'findings': findings,
            'claims': claims, 'production_evidence': production, 'test_evidence': tests}
