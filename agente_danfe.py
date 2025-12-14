import time
import re
import logging
import requests
import zipfile
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# ================= CONFIGURAÇÕES =================

HEADERS = {
    "X-CNPJ": "27469509000135"
}

API_URL = "https://danfe.maissistem.com.br/processar"
DOWNLOAD_URL = "https://danfe.maissistem.com.br/download"

PASTA_ENTRADA = Path.home() / "Downloads"
PASTA_SAIDA = Path("C:/Danfe")

PADRAO_NOME = re.compile(r"^arquivos-.*\.zip$", re.IGNORECASE)
PADRAO_REFERENCIA = re.compile(r"(19|20)\d{2}[-_]?(0[1-9]|1[0-2])")

TEMPO_ESPERA_COPIA = 2  # segundos

# ================= LOG =================

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)-8s | %(message)s"
)

# ================= FUNÇÕES =================

def aguardar_copia(caminho):
    tamanho_anterior = -1
    while True:
        tamanho_atual = caminho.stat().st_size
        if tamanho_atual == tamanho_anterior:
            return
        tamanho_anterior = tamanho_atual
        time.sleep(1)

def extrair_zip(zip_path, destino):
    logging.info("📂 Extraindo ZIP final...")
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(destino)

def processar_zip(caminho_zip):
    nome = caminho_zip.name
    logging.info(f"📄 Arquivo detectado: {nome}")

    if not PADRAO_NOME.match(nome):
        logging.info(f"⏭ Ignorado (nome inválido): {nome}")
        return

    match = PADRAO_REFERENCIA.search(nome)
    if not match:
        logging.warning(f"⚠️ Referência ano-mês não encontrada: {nome}")
        return

    referencia = match.group()
    logging.info(f"✅ Referência identificada: {referencia}")

    logging.info("📤 Enviando para API...")
    with open(caminho_zip, "rb") as f:
        response = requests.post(
            API_URL,
            headers=HEADERS,
            files={"arquivo": (nome, f, "application/zip")},
            timeout=300
        )

    logging.info(f"📡 Status HTTP: {response.status_code}")
    logging.debug(f"📨 Resposta completa: {response.text}")

    if response.status_code != 200:
        raise Exception("API retornou erro HTTP")

    dados = response.json()
    zip_final = dados.get("arquivo_zip")

    if not zip_final:
        raise Exception("API não retornou arquivo_zip")

    pasta_destino = PASTA_SAIDA / referencia
    pasta_destino.mkdir(parents=True, exist_ok=True)

    caminho_zip_final = pasta_destino / "DANFE-XML.zip"

    logging.info(f"📥 Baixando ZIP final: {zip_final}")
    r = requests.get(f"{DOWNLOAD_URL}/{zip_final}", timeout=300)
    with open(caminho_zip_final, "wb") as f:
        f.write(r.content)

    logging.info(f"💾 ZIP salvo em: {caminho_zip_final}")

    extrair_zip(caminho_zip_final, pasta_destino)

    logging.info(f"✅ Processamento concluído: {referencia}")

# ================= WATCHDOG =================

class MonitorHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return

        caminho = Path(event.src_path)

        if caminho.suffix.lower() != ".zip":
            return

        logging.info(f"📥 Novo arquivo detectado: {caminho}")

        logging.debug("⏳ Aguardando término da cópia...")
        aguardar_copia(caminho)

        try:
            processar_zip(caminho)
        except Exception as e:
            logging.error(f"❌ Erro ao processar {caminho.name}: {e}", exc_info=True)

# ================= MAIN =================

if __name__ == "__main__":
    logging.info("🚀 Agente DANFE iniciado e monitorando pasta")
    logging.info(f"📁 Pasta monitorada: {PASTA_ENTRADA}")

    observer = Observer()
    observer.schedule(MonitorHandler(), str(PASTA_ENTRADA), recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()

    observer.join()
