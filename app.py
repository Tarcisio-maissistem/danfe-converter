from flask import Flask, render_template, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
import os
import zipfile
import shutil
from pathlib import Path
from brazilfiscalreport.danfe import Danfe
import xml.etree.ElementTree as ET
import re
import traceback
import logging
import sys
from datetime import datetime
import tempfile
from functools import wraps


# ========================================
# CONFIGURAÇÃO DE LOGGING PROFISSIONAL
# ========================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ========================================
# INICIALIZAÇÃO DA APLICAÇÃO
# ========================================
app = Flask(__name__)

# Configurar CORS com segurança
ALLOWED_ORIGINS = os.getenv('ALLOWED_ORIGINS', '*').split(',')
logger.info(f"🔒 CORS configurado para: {ALLOWED_ORIGINS}")

CORS(app, resources={
    r"/*": {
        "origins": ALLOWED_ORIGINS,
        "methods": ["GET", "POST", "OPTIONS", "DELETE"],
        "allow_headers": ["Content-Type"],
        "max_age": 3600
    }
})

# Configurações da aplicação
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 3600

# Usar /tmp em produção (Docker/Linux) ou pasta local em desenvolvimento
IS_PRODUCTION = os.getenv('ENVIRONMENT', 'production') == 'production'
UPLOAD_FOLDER = '/tmp/uploads' if IS_PRODUCTION else 'uploads'
TEMP_OUTPUT = '/tmp/temp_output' if IS_PRODUCTION else 'temp_output'

logger.info(f"🌍 Ambiente: {'PRODUÇÃO' if IS_PRODUCTION else 'DESENVOLVIMENTO'}")
logger.info(f"📁 Upload folder: {UPLOAD_FOLDER}")
logger.info(f"📁 Output folder: {TEMP_OUTPUT}")

# Tentar importar rarfile (biblioteca para .RAR)
try:
    import rarfile
    RAR_AVAILABLE = True
    logger.info("✅ Suporte para arquivos .RAR disponível")
except ImportError:
    RAR_AVAILABLE = False
    logger.warning("⚠️ rarfile não instalado - arquivos .RAR não serão suportados")
    logger.warning("   Para habilitar: pip install rarfile")

# ========================================
# FUNÇÕES AUXILIARES
# ========================================

