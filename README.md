# Pdf_signer

A lightweight Flask web app to upload PDFs and apply a saved signature image programmatically.

**Live demo:** https://pdf-signer-fr52.onrender.com

## Features
- Upload PDF files and sign them with a stored signature image.
- Simple dashboard and admin upload templates included.
- Built with Flask and PyMuPDF (PyMuPDF used as `fitz`).

## Repo structure
```
Pdf_signer/
├─ app.py
├─ requirements.txt
├─ Procfile
├─ templates/
│  ├─ index.html
│  ├─ login.html
│  └─ ... (other templates)
├─ static/
│  └─ signature.png
├─ uploads/
├─ signed/
└─ requests.db
```

## Run locally
1. Create and activate a Python venv:
```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run locally:
```bash
# for development
python app.py

# or run with gunicorn (mirrors production)
gunicorn app:app --bind 0.0.0.0:5000
```

4. Open http://127.0.0.1:5000 in your browser.

## Deployment
This repo is deployable to Render.com (used here). Use a `Procfile`:
```
web: gunicorn app:app --bind 0.0.0.0:$PORT
```

Make sure `requirements.txt` includes all needed packages (Flask, gunicorn, PyMuPDF, ...).

## Notes & Recommendations
- **Ephemeral filesystem:** Free Render instances have ephemeral storage. For production, move uploads to S3 or a similar object storage and use a managed DB (Postgres).
- **Secrets:** Use environment variables (set in Render) for any API keys / secrets. Don’t commit secrets to Git.
- **Security:** Validate uploaded filenames and file types. Limit upload size.

## Contact
Mahi Gupta — GitHub: [@mahigupta4002](https://github.com/mahigupta4002)
