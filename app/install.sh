#!/bin/bash

# Atualiza o sistema
apt-get update

# Instala o Java
apt-get install -y default-jre

# Instala o Tesseract
apt-get install -y tesseract-ocr

# Instala as dependências do Python
pip install -r requirements.txt