def validar_cnpj_api(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        cnpj = request.headers.get("X-CNPJ")

        # Acesso via site (sem header) → permitido
        if not cnpj:
            return f(*args, **kwargs)

        cnpj = re.sub(r"\D", "", cnpj)

        if cnpj not in CNPJS_AUTORIZADOS:
            logger.warning(f"🚫 CNPJ não autorizado: {cnpj}")
            return jsonify({"erro": "CNPJ não autorizado"}), 403

        logger.info(f"🔐 Acesso autorizado para CNPJ: {cnpj}")
        return f(*args, **kwargs)

    return decorated

AUTHORIZED_CNPJS_FILE = "authorized_cnpjs.txt"

def carregar_cnpjs_autorizados():
    if not os.path.exists(AUTHORIZED_CNPJS_FILE):
        return set()

    cnpjs = set()
    with open(AUTHORIZED_CNPJS_FILE, "r") as f:
        for linha in f:
            cnpj = re.sub(r"\D", "", linha.strip())
            if len(cnpj) == 14:
                cnpjs.add(cnpj)

    logger.info(f"🔐 CNPJs autorizados carregados: {len(cnpjs)}")
    return cnpjs

CNPJS_AUTORIZADOS = carregar_cnpjs_autorizados()

def is_xml_nfe(xml_path):
    """
    Verifica se o XML é uma NFe válida.
    Ignora eventos, NFSe e outros XMLs fiscais.
    """
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()

        # Namespace padrão da NFe
        ns = {'nfe': 'http://www.portalfiscal.inf.br/nfe'}

        return root.find('.//nfe:infNFe', ns) is not None
    except Exception as e:
        logger.warning(f"⚠️ Erro ao validar tipo do XML {os.path.basename(xml_path)}: {str(e)}")
        return False


def is_valid_zip(path):
    """Verifica se o arquivo é um ZIP válido"""
    try:
        return zipfile.is_zipfile(path)
    except Exception:
        return False

def limpar_nome_arquivo(nome):
    """Remove caracteres inválidos do nome do arquivo"""
    return re.sub(r'[<>:"/\\|?*]', '', nome)

def sanitize_path(base_dir, filename):
    """
    Previne Zip Slip vulnerability
    Garante que o caminho extraído está dentro do diretório base
    """
    filepath = os.path.normpath(os.path.join(base_dir, filename))
    if not filepath.startswith(os.path.abspath(base_dir)):
        raise ValueError(f"⚠️ Caminho suspeito detectado: {filename}")
    return filepath

def safe_extract_zip(zip_path, extract_dir):
    """Extrai ZIP de forma segura, prevenindo Zip Slip"""
    logger.info(f"📂 Extraindo ZIP com validação de segurança...")
    
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        for member in zip_ref.namelist():
            target_path = sanitize_path(extract_dir, member)
            
            if member.endswith('/'):
                os.makedirs(target_path, exist_ok=True)
            else:
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                with zip_ref.open(member) as source, open(target_path, 'wb') as target:
                    shutil.copyfileobj(source, target)
    
    logger.info(f"✅ ZIP extraído com segurança em: {extract_dir}")

def safe_extract_rar(rar_path, extract_dir):
    """Extrai RAR de forma segura"""
    if not RAR_AVAILABLE:
        raise Exception("Suporte para RAR não disponível. Instale: pip install rarfile")
    
    logger.info(f"📂 Extraindo RAR com validação de segurança...")
    
    with rarfile.RarFile(rar_path, 'r') as rar_ref:
        for member in rar_ref.namelist():
            target_path = sanitize_path(extract_dir, member)
            
            if member.endswith('/') or member.endswith('\\'):
                os.makedirs(target_path, exist_ok=True)
            else:
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                with rar_ref.open(member) as source, open(target_path, 'wb') as target:
                    shutil.copyfileobj(source, target)
    
    logger.info(f"✅ RAR extraído com segurança em: {extract_dir}")

def extrair_dados_xml(xml_path):
    """Extrai informações do destinatário do XML"""
    try:
        logger.debug(f"📄 Extraindo dados do XML: {os.path.basename(xml_path)}")
        tree = ET.parse(xml_path)
        root = tree.getroot()
        
        ns = {'nfe': 'http://www.portalfiscal.inf.br/nfe'}
        
        dest = root.find('.//nfe:dest', ns)
        if dest is None:
            logger.warning(f"⚠️ Destinatário não encontrado em {os.path.basename(xml_path)}")
            return None, None, None
            
        nome_elem = dest.find('nfe:xNome', ns)
        cnpj_elem = dest.find('nfe:CNPJ', ns)
        cpf_elem = dest.find('nfe:CPF', ns)
        
        nome = nome_elem.text if nome_elem is not None else 'CLIENTE_DESCONHECIDO'
        documento = cnpj_elem.text if cnpj_elem is not None else (cpf_elem.text if cpf_elem is not None else '00000000000000')
        
        chave_elem = root.find('.//nfe:infNFe', ns)
        chave = chave_elem.get('Id', '').replace('NFe', '') if chave_elem is not None else os.path.basename(xml_path).replace('.xml', '')
        
        logger.debug(f"✅ Dados extraídos: {nome[:30]}... - {documento}")
        return limpar_nome_arquivo(nome), documento, chave
    except Exception as e:
        logger.error(f"❌ Erro ao processar XML {os.path.basename(xml_path)}: {str(e)}")
        return None, None, None

def processar_xml_para_danfe(xml_path, output_dir):
    """Converte XML em DANFE (PDF)"""
    try:
        nome_cliente, documento, chave = extrair_dados_xml(xml_path)
        
        if not nome_cliente or not documento:
            return False, "Erro ao extrair dados do XML"
        
        nome_pasta = f"{nome_cliente} - {documento}"
        pasta_cliente = os.path.join(output_dir, nome_pasta)
        os.makedirs(pasta_cliente, exist_ok=True)
        
        xml_destino = os.path.join(pasta_cliente, f"{chave}.xml")
        shutil.copy2(xml_path, xml_destino)
        
        pdf_destino = os.path.join(pasta_cliente, f"{chave}.pdf")
        
        # Tentar diferentes encodings
        xml_content = None
        for encoding in ['utf-8', 'iso-8859-1', 'latin1', 'cp1252']:
            try:
                with open(xml_path, 'r', encoding=encoding) as f:
                    xml_content = f.read()
                break
            except UnicodeDecodeError:
                continue
        
        if xml_content is None:
            with open(xml_path, 'rb') as f:
                xml_content = f.read().decode('utf-8', errors='ignore')
        
        danfe = Danfe(xml=xml_content)
        danfe.output(pdf_destino)
        
        return True, f"Processado: {nome_cliente}"
    except Exception as e:
        logger.error(f"❌ Erro ao processar {os.path.basename(xml_path)}: {str(e)}")
        return False, f"Erro: {str(e)}"

def cleanup_old_files():
    """Remove arquivos temporários antigos (mais de 1 hora)"""
    try:
        current_time = datetime.now().timestamp()
        
        for folder in [UPLOAD_FOLDER, TEMP_OUTPUT]:
            if not os.path.exists(folder):
                continue
                
            for item in os.listdir(folder):
                item_path = os.path.join(folder, item)
                
                if os.path.getmtime(item_path) < current_time - 3600:  # 1 hora
                    try:
                        if os.path.isdir(item_path):
                            shutil.rmtree(item_path)
                        else:
                            os.remove(item_path)
                        logger.debug(f"🧹 Removido arquivo antigo: {item}")
                    except Exception as e:
                        logger.warning(f"⚠️ Não foi possível remover {item}: {str(e)}")
    except Exception as e:
        logger.error(f"❌ Erro ao limpar arquivos antigos: {str(e)}")

# ========================================
# ROTAS DA APLICAÇÃO
# ========================================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/favicon.ico')
def favicon():
    """Rota explícita para favicon"""
    return send_from_directory(
        os.path.join(app.root_path, 'static'),
        'favicon.ico',
        mimetype='image/vnd.microsoft.icon'
    ) if os.path.exists(os.path.join(app.root_path, 'static', 'favicon.ico')) else ('', 204)

@app.route('/health')
def health():
    """Endpoint para verificar saúde da aplicação"""
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat(),
        'environment': 'production' if IS_PRODUCTION else 'development',
        'rar_support': RAR_AVAILABLE
    }), 200

