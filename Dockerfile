FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONUTF8=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY emojigif ./emojigif
COPY main.py .
RUN useradd --create-home bot && mkdir /app/data && chown bot:bot /app/data
USER bot
CMD ["python", "main.py"]
