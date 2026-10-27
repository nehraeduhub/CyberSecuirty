FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN chmod +x entrypoint.sh && useradd --system --home /app techguardinas && mkdir -p /app/staticfiles && chown -R techguardinas /app/staticfiles
USER techguardinas
ENTRYPOINT ["/app/entrypoint.sh"]
