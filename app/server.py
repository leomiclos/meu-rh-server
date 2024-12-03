# 1. Importações do sistema e utilitários gerais
import os
import re
from datetime import datetime
from io import BytesIO

# 2. Bibliotecas de processamento de imagens e OCR
import cv2
import numpy as np
from PIL import Image
import pytesseract as pt
from pdf2image import convert_from_path

# 3. Frameworks e ferramentas para APIs
from flask import Flask, request, jsonify, Response, send_from_directory
from flask_cors import CORS

# 4. Banco de dados e manipulação de objetos BSON
from pymongo import MongoClient
from bson import ObjectId

# 5. Segurança e validação
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# 6. Manipulação de texto
from spellchecker import SpellChecker

# 7. Codificação e manipulação de arquivos
import base64
import io

# Configuração do pytesseract
tesseract_path = '/usr/bin/tesseract'
# tesseract_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if os.path.exists(tesseract_path):
    pt.pytesseract.tesseract_cmd = tesseract_path
    print(f"Tesseract configurado com sucesso para: {tesseract_path}")
else:
    print(f"Erro: Não foi possível encontrar Tesseract em {tesseract_path}")

    
# Inicializa o SpellChecker para português
spell = SpellChecker(language='pt')

# Configuração do MongoDB
uri = "mongodb+srv://leonardormiclos:leonardo2024@meurh.wddun.mongodb.net/?retryWrites=true&w=majority&appName=meuRH"
client = MongoClient(uri)

