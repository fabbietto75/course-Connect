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

**Perché il database “non si aggiorna”:** l’app **non parte** (crash su `psycopg2` con Python **3.14**), quindi nessuna migrazione/schema viene applicata finché il processo non resta in esecuzione con **Python 3.11**.

Render (2026) usa **3.14.3** di default. Il file **`.python-version`** da solo non basta sempre: va impostato esplicitamente **`PYTHON_VERSION`**.

### Cosa fare (scegline una)

1. **Metodo consigliato (native Python)**  
   Dashboard del **Web Service** → **Environment** → aggiungi  
   **`PYTHON_VERSION`** = **`3.11.9`** (versione completa, obbligatoria).  
   Poi **Manual Deploy** → **Clear build cache** → **Deploy latest commit**.

2. **Blueprint**  
   Nel repo c’è **`render.yaml`** con `PYTHON_VERSION: 3.11.9`. Puoi collegare il Blueprint al repo oppure copiare `envVars` nel servizio esistente.

3. **Docker (alternativa sicura)**  
   Nel servizio imposta **Environment** = **Docker** e usa il **`Dockerfile`** in root (immagine `python:3.11`). Render ignora il runtime Python “native” e usa quello del container.

**Start Command** (native, non Docker): deve includere **`$PORT`**:

`gunicorn --chdir courseconnect-main --bind 0.0.0.0:$PORT app:app`

Non usare solo `gunicorn app:app` senza bind alla porta.

**Procfile** in root è già allineato al comando sopra (con `--chdir`).
