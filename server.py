import os
import re
from datetime import datetime
from io import BytesIO

import numpy as np
import pytesseract as pt
import cv2
from PIL import Image
from pdf2image import convert_from_path
from flask import Flask, request, jsonify
from flask_cors import CORS
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from werkzeug.security import generate_password_hash, check_password_hash
from bson import ObjectId
from spellchecker import SpellChecker

# Configuração do pytesseract
pt.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# Inicializa o SpellChecker para português
spell = SpellChecker(language='pt')

# Configuração do MongoDB
uri = "mongodb+srv://leonardormiclos:leonardo2024@meurh.wddun.mongodb.net/?retryWrites=true&w=majority&appName=meuRH"
client = MongoClient(uri, server_api=ServerApi('1'))

# Confirmação de conexão com o MongoDB
try:
    client.admin.command('ping')
    print("Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    print(f"Erro ao conectar ao MongoDB: {e}")

db = client['meuRH']  # Nome do banco de dados

app = Flask(__name__)
CORS(app)  # Permite requisições CORS

# Diretório onde as imagens e os resultados processados serão salvos
SAVE_DIR = 'C:/Users/leomi/OneDrive/Área de Trabalho/Faculdade Leo/aplicativo-tcc/img'
if not os.path.exists(SAVE_DIR):
    os.makedirs(SAVE_DIR)

@app.route('/extract-text', methods=['POST'])
def extract_text():
    if 'image' not in request.files:
        return jsonify({"error": "Nenhuma imagem foi enviada"}), 400

    file = request.files['image']
    file_extension = file.filename.split('.')[-1].lower()
    
    print(f"Recebendo arquivo: {file.filename}, extensão: {file_extension}")

    if file_extension in ['jpg', 'jpeg', 'png']:
        img_array = np.frombuffer(file.read(), np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        text = pt.image_to_string(img)

    elif file_extension == 'pdf':
        images = convert_from_path(BytesIO(file.read()))
        text = ''
        for image in images:
            text += pt.image_to_string(np.array(image)) + ' '

    else:
        return jsonify({"error": "Formato de arquivo não suportado"}), 400

    text = text.replace('\n', ' ')
    corrected_text = correct_spelling(text)

    words = corrected_text.split()
    words_objects = [{"word": word} for word in words]

    course_name = extract_course_name(corrected_text)
    training_name = extract_training_name(corrected_text)  
    date = extract_date(corrected_text)
    duration = extract_duration_or_calculate(corrected_text)

    return jsonify({
        "extracted_text": corrected_text,
        "words": words_objects,
        "course_name": course_name,
        "training_name": training_name,
        "date": date,
        "duration": duration
    })

def correct_spelling(text):
    words = text.split()
    misspelled = spell.unknown(words)

    for word in misspelled:
        corrected_word = spell.candidates(word)
        if corrected_word:
            text = text.replace(word, corrected_word.pop())

    return text

def extract_course_name(text):
    match = re.search(r'(curso\s*"?([\w\s]+)"?)', text, re.IGNORECASE)
    return match.group(2).strip() if match else None

def extract_training_name(text):
    match = re.search(r'(treinamento\s*"?([\w\s]+)"?)', text, re.IGNORECASE)
    return match.group(2).strip() if match else None

def extract_date(text):
    match = re.search(r'(\d{2}[/-]\d{2}[/-]\d{4}|\d{4})', text)
    return match.group(0) if match else None

def extract_duration_or_calculate(text):
    duration_match = re.search(r'(\d+\s*(horas?|h))', text, re.IGNORECASE)
    if duration_match:
        return duration_match.group(0)
    
    date_range_match = re.search(r'(\d{2}[/-]\d{2}[/-]\d{4})\s*[aà]\s*(\d{2}[/-]\d{2}[/-]\d{4})', text)
    if date_range_match:
        start_date_str, end_date_str = date_range_match.groups()
        try:
            start_date = datetime.strptime(start_date_str, '%d/%m/%Y')
            end_date = datetime.strptime(end_date_str, '%d/%m/%Y')
            days_difference = (end_date - start_date).days + 1
            hours = days_difference * 8  # Ajuste o valor 8 para a carga horária padrão desejada
            return f"{hours} horas (calculadas)"
        except ValueError:
            return None
    return None

@app.route('/helloworld', methods=['GET'])
def verifyIsOn():
    return "API Online"

def serialize(funcionario):
    return {
        'id': str(funcionario['_id']),
        'nome': funcionario.get('nome', ''),
        'usuario': funcionario.get('usuario', ''),
        'email': funcionario.get('email', ''),
        'idade': funcionario.get('idade', ''),
        'tipo_funcionario': funcionario.get('tipo_funcionario', ''),
        'cargo': {
            'nome_cargo': funcionario.get('cargo', {}).get('nome_cargo', ''),
            'salario': funcionario.get('cargo', {}).get('salario', '')
        },
        'photo': funcionario.get('photo', None)
    }

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    
    usuario = data.get('usuario')
    senha = data.get('senha')
    
    if not usuario or not senha:
        return jsonify({'error': 'Nome de usuário e senha são obrigatórios.'}), 400

    try:
        funcionario = db.funcionarios.find_one({'usuario': usuario})
        print(f"Funcionário encontrado: {funcionario}")

        if funcionario:
            if check_password_hash(funcionario['senha'], str(senha)):
                funcionario.pop('senha', None)
                funcionario = serialize(funcionario)
                return jsonify({'message': 'Login bem-sucedido!', 'funcionario': funcionario}), 200
            else:
                return jsonify({'error': 'Nome de usuário ou senha incorretos.'}), 401
        else:
            return jsonify({'error': 'Funcionário não encontrado.'}), 404
            
    except Exception as e:
        return jsonify({'error': f'Erro ao acessar o banco de dados: {str(e)}'}), 500

# Rotas CRUD para Funcionários
@app.route('/funcionarios', methods=['POST'])
def create_funcionario():
    data = request.json
    print(data)

    # Verificar se os campos obrigatórios estão presentes
    required_fields = ['nome', 'usuario', 'idade', 'email', 'tipo_funcionario']
    for field in required_fields:
        if field not in data:
            return jsonify({'error': f'Campo "{field}" é obrigatório.'}), 400

    # Verificar se o usuário já existe
    usuario_existente = db.funcionarios.find_one({'usuario': data.get('usuario')})
    if usuario_existente:
        return jsonify({'error': 'Usuário já existe.'}), 400

    # Definir a senha como "12345" para todos os novos usuários
    senha = "12345"
    senha_hash = generate_password_hash(senha)

    # Verificar o cargo
    nome_cargo = data.get('nomeCargo')
    cargo_salario = data.get('salario')

    # Definir valores padrão para cargo se não fornecidos
    if not nome_cargo:
        nome_cargo = "Não especificado"
    if cargo_salario is None:
        cargo_salario = 0  # Ou outro valor padrão que faça sentido

    novo_funcionario = {
        "nome": data.get('nome'),
        "usuario": data.get('usuario'),
        "photo": data.get('photo', None),  # Foto pode ser opcional
        "idade": data.get('idade'),
        "senha": senha_hash,
        "email": data.get('email'),
        "tipo_funcionario": data.get('tipo_funcionario'),
        "cargo": {
            "nome_cargo": nome_cargo,
            "salario": cargo_salario
        }
    }

    try:
        # Inserir o novo funcionário no banco de dados
        result = db.funcionarios.insert_one(novo_funcionario)
        return jsonify({'id': str(result.inserted_id)}), 201
    except Exception as e:
        # Em caso de erro na inserção
        return jsonify({'error': f'Erro ao criar funcionário: {str(e)}'}), 500


@app.route('/funcionarios', methods=['GET'])
def get_funcionarios():
    funcionarios = list(db.funcionarios.find({}, {'_id': 0}))
    return jsonify(funcionarios), 200

@app.route('/funcionarios/<string:nome>', methods=['GET'])
def get_funcionario(nome):
    funcionario = db.funcionarios.find_one({'nome': nome}, {'_id': 0})
    if funcionario:
        return jsonify(funcionario), 200
    return jsonify({'error': 'Funcionário não encontrado'}), 404

@app.route('/funcionarios/<string:usuario>', methods=['PUT'])
def update_funcionario(usuario):
    data = request.json
    result = db.funcionarios.update_one({'usuario': usuario}, {'$set': data})

    if result.matched_count > 0:
        return jsonify({'message': 'Funcionário atualizado com sucesso'}), 200
    
    return jsonify({'error': 'Funcionário não encontrado'}), 404

@app.route('/funcionarios/<string:nome>', methods=['DELETE'])
def delete_funcionario(nome):
    result = db.funcionarios.delete_one({'nome': nome})
    if result.deleted_count > 0:
        return jsonify({'message': 'Funcionário deletado com sucesso'}), 200
    return jsonify({'error': 'Funcionário não encontrado'}), 404

# Rotas CRUD para Certificados
@app.route('/certificados', methods=['POST'])
def create_certificado():
    data = request.json
    result = db.certificados.insert_one(data)
    return jsonify({'id': str(result.inserted_id)}), 201

@app.route('/certificados', methods=['GET'])
def get_certificados():
    certificados = list(db.certificados.find({}, {'_id': 0}))
    return jsonify(certificados), 200

@app.route('/certificados/<string:id>', methods=['GET'])
def get_certificado(id):
    certificado = db.certificados.find_one({'_id': ObjectId(id)}, {'_id': 0})
    if certificado:
        return jsonify(certificado), 200
    return jsonify({'error': 'Certificado não encontrado'}), 404

@app.route('/certificados/<string:id>', methods=['PUT'])
def update_certificado(id):
    data = request.json
    result = db.certificados.update_one({'_id': ObjectId(id)}, {'$set': data})

    if result.matched_count > 0:
        return jsonify({'message': 'Certificado atualizado com sucesso'}), 200
    
    return jsonify({'error': 'Certificado não encontrado'}), 404

@app.route('/certificados/<string:id>', methods=['DELETE'])
def delete_certificado(id):
    result = db.certificados.delete_one({'_id': ObjectId(id)})
    if result.deleted_count > 0:
        return jsonify({'message': 'Certificado deletado com sucesso'}), 200
    return jsonify({'error': 'Certificado não encontrado'}), 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
