# CourseConnect

Il codice dell’app vive in **`courseconnect-main/`** (coerente con il deploy su Render: `Procfile` in root usa `gunicorn --chdir courseconnect-main`).

**Sviluppo locale**

```bash
cd courseconnect-main
python -m venv .venv && source .venv/bin/activate   # opzionale
pip install -r requirements.txt
flask run   # oppure: python app.py se previsto dallo script
```
