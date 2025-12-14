# 🧾 DANFE Converter

Sistema web para conversão automática de XMLs de NF-e em DANFEs (PDFs), organizados por destinatário.

![Status](https://img.shields.io/badge/status-production--ready-success)
![Python](https://img.shields.io/badge/python-3.11-blue)
![Flask](https://img.shields.io/badge/flask-3.0.0-lightgrey)
![License](https://img.shields.io/badge/license-MIT-green)

## 🚀 Funcionalidades

- ✅ Upload de arquivo ZIP contendo múltiplos XMLs
- ✅ Conversão automática de XML para DANFE (PDF)
- ✅ Organização por destinatário (Nome + CNPJ/CPF)
- ✅ Download do resultado em ZIP organizado
- ✅ Interface web moderna e responsiva
- ✅ Processamento em lote (múltiplos XMLs)
- ✅ Suporte a diferentes encodings (UTF-8, ISO-8859-1, etc.)
- ✅ Logs detalhados do processamento
- ✅ Limpeza automática de arquivos temporários

## 🏗️ Tecnologias

- **Backend:** Flask 3.0 + Gunicorn
- **Processamento:** brazilfiscalreport 2.1.10
- **Frontend:** HTML5 + CSS3 + JavaScript Vanilla
- **Deploy:** Docker + Easypanel
- **Segurança:** CORS configurável, Zip Slip protection, Path Traversal protection

## 📋 Requisitos

- Python 3.11+
- Docker (para deploy em produção)
- 1GB RAM (mínimo recomendado)
- 2GB disco (para processamento de grandes lotes)

## 🛠️ Instalação Local

### 1. Clone o repositório
```bash
git clone https://github.com/SEU-USUARIO/danfe-converter.git
cd danfe-converter
```

### 2. Crie ambiente virtual
```bash
python -m venv venv
```

### 3. Ative o ambiente virtual

**Windows:**
```bash
venv\Scripts\activate
```

**Linux/Mac:**
```bash
source venv/bin/activate
```

### 4. Instale dependências
```bash
pip install -r requirements.txt
```

### 5. Execute a aplicação
```bash
python app.py
```

### 6. Acesse no navegador
```
http://localhost:5000
```

## 🐳 Deploy com Docker

### Build da imagem
```bash
docker build -t danfe-converter .
```

### Executar container
```bash
docker run -p 5000:5000 \
  -e ENVIRONMENT=production \
  -e ALLOWED_ORIGINS=https://seu-dominio.com \
  danfe-converter
```

## 🌐 Deploy no Easypanel

### 1. Preparar repositório
```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/SEU-USUARIO/danfe-converter.git
git push -u origin main
```

### 2. Configurar no Easypanel

1. Criar nova aplicação
2. Conectar ao GitHub
3. Selecionar repositório
4. Configurar variáveis de ambiente:
   ```
   ENVIRONMENT=production
   PORT=5000
   ALLOWED_ORIGINS=https://seu-dominio.com
   ```
5. Adicionar domínio
6. Deploy!

### 3. Configurar DNS

No seu provedor de DNS:
```
Tipo:  A
Nome:  danfe (ou subdomínio desejado)
Valor: [IP fornecido pelo Easypanel]
TTL:   300
```

## ⚙️ Configuração

### Variáveis de Ambiente

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `ENVIRONMENT` | `production` | Ambiente de execução |
| `PORT` | `5000` | Porta da aplicação |
| `ALLOWED_ORIGINS` | `*` | Origens permitidas no CORS |

### Exemplo `.env`
```bash
ENVIRONMENT=production
PORT=5000
ALLOWED_ORIGINS=https://danfe.exemplo.com,https://www.exemplo.com
```

## 📊 Uso

### 1. Preparar arquivos
- Coloque todos os XMLs de NF-e em uma pasta
- Compacte a pasta em formato ZIP

### 2. Upload
- Acesse a aplicação no navegador
- Clique ou arraste o arquivo ZIP para a área de upload
- Clique em "Processar Arquivos"

### 3. Aguardar processamento
- O sistema irá processar todos os XMLs
- Mostrará progresso em tempo real
- Exibirá total de sucessos e erros

### 4. Download
- Clique em "Baixar DANFE-XML.zip"
- O arquivo conterá:
  ```
  DANFE-XML/
  ├── EMPRESA A - 12345678000190/
  │   ├── 52251127469509000134550030000000901773489407.xml
  │   └── 52251127469509000134550030000000901773489407.pdf
  ├── EMPRESA B - 98765432000100/
  │   ├── 52251127469509000134550030000000911807789782.xml
  │   └── 52251127469509000134550030000000911807789782.pdf
  └── ...
  ```

## 🔒 Segurança

### Medidas Implementadas

- ✅ **Zip Slip Protection:** Validação de caminhos de arquivos
- ✅ **Path Traversal Protection:** Sanitização de nomes de arquivo
- ✅ **CORS Configurável:** Restrição de origens permitidas
- ✅ **File Size Limit:** Máximo de 500MB por upload
- ✅ **Timeout Protection:** 10 minutos de timeout por requisição
- ✅ **Auto-cleanup:** Remoção automática de arquivos temporários

### Vulnerabilidades Corrigidas

| CVE | Descrição | Status |
|-----|-----------|--------|
| CVE-2018-1000117 | Zip Slip (Path Traversal) | ✅ Corrigida |
| - | Path Traversal no Download | ✅ Corrigida |
| - | CORS Aberto | ✅ Configurável |
| - | Filename Injection | ✅ Sanitização |

## 📈 Performance

### Capacidade

- **Workers:** 2
- **Threads por Worker:** 4
- **Conexões Simultâneas:** 8
- **Timeout:** 600 segundos
- **Max File Size:** 500MB

### Benchmark

- **100 XMLs:** ~30 segundos
- **500 XMLs:** ~2 minutos
- **1000 XMLs:** ~4 minutos

*Tempos variam conforme complexidade dos XMLs e recursos do servidor*

## 🐛 Troubleshooting

### Erro: "Erro ao extrair dados do XML"
- **Causa:** XML de cancelamento ou formato inválido
- **Solução:** Remova XMLs de cancelamento (começam com `canc_`)

### Erro: "Arquivo ZIP contém caminhos inválidos"
- **Causa:** Tentativa de Zip Slip attack
- **Solução:** Arquivo malicioso detectado, não processar

### Upload lento
- **Causa:** Arquivo muito grande ou conexão lenta
- **Solução:** Dividir em lotes menores ou aumentar timeout

### Processamento falha
- **Causa:** Memória insuficiente
- **Solução:** Aumentar RAM do container para 2GB

## 📝 Logs

### Formato
```
2025-12-13 14:30:45 | INFO     | __main__ | 🚀 INICIANDO PROCESSAMENTO
2025-12-13 14:30:46 | INFO     | __main__ | 📦 Arquivo recebido: notas.zip
2025-12-13 14:30:47 | INFO     | __main__ | 📊 Processados 10 XMLs...
2025-12-13 14:30:50 | INFO     | __main__ | ✅ PROCESSAMENTO CONCLUÍDO!
```

### Níveis de Log

- `INFO`: Operações normais
- `WARNING`: Situações não críticas
- `ERROR`: Erros no processamento
- `DEBUG`: Detalhes técnicos (apenas dev)

## 🧪 Testes

### Health Check
```bash
curl https://seu-dominio.com/health
```

**Resposta esperada:**
```json
{
  "status": "ok",
  "timestamp": "2025-12-13T14:30:45.123456",
  "environment": "production"
}
```

## 🤝 Contribuindo

1. Fork o projeto
2. Crie uma branch para sua feature (`git checkout -b feature/MinhaFeature`)
3. Commit suas mudanças (`git commit -m 'Adiciona MinhaFeature'`)
4. Push para a branch (`git push origin feature/MinhaFeature`)
5. Abra um Pull Request

## 📄 Licença

Este projeto está sob a licença MIT. Veja o arquivo [LICENSE](LICENSE) para mais detalhes.

## 👨‍💻 Autor

Mais Sistem - Desenvolvido com ❤️ para facilitar a gestão de notas fiscais eletrônicas.

## 📞 Suporte

- **Issues:** https://github.com/Tarcisio-maissistem/danfe-converter/issues
- **Email:** maissistem@gmail.com
- **Website:** https://maissistem.com.br

## 🎯 Roadmap

- [ ] Autenticação de usuários
- [ ] API REST para integração
- [ ] Processamento em background (Celery)
- [ ] Suporte a NFS-e
- [ ] Dashboard de estatísticas
- [ ] Armazenamento em nuvem (S3)
- [ ] Notificações por email
- [ ] Rate limiting por usuário

## ⭐ Agradecimentos

- [brazilfiscalreport](https://github.com/Engenere/BrazilFiscalReport) - Biblioteca para geração de DANFEs
- [Flask](https://flask.palletsprojects.com/) - Framework web
- [Gunicorn](https://gunicorn.org/) - WSGI HTTP Server

---

Feito com ❤️ e ☕ no Brasil 🇧🇷