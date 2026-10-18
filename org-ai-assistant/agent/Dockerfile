FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV AI_EXAMPLES_FILE=/database/04_sample_questions.sql
CMD ["python", "ask.py", "--help"]
