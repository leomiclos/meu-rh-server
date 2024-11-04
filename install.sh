#!/bin/bash

# Atualiza o sistema e instala o Java
apt-get update && apt-get install -y default-jre

# Instala as dependências do Python
pip install -r requirements.txt