@app.route('/processar', methods=['POST', 'OPTIONS'])
@validar_cnpj_api
def processar():
    if request.method == 'OPTIONS':
        return '', 204
    
    logger.info("=" * 60)
    logger.info("🚀 INICIANDO PROCESSAMENTO")
    logger.info("=" * 60)
    
    cleanup_old_files()
    
    # Aceitar múltiplos arquivos (novo) ou arquivo único (compatibilidade)
    arquivos = []
    if 'arquivos' in request.files:
        arquivos = request.files.getlist('arquivos')
    elif 'arquivo' in request.files:
        arquivos = [request.files['arquivo']]
    
    if not arquivos:
        logger.error("❌ Nenhum arquivo enviado")
        return jsonify({'erro': 'Nenhum arquivo enviado'}), 400
    
    if not arquivos or len(arquivos) == 0 or (len(arquivos) == 1 and arquivos[0].filename == ''):
        logger.error("❌ Nenhum arquivo selecionado")
        return jsonify({'erro': 'Nenhum arquivo selecionado'}), 400
    
    logger.info(f"📦 Arquivos recebidos: {len(arquivos)}")
    
    resultados = []
    total_processados = 0
    total_erros = 0
    
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(TEMP_OUTPUT, exist_ok=True)
    
    try:
        import uuid
        temp_id = str(uuid.uuid4())[:8]
        temp_dir = os.path.join(UPLOAD_FOLDER, f'temp_{temp_id}')
        os.makedirs(temp_dir, exist_ok=True)
        
        extract_dir = os.path.join(temp_dir, 'extracted')
        os.makedirs(extract_dir, exist_ok=True)
        
        # Processar cada arquivo enviado
        for arquivo in arquivos:
            if arquivo.filename == '':
                continue
            
            filename_lower = arquivo.filename.lower()
            logger.info(f"📄 Processando: {arquivo.filename}")
            
            # Se for XML direto, salvar na pasta de extração
            if filename_lower.endswith('.xml'):
                xml_path = os.path.join(extract_dir, limpar_nome_arquivo(arquivo.filename))
                arquivo.save(xml_path)
                logger.info(f"✅ XML salvo diretamente: {arquivo.filename}")
            
            # Se for ZIP, extrair
            elif filename_lower.endswith('.zip'):
                zip_path = os.path.join(temp_dir, limpar_nome_arquivo(arquivo.filename))
                arquivo.save(zip_path)
                logger.info(f"📦 ZIP salvo: {arquivo.filename}")

                # ✅ VALIDAÇÃO REAL DO ZIP (CORREÇÃO DO BUG)
                if not is_valid_zip(zip_path):
                    logger.error(f"❌ Arquivo não é um ZIP válido: {arquivo.filename}")
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    return jsonify({
                        'erro': f"O arquivo '{arquivo.filename}' não é um ZIP válido ou está corrompido."
                    }), 400
                safe_extract_zip(zip_path, extract_dir)

            
            # Se for RAR, extrair
            elif filename_lower.endswith('.rar'):
                if not RAR_AVAILABLE:
                    logger.error("❌ Suporte para RAR não disponível")
                    return jsonify({'erro': 'Suporte para arquivos .RAR não está instalado no servidor'}), 400
                
                rar_path = os.path.join(temp_dir, limpar_nome_arquivo(arquivo.filename))
                arquivo.save(rar_path)
                logger.info(f"📦 RAR salvo: {arquivo.filename}")
                safe_extract_rar(rar_path, extract_dir)
            
            else:
                logger.warning(f"⚠️ Arquivo ignorado (formato não suportado): {arquivo.filename}")
        
        # Processar todos os XMLs encontrados
        pasta_danfe = os.path.join(extract_dir, 'DANFE-XML')
        os.makedirs(pasta_danfe, exist_ok=True)
        logger.info(f"📁 Pasta DANFE-XML criada: {pasta_danfe}")
        
        xml_count = 0
        for root, dirs, files in os.walk(extract_dir):
            if 'DANFE-XML' in root:
                continue
            
            for file in files:
                if file.endswith('.xml'):
                    xml_path = os.path.join(root, file)

                    # ✅ Ignorar XML que não é NFe (eventos, NFSe, etc)
                    if not is_xml_nfe(xml_path):
                        logger.info(f"⏭️ XML ignorado (não é NFe): {file}")
                        continue

                    xml_count += 1

                    if xml_count % 10 == 0:
                        logger.info(f"📊 Processados {xml_count} XMLs...")

                    sucesso, mensagem = processar_xml_para_danfe(xml_path, pasta_danfe)

                    if sucesso:
                        total_processados += 1
                        resultados.append({'tipo': 'sucesso', 'mensagem': mensagem})
                    else:
                        total_erros += 1
                        resultados.append({'tipo': 'erro', 'mensagem': f"{file}: {mensagem}"})

        
        logger.info(f"📊 Total de XMLs encontrados: {xml_count}")
        
        if xml_count == 0:
            logger.error("❌ Nenhum arquivo XML encontrado")
            shutil.rmtree(temp_dir)
            return jsonify({'erro': 'Nenhum arquivo XML encontrado nos arquivos enviados'}), 400
        
        # Criar arquivo ZIP com os resultados
        zip_resultado = os.path.join(TEMP_OUTPUT, f'DANFE-XML_{temp_id}.zip')
        
        logger.info(f"📦 Criando ZIP final: {zip_resultado}")
        with zipfile.ZipFile(zip_resultado, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(pasta_danfe):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, extract_dir)
                    zipf.write(file_path, arcname)
        
        logger.info(f"✅ ZIP final criado com sucesso!")
        
        shutil.rmtree(temp_dir)
        logger.info(f"🧹 Arquivos temporários removidos")
        
        logger.info("=" * 60)
        logger.info(f"✅ PROCESSAMENTO CONCLUÍDO!")
        logger.info(f"   Processados: {total_processados}")
        logger.info(f"   Erros: {total_erros}")
        logger.info("=" * 60)
        
        return jsonify({
            'sucesso': True,
            'total_processados': total_processados,
            'total_erros': total_erros,
            'resultados': resultados,
            'arquivo_zip': os.path.basename(zip_resultado)
        })
        
    except ValueError as e:
        logger.error(f"🚨 TENTATIVA DE ATAQUE DETECTADA: {str(e)}")
        return jsonify({'erro': 'Arquivo contém caminhos inválidos'}), 400
    except Exception as e:
        logger.error("=" * 60)
        logger.error(f"❌ ERRO CRÍTICO NO PROCESSAMENTO")
        logger.error(f"❌ {str(e)}")
        logger.error(traceback.format_exc())
        logger.error("=" * 60)
        return jsonify({'erro': f'Erro ao processar: {str(e)}'}), 500

