# CourseConnect

Il codice dell’app vive in **`courseconnect-main/`** (coerente con il deploy su Render: `Procfile` in root usa `gunicorn --chdir courseconnect-main`).

**Sviluppo locale**

```bash
cd courseconnect-main
python -m venv .venv && source .venv/bin/activate   # opzionale
pip install -r requirements.txt
flask run   # oppure: python app.py se previsto dallo script
```

## Deploy su Render (Python)

Render usa **Python 3.14** di default: `psycopg2-binary` va in errore. Il repo include **`.python-version`** (`3.11.9`) e **`runtime.txt`** (`python-3.11.9`) nella root e in `courseconnect-main/`.

Se il deploy resta su 3.14: nel dashboard del servizio aggiungi la variabile d’ambiente **`PYTHON_VERSION`** = **`3.11.9`**, poi **Clear build cache** e ridistribuisci.

**Start Command** consigliato (porta obbligatoria):

`gunicorn --chdir courseconnect-main --bind 0.0.0.0:$PORT app:app`
