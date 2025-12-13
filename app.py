from flask import Flask, render_template, request, jsonify, send_file
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

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configurar CORS para produção
CORS(app, resources={
    r"/*": {
        "origins": "*",  # Em produção, aceita qualquer origem
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type"]
    }
})

app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

UPLOAD_FOLDER = '/tmp/uploads'
TEMP_OUTPUT = '/tmp/temp_output'

# Criar diretórios no /tmp (para ambiente Docker)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(TEMP_OUTPUT, exist_ok=True)

def limpar_nome_arquivo(nome):
    """Remove caracteres inválidos do nome do arquivo"""
    return re.sub(r'[<>:"/\\|?*]', '', nome)

def extrair_dados_xml(xml_path):
    """Extrai informações do destinatário do XML"""
    try:
        logger.info(f"📄 Extraindo dados do XML: {xml_path}")
        tree = ET.parse(xml_path)
        root = tree.getroot()
        
        ns = {'nfe': 'http://www.portalfiscal.inf.br/nfe'}
        
        dest = root.find('.//nfe:dest', ns)
        if dest is None:
            logger.warning(f"⚠️ Destinatário não encontrado em {xml_path}")
            return None, None, None
            
        nome_elem = dest.find('nfe:xNome', ns)
        cnpj_elem = dest.find('nfe:CNPJ', ns)
        cpf_elem = dest.find('nfe:CPF', ns)
        
        nome = nome_elem.text if nome_elem is not None else 'CLIENTE_DESCONHECIDO'
        documento = cnpj_elem.text if cnpj_elem is not None else (cpf_elem.text if cpf_elem is not None else '00000000000000')
        
        chave_elem = root.find('.//nfe:infNFe', ns)
        chave = chave_elem.get('Id', '').replace('NFe', '') if chave_elem is not None else os.path.basename(xml_path).replace('.xml', '')
        
        logger.info(f"✅ Dados extraídos: {nome} - {documento}")
        return limpar_nome_arquivo(nome), documento, chave
    except Exception as e:
        logger.error(f"❌ Erro ao processar XML {xml_path}: {str(e)}")
        logger.error(traceback.format_exc())
        return None, None, None

def processar_xml_para_danfe(xml_path, output_dir):
    """Converte XML em DANFE (PDF)"""
    try:
        logger.info(f"🔄 Processando: {xml_path}")
        
        nome_cliente, documento, chave = extrair_dados_xml(xml_path)
        
        if not nome_cliente or not documento:
            logger.error(f"❌ Falha ao extrair dados de {xml_path}")
            return False, "Erro ao extrair dados do XML"
        
        nome_pasta = f"{nome_cliente} - {documento}"
        pasta_cliente = os.path.join(output_dir, nome_pasta)
        os.makedirs(pasta_cliente, exist_ok=True)
        logger.info(f"📁 Pasta criada: {pasta_cliente}")
        
        xml_destino = os.path.join(pasta_cliente, f"{chave}.xml")
        shutil.copy2(xml_path, xml_destino)
        logger.info(f"📋 XML copiado: {xml_destino}")
        
        pdf_destino = os.path.join(pasta_cliente, f"{chave}.pdf")
        
        logger.info(f"🖨️ Gerando DANFE...")
        
        # Tentar diferentes encodings
        xml_content = None
        for encoding in ['utf-8', 'iso-8859-1', 'latin1', 'cp1252']:
            try:
                with open(xml_path, 'r', encoding=encoding) as f:
                    xml_content = f.read()
                logger.info(f"✅ XML lido com encoding: {encoding}")
                break
            except UnicodeDecodeError:
                continue
        
        if xml_content is None:
            with open(xml_path, 'rb') as f:
                xml_content = f.read().decode('utf-8', errors='ignore')
        
        danfe = Danfe(xml=xml_content)
        danfe.output(pdf_destino)
        logger.info(f"✅ DANFE gerado: {pdf_destino}")
        
        return True, f"Processado: {nome_cliente}"
    except Exception as e:
        logger.error(f"❌ Erro ao processar {xml_path}: {str(e)}")
        logger.error(traceback.format_exc())
        return False, f"Erro: {str(e)}"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/health')
def health():
    """Endpoint de health check"""
    return jsonify({'status': 'healthy'}), 200

@app.route('/processar', methods=['POST', 'OPTIONS'])
def processar():
    if request.method == 'OPTIONS':
        return '', 204
    
    logger.info("=" * 60)
    logger.info("🚀 INICIANDO PROCESSAMENTO")
    logger.info("=" * 60)
    
    if 'arquivo' not in request.files:
        logger.error("❌ Nenhum arquivo enviado")
        return jsonify({'erro': 'Nenhum arquivo enviado'}), 400
    
    arquivo = request.files['arquivo']
    
    if arquivo.filename == '':
        logger.error("❌ Nenhum arquivo selecionado")
        return jsonify({'erro': 'Nenhum arquivo selecionado'}), 400
    
    if not arquivo.filename.endswith('.zip'):
        logger.error("❌ Arquivo não é ZIP")
        return jsonify({'erro': 'Apenas arquivos ZIP são aceitos'}), 400
    
    logger.info(f"📦 Arquivo recebido: {arquivo.filename}")
    
    resultados = []
    total_processados = 0
    total_erros = 0
    
    try:
        import uuid
        temp_id = str(uuid.uuid4())[:8]
        temp_dir = os.path.join(UPLOAD_FOLDER, f'temp_{temp_id}')
        os.makedirs(temp_dir, exist_ok=True)
        
        zip_path = os.path.join(temp_dir, arquivo.filename)
        arquivo.save(zip_path)
        logger.info(f"💾 ZIP salvo em: {zip_path}")
        
        extract_dir = os.path.join(temp_dir, 'extracted')
        os.makedirs(extract_dir, exist_ok=True)
        
        logger.info(f"📂 Extraindo ZIP...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
        logger.info(f"✅ ZIP extraído em: {extract_dir}")
        
        pasta_danfe = os.path.join(extract_dir, 'DANFE-XML')
        os.makedirs(pasta_danfe, exist_ok=True)
        logger.info(f"📁 Pasta DANFE-XML criada: {pasta_danfe}")
        
        xml_count = 0
        for root, dirs, files in os.walk(extract_dir):
            for file in files:
                if file.endswith('.xml'):
                    xml_count += 1
                    xml_path = os.path.join(root, file)
                    logger.info(f"📄 Encontrado XML #{xml_count}: {file}")
                    
                    sucesso, mensagem = processar_xml_para_danfe(xml_path, pasta_danfe)
                    
                    if sucesso:
                        total_processados += 1
                        resultados.append({'tipo': 'sucesso', 'mensagem': mensagem})
                        logger.info(f"✅ Sucesso #{total_processados}")
                    else:
                        total_erros += 1
                        resultados.append({'tipo': 'erro', 'mensagem': f"{file}: {mensagem}"})
                        logger.error(f"❌ Erro #{total_erros}: {mensagem}")
        
        logger.info(f"📊 Total de XMLs encontrados: {xml_count}")
        
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
        file_path = os.path.join(TEMP_OUTPUT, filename)
        return send_file(file_path, as_attachment=True, download_name=filename)
    except Exception as e:
        return jsonify({'erro': f'Erro ao baixar arquivo: {str(e)}'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(
        debug=False,
        host='0.0.0.0',
        port=port,
        threaded=True
    )