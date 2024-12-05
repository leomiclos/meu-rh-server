FROM python:3.9-slim

# Instalar dependências do sistema, incluindo o Java, Tesseract e bibliotecas gráficas necessárias para o OpenCV
RUN apt-get update && \
    apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-por \
    openjdk-17-jre-headless \
    libgl1 && \
    apt-get clean


# Copiar e instalar dependências do Python
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Configurar o diretório de trabalho
WORKDIR /app

# Copiar o código fonte para o contêiner
COPY . /app


CMD ["python", "server.py"]
