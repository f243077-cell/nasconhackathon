FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /srv
COPY backend/requirements.txt /srv/requirements.txt
RUN pip install -r /srv/requirements.txt
COPY backend/app /srv/app
COPY tests /srv/tests
EXPOSE 8080
CMD ["sh", "-c", "python -m app.bootstrap && exec uvicorn app.main:app --host 0.0.0.0 --port 8080 --workers ${WEB_CONCURRENCY:-2} --no-access-log"]
