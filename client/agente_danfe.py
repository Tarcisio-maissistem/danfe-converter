import os
import sys
import time
import re
import zipfile
import shutil
import logging
import requests
import configparser
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import json

# ============================
# CONFIGURAÇÃO - Carregar .ini
# ============================

def get_base_dir():
    if getattr(sys, 'frozen', False):
        # Rodando como EXE
        return os.path.dirname(sys.executable)
    else:
        # Rodando como .py
        return os.path.dirname(os.path.abspath(__file__))

BASE_DIR = get_base_dir()
CONFIG_PATH = os.path.join(BASE_DIR, "config.ini")

if not os.path.exists(CONFIG_PATH):
    raise FileNotFoundError(f"❌ config.ini não encontrado em: {CONFIG_PATH}")

config = configparser.ConfigParser()
config.read(CONFIG_PATH, encoding="utf-8")

CNPJ = re.sub(r"\D", "", config.get("API", "cnpj"))
API_URL = config.get("API", "url_processar")
API_DOWNLOAD = config.get("API", "url_download")

PASTA_MONITORADA = config.get("PASTAS", "monitorar")
PASTA_SAIDA = config.get("PASTAS", "saida")

HEADERS = {"X-CNPJ": CNPJ}

# ============================
# LOGGING
# ============================
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "agente.log"), encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger("AGENTE-DANFE")

# ============================
# CONSTANTES
# ============================
REGEX_REFERENCIA = r"(19|20)\d{2}[-_]?(0[1-9]|1[0-2])"
STATUS_FILE = os.path.join(BASE_DIR, "status.json")

# ============================
# FUNÇÕES AUXILIARES
# ============================

def atualizar_status(status, detalhe=""):
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "status": status,
            "detalhe": detalhe,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }, f, ensure_ascii=False, indent=2)

def aguardar_copia(caminho, timeout=60):
    logger.debug("⏳ Aguardando término da cópia...")
    tamanho_anterior = -1
    inicio = time.time()

    while time.time() - inicio < timeout:
        tamanho = os.path.getsize(caminho)
        if tamanho == tamanho_anterior:
            return True
        tamanho_anterior = tamanho
        time.sleep(1)

    return False


def extrair_referencia(nome):
    match = re.search(REGEX_REFERENCIA, nome)
    return match.group(0).replace("_", "-") if match else None


def processar_zip(caminho_zip):
    nome = os.path.basename(caminho_zip)
    logger.info(f"📄 Arquivo detectado: {nome}")

    referencia = extrair_referencia(nome)
    if not referencia:
        logger.warning(f"⏭ Ignorado (nome inválido): {nome}")
        return

    logger.info(f"✅ Referência identificada: {referencia}")

    pasta_destino = os.path.join(PASTA_SAIDA, referencia)
    os.makedirs(pasta_destino, exist_ok=True)

    # ===============================
    # ENVIO PARA API
    # ===============================
    atualizar_status("PROCESSANDO", f"Enviando para API: {nome}")

    logger.info("📤 Enviando para API...")

    with open(caminho_zip, "rb") as f:
        response = requests.post(
            API_URL,
            headers=HEADERS,
            files={"arquivo": (nome, f, "application/zip")},
            timeout=600
        )

    logger.info(f"📡 Status HTTP: {response.status_code}")
    logger.debug(f"📨 Resposta: {response.text}")

    if response.status_code != 200:
        raise Exception("API retornou erro")

    dados = response.json()
    zip_saida = dados.get("arquivo_zip")

    if not zip_saida:
        raise Exception("Resposta da API inválida")

    # ===============================
    # DOWNLOAD DO ZIP FINAL
    # ===============================
    logger.info(f"📥 Baixando ZIP final: {zip_saida}")

    resp_zip = requests.get(
        f"{API_DOWNLOAD}/{zip_saida}",
        timeout=600
    )

    zip_local = os.path.join(pasta_destino, "DANFE-XML.zip")

    with open(zip_local, "wb") as f:
        f.write(resp_zip.content)

    logger.info(f"💾 ZIP salvo em: {zip_local}")

    # ===============================
    # EXTRAÇÃO
    # ===============================
    logger.info("📂 Extraindo XMLs e DANFEs...")

    with zipfile.ZipFile(zip_local, "r") as zip_ref:
        zip_ref.extractall(pasta_destino)

    # ===============================
    # LIMPEZA TOTAL
    # ===============================
    os.remove(zip_local)
    logger.info("🗑️ DANFE-XML.zip removido")

    os.remove(caminho_zip)
    logger.info("🗑️ Arquivo original removido")

    atualizar_status("CONCLUÍDO", f"Processamento concluído para {referencia}")

# ============================
# WATCHDOG
# ============================

class MonitorHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return

        caminho = event.src_path
        nome = os.path.basename(caminho).lower()

        if not nome.startswith("arquivos-") or not nome.endswith(".zip"):
            logger.debug(f"⏭ Ignorado: {nome}")
            return

        logger.info(f"📥 Novo arquivo detectado: {caminho}")

        if not aguardar_copia(caminho):
            logger.error("❌ Timeout ao aguardar cópia")
            return

        try:
            processar_zip(caminho)
        except Exception as e:
            logger.exception(f"❌ Erro ao processar {nome}: {e}")


# ============================
# MAIN
# ============================

if __name__ == "__main__":
    logger.info("🚀 Agente DANFE iniciado")
    logger.info(f"📁 Monitorando: {PASTA_MONITORADA}")
    logger.info(f"🔐 CNPJ configurado: {CNPJ}")

    observer = Observer()
    observer.schedule(MonitorHandler(), PASTA_MONITORADA, recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()

    observer.join()
