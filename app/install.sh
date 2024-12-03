#!/bin/bash

# Atualiza o sistema
apt-get update

# Instala o Tesseract
apt-get install -y tesseract-ocr

# Instala as dependências do Python
pip install -r requirements.txt
