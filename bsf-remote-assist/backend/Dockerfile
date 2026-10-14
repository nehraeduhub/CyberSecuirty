FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN chmod +x entrypoint.sh && useradd --system --home /app bsf && mkdir -p /app/staticfiles && chown -R bsf /app/staticfiles
USER bsf
ENTRYPOINT ["/app/entrypoint.sh"]
