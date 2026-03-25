web: gunicorn --chdir courseconnect-main --bind 0.0.0.0:$PORT --workers 1 --worker-class gthread --threads 2 --timeout 300 --graceful-timeout 30 app:app
