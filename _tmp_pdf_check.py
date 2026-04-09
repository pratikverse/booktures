import pdfplumber
from pypdf import PdfReader
path = 'backend/storage/pdfs/bdc2bb89-c2ca-4fac-817c-a5c6e876b9a4_houn.pdf'
print('Using pdfplumber')
with pdfplumber.open(path) as pdf:
    for idx in [0,1,2,4,5,9,19]:
        text = pdf.pages[idx].extract_text(layout=True, x_tolerance=1, y_tolerance=1) or pdf.pages[idx].extract_text() or ''
        text = ' '.join(text.split())
        print(f'PLUMBER PAGE {idx+1}: {text[:500]}')
print('Using pypdf')
reader = PdfReader(path)
for idx in [0,1,2,4,5,9,19]:
    text = (reader.pages[idx].extract_text() or '').replace('\n',' ')
    text = ' '.join(text.split())
    print(f'PYPDF PAGE {idx+1}: {text[:500]}')
