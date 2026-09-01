# Multi-stage: build wheels once, ship a slim non-root runtime.
FROM python:3.12-slim AS build
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DJANGO_ENV=prod
RUN useradd --system --uid 1000 --create-home app
WORKDIR /app
COPY --from=build /install /usr/local
COPY --chown=app:app . .
# collectstatic needs settings to import but not the DB or a real secret.
RUN DJANGO_ENV=dev python manage.py collectstatic --noinput && chown -R app:app staticfiles
USER app
EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", "--timeout", "30", \
     "--max-requests", "1000", "--max-requests-jitter", "100", \
     "--access-logfile", "-", "--error-logfile", "-"]