@app.route('/download/<filename>')
def download(filename):
    """Endpoint para download do arquivo ZIP processado"""
    try:
        safe_filename = os.path.basename(filename)
        file_path = os.path.join(TEMP_OUTPUT, safe_filename)
        
        if not os.path.exists(file_path):
            logger.error(f"❌ Arquivo não encontrado: {safe_filename}")
            return jsonify({'erro': 'Arquivo não encontrado'}), 404
        
        logger.info(f"⬇️ Download iniciado: {safe_filename}")
        
        return send_file(
            file_path,
            as_attachment=True,
            download_name='DANFE-XML.zip',
            max_age=0
        )
    except Exception as e:
        logger.error(f"❌ Erro ao baixar arquivo: {str(e)}")
        return jsonify({'erro': f'Erro ao baixar arquivo: {str(e)}'}), 500

# ========================================
# EXECUÇÃO DA APLICAÇÃO
# ========================================

if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("🚀 SISTEMA DANFE INICIADO!")
    logger.info("=" * 60)
    logger.info(f"🌍 Ambiente: {'PRODUÇÃO' if IS_PRODUCTION else 'DESENVOLVIMENTO'}")
    logger.info(f"🔒 CORS Origins: {ALLOWED_ORIGINS}")
    logger.info(f"📦 Suporte RAR: {'✅ SIM' if RAR_AVAILABLE else '❌ NÃO'}")
    logger.info("=" * 60)
    
    if IS_PRODUCTION:
        logger.warning("⚠️  Executando Flask dev server em produção!")
        logger.warning("⚠️  Use Gunicorn para produção: gunicorn app:app")
    
    app.run(
        debug=not IS_PRODUCTION,
        host='0.0.0.0',
        port=int(os.getenv('PORT', 5000)),
        threaded=True
    )