# Confirmação de conexão com o MongoDB
try:
    client.admin.command('ping')
    print("Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    print(f"Erro ao conectar ao MongoDB: {e}")

db = client['meuRH']  # Nome do banco de dados
certificates_collection = db['certificates']  # Coleção de certificados
funcionarios = db['funcionarios']

# Flask Configuration
app = Flask(__name__)
CORS(app)  # Permite requisições CORS

# Diretório onde as imagens e os resultados processados serão salvos
SAVE_DIR = 'C:/Users/leomi/OneDrive/Área de Trabalho/Faculdade Leo/aplicativo-tcc/img'
if not os.path.exists(SAVE_DIR):
    os.makedirs(SAVE_DIR)

def compress_image(photo):
    try:
        # Abrir a imagem
        image = Image.open(photo)
        
        # Converte para RGB se for PNG ou outro formato
        image = image.convert('RGB')
        
        # Salvar a imagem comprimida em um buffer de memória
        output_io = io.BytesIO()
        image.save(output_io, format='JPEG', quality=85)  # Ajuste de qualidade (85% de compressão)
        output_io.seek(0)
        
        return output_io.read()  # Retorna os dados binários da imagem comprimida
    
    except Exception as e:
        print(f"Erro ao comprimir imagem: {str(e)}")
        raise ValueError("Erro ao processar a imagem.")


@app.route('/extract-text', methods=['POST'])
def extract_text():
    if 'image' not in request.files:
        return jsonify({"error": "Insira uma imagem"}), 400

    file = request.files['image']
    user_id = request.form['user_id']
    user_name = request.form['user_name']  # O nome do usuário será enviado diretamente pelo front-end

    file_extension = file.filename.split('.')[-1].lower()

    print(f"Recebendo arquivo: {file.filename}, extensão: {file_extension}, usuário: {user_name}")

    # Processamento da imagem para melhor qualidade
    def preprocess_image(image):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)  # Converte para escala de cinza
        gray = cv2.medianBlur(gray, 3)  # Aplica um filtro de mediana para remover ruídos
        return gray

    if file_extension in ['jpg', 'jpeg', 'png']:
        img_array = np.frombuffer(file.read(), np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        processed_img = preprocess_image(img)
        text = pt.image_to_string(processed_img, lang='por', config='--psm 6')

    elif file_extension == 'pdf':
        images = convert_from_path(BytesIO(file.read()))
        text = ''
        for image in images:
            processed_img = preprocess_image(np.array(image))
            text += pt.image_to_string(processed_img, lang='por', config='--psm 6') + ' '

    else:
        return jsonify({"error": "Formato de arquivo não suportado"}), 400

    # Corrigir a formatação do texto extraído
    text = text.replace('\n', ' ').replace('\r', '')  # Remove quebras de linha

    course_name = extract_course_name(text)  # Extrai o nome do curso
    date = extract_date(text)
    duration = extract_duration_or_calculate(text)

    # Dados do certificado
    certificate_data = {
        "user_id": user_id,  # Salva o ID do usuário
        "user_name": user_name,  # Salva o nome do usuário enviado pelo front-end
        "course_name": course_name,
        "date": date,
        "duration": duration,
        "extracted_text": text,
    }

    try:
        # Inserir o novo certificado no banco de dados
        result = certificates_collection.insert_one(certificate_data)
        print(f"Certificado salvo com ID: {result.inserted_id}")

        return jsonify({
            "user_name": user_name,
            "course_name": course_name,
            "date": date,
            "duration": duration,
            "extracted_text": text,
            "message": "Certificado salvo com sucesso!"
        }), 201

    except Exception as e:
        return jsonify({"error": f"Erro ao salvar certificado: {str(e)}"}), 500


def extract_course_name(text):
    # Tenta primeiro capturar texto entre aspas (incluindo casos com números no início)
    course_name = extract_course_name_from_quotes(text)
    if course_name:
        return course_name

    # Captura com base em palavras-chave e permite numerais no início
    match = re.search(
        r'(curso|treinamento|workshop|palestra|seminário|evento)\s*(?:“|")?[\dºª]*\s*[^0-9“"]+',
        text,
        re.IGNORECASE
    )
    if match:
        course_name = match.group(0).strip()
        # Remove sufixos irrelevantes e limpa o nome do curso
        course_name = re.sub(r' -.*| promovido.*| patrocínio.*| apoio.*| realizado.*| com.*', '', course_name)
        return course_name
    
    return None


def extract_course_name_from_quotes(text):
    # Expressão regular para encontrar texto entre aspas (e números no início)
    quotes_pattern = r'“([^“”]+)”|\"([^"]+)\"'

    # Encontra todas as ocorrências de texto entre aspas
    matches = re.findall(quotes_pattern, text)
    
    # Processa os textos encontrados entre aspas
    for match in matches:
        match_clean = ''.join(match).strip()  # Combina grupos e limpa espaços
        if len(match_clean.split()) > 1:  # Certifica que o nome do curso tem mais de uma palavra
            return match_clean
    
    return None


def is_course_name(text):
    # Função para verificar se o texto tem uma estrutura que possa ser um nome de curso
    # Aqui você pode adicionar mais lógica para verificar a plausibilidade do nome do curso
    # Por exemplo, um nome de curso normalmente é mais longo, tem mais de uma palavra, etc.
    if len(text.split()) > 1:  # Um nome de curso geralmente tem mais de uma palavra
        return True
    return False


def extract_date(text):
    # Ajuste para capturar várias formas de data, incluindo separadores diferentes
    match = re.search(r'(\d{2}[/-]\d{2}[/-]\d{4}|\d{4})', text)
    if match:
        return match.group(0)  # Retorna a data encontrada
    return None

def extract_duration_or_calculate(text):
    # Tenta encontrar a duração mencionada diretamente
    duration_match = re.search(r'(\d+\s*(horas?|h|minutos?|m))', text, re.IGNORECASE)
    if duration_match:
        return duration_match.group(0)
    
    # Extrai as datas de início e fim do período para calcular a duração em horas
    date_range_match = re.search(r'(\d{2}[/-]\d{2}[/-]\d{4})\s*[aà]\s*(\d{2}[/-]\d{2}[/-]\d{4})', text)
    if date_range_match:
        start_date_str, end_date_str = date_range_match.groups()
        try:
            start_date = datetime.strptime(start_date_str, '%d/%m/%Y')
            end_date = datetime.strptime(end_date_str, '%d/%m/%Y')
            # Calcula a diferença em dias e assume 8 horas por dia
            days_difference = (end_date - start_date).days + 1
            hours = days_difference * 8  # Ajuste o valor 8 para a carga horária padrão desejada
            return f"{hours} horas (calculadas)"
        except ValueError:
            return None
    return None


@app.route('/helloworld', methods=['GET'])
def verifyIsOn():
    return "API Online"

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


# Função para listar certificados por ID de usuário
@app.route('/certificados/funcionario/<string:funcionario_id>', methods=['GET'])
def listar_certificados_por_funcionario(funcionario_id):
    try:
        certificados = list(db.certificados.find({'funcionario_id': ObjectId(funcionario_id)}, {'_id': 0}))  # Filtra por funcionario_id
        if certificados:
            return jsonify(certificados), 200
        return jsonify({'error': 'Nenhum certificado encontrado para este funcionário.'}), 404
    except Exception as e:
        return jsonify({'error': f'Erro ao obter certificados: {str(e)}'}), 500


# Função para editar um certificado
@app.route('/certificados/<string:id>', methods=['PUT'])
def editar_certificado(id):
    data = request.json  # Dados para atualização
    
    # Atualizando o certificado
    try:
        result = db.certificados.update_one(
            {'_id': ObjectId(id)},  # Filtra pelo id do certificado
            {'$set': data}  # Atualiza os dados
        )
        
        if result.matched_count > 0:
            return jsonify({'message': 'Certificado atualizado com sucesso'}), 200
        else:
            return jsonify({'error': 'Certificado não encontrado'}), 404
    except Exception as e:
        return jsonify({'error': f'Erro ao atualizar certificado: {str(e)}'}), 500


@app.route('/certificados', methods=['GET'])
def listar_certificados():
    try:
        # Busca todos os certificados na coleção 'certificates'
        certificates = list(db.certificates.find())
        # Converte o campo '_id' para string
        for certificate in certificates:
            certificate['_id'] = str(certificate['_id'])
        return jsonify(certificates), 200  # Retorna a lista de certificados
    except Exception as e:
        return jsonify({'error': f'Erro ao obter certificados: {str(e)}'}), 500


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



# Diretório onde as imagens dos funcionários serão salvas
UPLOAD_FOLDER = 'C:/Users/leomi/OneDrive/Área de Trabalho/Faculdade Leo/aplicativo-tcc/meu-rh-servidor/img'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

# Função para verificar se a extensão da imagem é permitida
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Função para salvar a foto no diretório
def save_photo(photo):
    if photo and allowed_file(photo.filename):
        filename = secure_filename(photo.filename)  # Garante um nome seguro para o arquivo
        filepath = os.path.join(UPLOAD_FOLDER, filename)  # Caminho completo para o diretório
        photo.save(filepath)  # Salva a foto no diretório
        return filepath  # Retorna o caminho onde a foto foi salva
    return None  # Retorna None se o arquivo não for válido

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    
    usuario = data.get('usuario')
    senha = data.get('senha')
    
    if not usuario or not senha:
        return jsonify({'error': 'Nome de usuário e senha são obrigatórios.'}), 400

    try:
        funcionario = db.funcionarios.find_one({'usuario': usuario})

        if funcionario:
            if funcionario['senha'] == str(senha):
                funcionario.pop('senha', None) 
                funcionario.pop('photo', None) 
                funcionario = serialize(funcionario)
                return jsonify({'message': 'Login bem-sucedido!', 'funcionario': funcionario}), 200
            else:
                return jsonify({'error': 'Nome de usuário ou senha incorretos.'}), 401
        else:
            return jsonify({'error': 'Funcionário não encontrado.'}), 404
            
    except Exception as e:
        return jsonify({'error': f'Erro ao acessar o banco de dados: {str(e)}'}), 500


@app.route('/funcionarios', methods=['POST'])
def create_funcionario():
    data = request.json

    # Verificar se os campos obrigatórios estão presentes
    required_fields = ['nome', 'usuario', 'idade', 'email', 'tipo_funcionario']
    for field in required_fields:
        if field not in data:
            return jsonify({'error': f'Campo "{field}" é obrigatório.'}), 400

    # Verificar se o usuário já existe
    usuario_existente = db.funcionarios.find_one({'usuario': data.get('usuario')})
    if usuario_existente:
        return jsonify({'error': 'Usuário já existe.'}), 400

    # Recebe a foto do funcionário
    if 'photo' not in request.files:
        return jsonify({'error': 'Foto do funcionário é obrigatória.'}), 400

    photo = request.files['photo']
    photo_path = compress_hash_base64(photo)  # Salva a foto e obtém o caminho
    if not photo_path:
        return jsonify({'error': 'Formato de imagem inválido. Apenas PNG, JPG e JPEG são permitidos.'}), 400


    # Definir a senha como "12345" para todos os novos usuários
    senha = "12345"

    novo_funcionario = {
        "nome": data.get('nome'),
        "usuario": data.get('usuario'),
        "photo": photo_path,  # Salva o caminho da foto
        "idade": data.get('idade'),
        "senha": senha,
        "email": data.get('email'),
        "tipo_funcionario": data.get('tipo_funcionario'),
        "cargo": {
            "nome_cargo": data.get('cargo', {}).get('nome_cargo'),
            "salario": data.get('cargo', {}).get('salario')
        }
    }

    try:
        # Inserir o novo funcionário no banco de dados
        result = db.funcionarios.insert_one(novo_funcionario)
        return jsonify({'id': str(result.inserted_id)}), 201
    except Exception as e:
        # Em caso de erro na inserção
        return jsonify({'error': f'Erro ao criar funcionário: {str(e)}'}), 500

@app.route('/funcionarios/<string:usuario>/imagem', methods=['GET'])
def get_photo(usuario):
    # Buscar o funcionário pelo nome de usuário
    funcionario = db.funcionarios.find_one({'usuario': usuario}, {'_id': 0})  # Exclui o campo _id na resposta
    
    if funcionario:
        # Se o funcionário tem uma foto
        if 'photo' in funcionario and funcionario['photo']:
            photo_data = funcionario['photo']
            
            try:
                # Decodificar a imagem de base64 para binário
                photo_bytes = base64.b64decode(photo_data)
                
                # Verifique se a decodificação foi bem-sucedida
                if photo_bytes:
                    # Abrir a imagem a partir dos dados binários
                    image = Image.open(io.BytesIO(photo_bytes))

                    # Compactar a imagem
                    image = image.convert('RGB')  # Converte para RGB caso a imagem seja PNG ou outro formato
                    output_io = io.BytesIO()
                    image.save(output_io, format='JPEG', quality=85)  # Ajuste a qualidade da compressão conforme necessário
                    output_io.seek(0)

                    # Retornar a imagem compactada como binário
                    return Response(output_io.read(), mimetype='image/jpeg')  # Envia a imagem compactada diretamente como binário
                else:
                    raise ValueError("Erro ao decodificar a imagem base64.")
            except Exception as e:
                print("Erro ao processar a foto:", str(e))
                return jsonify({'error': 'Erro ao processar a foto'}), 500
        else:
            return jsonify({'error': 'Funcionário não tem foto'}), 404
    else:
        return jsonify({'error': 'Funcionário não encontrado'}), 404

@app.route('/funcionarios/<string:usuario>', methods=['GET'])
def get_funcionario(usuario):
    # Buscar o funcionário pelo nome de usuário
    funcionario = db.funcionarios.find_one({'usuario': usuario}, {'_id': 0, 'photo': 0})  # Exclui o campo _id e 'photo' na resposta
    
    if funcionario:
        return jsonify(funcionario), 200
    else:
        return jsonify({'error': 'Funcionário não encontrado'}), 404

@app.route('/funcionarios/<string:user_id>', methods=['GET'])
def get_funcionario_by_id(user_id):
    try:
        funcionario = funcionarios.find_one({"_id": ObjectId(user_id)})
        if funcionario:
            return jsonify(funcionario), 200
        else:
            return jsonify({'error': 'Funcionário não encontrado'}), 404
    except Exception as e:
        return jsonify({'error': f'Erro ao buscar funcionário: {str(e)}'}), 500  

@app.route('/funcionarios', methods=['GET'])
def get_funcionarios():
    # Buscar todos os funcionários, excluindo os campos 'photo'
    funcionarios = db.funcionarios.find({}, {'photo': 0})
    
    # Converter o cursor do MongoDB para uma lista e transformar ObjectId em string
    funcionarios_list = []
    for funcionario in funcionarios:
        funcionario['_id'] = str(funcionario['_id'])  # Converte o ObjectId para string
        funcionarios_list.append(funcionario)
    
    if funcionarios_list:
        return jsonify(funcionarios_list), 200
    else:
        return jsonify({'error': 'Nenhum funcionário encontrado'}), 404


@app.route('/funcionarios/<string:usuario>', methods=['PUT'])
def update_funcionario(usuario):
    # Buscar o funcionário pelo nome de usuário
    funcionario = db.funcionarios.find_one({'usuario': usuario})
    
    if not funcionario:
        return jsonify({'error': 'Funcionário não encontrado.'}), 404

    # Dados recebidos para atualização (usuário pode estar enviando um JSON)
    data = request.form  # Usando request.form para pegar dados de 'multipart/form-data'
    
    # Verificar se os campos obrigatórios para atualização estão presentes
    required_fields = ['nome', 'usuario', 'idade', 'email', 'tipo_funcionario']
    for field in required_fields:
        if field in data and data[field] == '':
            return jsonify({'error': f'Campo "{field}" não pode ser vazio.'}), 400

    # Atualizar os campos no banco de dados
    updated_data = {
        "nome": data.get('nome', funcionario['nome']),
        "usuario": data.get('usuario', funcionario['usuario']),
        "idade": data.get('idade', funcionario['idade']),
        "email": data.get('email', funcionario['email']),
        "tipo_funcionario": data.get('tipo_funcionario', funcionario['tipo_funcionario']),
        "cargo": {
            "nome_cargo": data.get('cargo', {}).get('nome_cargo', funcionario['cargo'].get('nome_cargo')),
            "salario": data.get('cargo', {}).get('salario', funcionario['cargo'].get('salario'))
        }
    }

    # Atualizar a foto, se fornecida
    if 'photo' in request.files:
        photo = request.files['photo']
        
        if isinstance(photo, FileStorage):  # Certificando-se de que o 'photo' é um arquivo válido
            try:
                # Comprimir a imagem recebida
                compressed_photo = compress_image(photo)

                # Converter a imagem comprimida para base64
                buffered = BytesIO(compressed_photo)
                img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')  # Converter para base64

                # Salvar o base64 da imagem no campo 'photo'
                updated_data["photo"] = img_base64
            except Exception as e:
                return jsonify({'error': f'Erro ao processar a foto: {str(e)}'}), 400
        else:
            return jsonify({'error': 'Formato de imagem inválido.'}), 400

    # Atualizar o funcionário no banco de dados
    try:
        db.funcionarios.update_one({'usuario': usuario}, {'$set': updated_data})
        return jsonify({'message': 'Funcionário atualizado com sucesso.'}), 200
    except Exception as e:
        return jsonify({'error': f'Erro ao atualizar funcionário: {str(e)}'}), 500


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



