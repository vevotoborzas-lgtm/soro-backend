FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir email-validator==2.2.0

COPY . .

RUN python -c "import email_validator; print('email_validator OK')" && \
    python -c "from app.main import app; print('Import OK')"

RUN chmod +x startup.sh

EXPOSE 8000

CMD ["bash", "startup.sh"]
