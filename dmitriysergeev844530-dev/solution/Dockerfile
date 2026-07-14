FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir \
    --trusted-host pypi.org \
    --trusted-host files.pythonhosted.org \
    -r requirements.txt

COPY main.py ./

ENV PORT=8080
EXPOSE 8080

CMD ["python", "-u", "main.py"]
