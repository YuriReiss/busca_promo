import logging
import datetime
import threading
import asyncio
import os  # <-- A CORREÇÃO ESTÁ AQUI
from collections import deque

# --- Importações de API ---
import uvicorn
from fastapi import FastAPI

# --- Importações do Telegram ---
from telethon import TelegramClient, events # type: ignore
from telethon.sessions import StringSession # Importado para usar a sessão
from fastapi.middleware.cors import CORSMiddleware  # <-- 1. IMPORTAR O MIDDLEWARE

# --- Configuração ---
# 1. As credenciais agora vêm das "Variáveis de Ambiente" do servidor
API_ID_STR = os.environ.get('API_ID')
API_HASH = os.environ.get('API_HASH')

TELEGRAM_SESSION = os.environ.get('TELEGRAM_SESSION_STRING')

# Validação se as variáveis existem
if not API_ID_STR or not API_HASH or not TELEGRAM_SESSION:
    raise ValueError("API_ID, API_HASH, e TELEGRAM_SESSION_STRING devem ser definidos como variáveis de ambiente.")

# O API_ID precisa ser um inteiro
API_ID = int(API_ID_STR)

# 2. Lista de canais para monitorar (continua igual)
CANAL_ORIGEM = [
    "https://t.me/urubupromo",
    "https://t.me/pechinchou",
    "https://t.me/grupotempromo",
    "https://t.me/peguepromo",
    "https://t.me/+FrQHi-rbxbg4NDcx"
]

# 3. Não precisamos mais de SESSION_NAME
# SESSION_NAME = "minha_sessao_api" (Removido)

# 4. Armazenamento em memória (continua igual)
MAX_MENSAGENS = 100
messages_store = deque(maxlen=MAX_MENSAGENS)
# --------------------

# --- Parte 1: O Servidor da API (FastAPI) ---

# Cria a aplicação FastAPI (igual)
app = FastAPI(
    title="Telegram Monitor API",
    description="Uma API que expõe mensagens de canais do Telegram em tempo real.",
)

# Esta secção permite que qualquer website (origem) aceda à sua API.
app.add_middleware(
    CORSMiddleware, # type: ignore
    allow_origins=["*"],  # Permite todas as origens
    allow_credentials=True,
    allow_methods=["*"],  # Permite todos os métodos (GET, POST, etc.)
    allow_headers=["*"],  # Permite todos os cabeçalhos
)
# ----------------------------------------

@app.get("/", summary="Endpoint raiz")
def get_root():
    """Endpoint raiz para verificar se a API está online."""
    return {
        "status": "online",
        "monitoring_channels": CANAL_ORIGEM,
        "message_count": len(messages_store),
        "docs": "/docs"
    }

@app.get("/messages", summary="Obter as últimas mensagens")
def get_messages():
    """Retorna as últimas N mensagens coletadas dos canais."""
    return {"messages": list(messages_store)}

# --------------------

# --- Parte 2: O Cliente de Monitoramento (Telethon) ---

# Configura o logging (igual)
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

# Inicia o cliente Telethon USANDO A STRING DE SESSÃO
# Esta é a principal mudança!
client = TelegramClient(StringSession(TELEGRAM_SESSION), API_ID, API_HASH)

@client.on(events.NewMessage(chats=CANAL_ORIGEM))
async def handle_new_message(event):
    """
    Esta função é chamada pelo Telethon sempre que uma nova
    mensagem chega em qualquer um dos CANAIS_ORIGEM.
    """
    
    if event.message and event.message.text:
        texto_da_mensagem = event.message.text
        data_da_mensagem = event.message.date
        
        chat = await event.get_chat()
        channel_name = getattr(chat, 'username', str(chat.id))
        
        logger.info(f"Nova mensagem de @{channel_name}: {texto_da_mensagem[:50]}...")
        
        message_data = {
            "channel": channel_name,
            "timestamp_utc": data_da_mensagem.isoformat(),
            "text": texto_da_mensagem,
            "message_id": event.message.id,
            "channel_id": event.message.peer_id.channel_id,
        }
        
        # Adiciona a mensagem ao início do deque (thread-safe)
        messages_store.appendleft(message_data)

# --------------------

# --- Parte 3: Iniciando os dois serviços ---

def start_api_server():
    """Inicia o servidor FastAPI (Uvicorn) em um thread separado."""
    logger.info("Iniciando servidor FastAPI...")
    
    # Serviços de hospedagem (como Render) definem a variável $PORT
    port = int(os.environ.get("PORT", 8000))
    # host="0.0.0.0" torna o servidor acessível publicamente
    uvicorn.run(app, host="0.0.0.0", port=port)

async def main():
    """Função principal para fazer login e iniciar os dois serviços."""
    
    # 1. Inicia o servidor da API em um thread daemon
    api_thread = threading.Thread(target=start_api_server, daemon=True)
    api_thread.start()
    
    logger.info("Iniciando o cliente Telethon...")
    
    # 2. O client.start() AGORA É NÃO-INTERATIVO!
    #    Ele vai apenas se conectar usando a string de sessão.
    await client.start() 
    
    logger.info("Login do Telethon (via sessão) bem-sucedido.")
    logger.info(f"Monitoramento iniciado. API disponível.")
    
    # 3. Mantém o cliente Telethon rodando (bloqueia o thread principal)
    await client.run_until_disconnected()

if __name__ == "__main__":
    with client:
        client.loop.run_until_complete(main())