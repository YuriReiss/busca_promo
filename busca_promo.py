import logging
import datetime
import threading
import asyncio
import os
import time   # <-- ADICIONADO PARA O PING
import httpx  # <-- ADICIONADO PARA O PING
from collections import deque

# --- Importações de API ---
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# --- Importações do Telegram ---
from telethon import TelegramClient, events # type: ignore
from telethon.sessions import StringSession

# --- Configuração ---
# 1. Credenciais
API_ID_STR = os.environ.get('API_ID')
API_HASH = os.environ.get('API_HASH')
TELEGRAM_SESSION = os.environ.get('TELEGRAM_SESSION_STRING')

# --- 2. URL PARA O SELF-PING ---
# A plataforma Render (e outras) definem esta variável automaticamente.
# Esta é a URL pública do seu serviço.
RENDER_EXTERNAL_URL = os.environ.get('RENDER_EXTERNAL_URL')

# Validação se as variáveis existem
if not API_ID_STR or not API_HASH or not TELEGRAM_SESSION:
    raise ValueError("API_ID, API_HASH, e TELEGRAM_SESSION_STRING devem ser definidos como variáveis de ambiente.")

API_ID = int(API_ID_STR)

# 2. Lista de canais
CANAL_ORIGEM = [
    "https://t.me/urubupromo",
    "https://t.me/pechinchou"
]

# 4. Armazenamento em memória
MAX_MENSAGENS = 100
messages_store = deque(maxlen=MAX_MENSAGENS)
# --------------------

# --- Parte 1: O Servidor da API (FastAPI) ---

app = FastAPI(
    title="Telegram Monitor API",
    description="Uma API que expõe mensagens de canais do Telegram em tempo real.",
)

# Permite que qualquer website (origem) aceda à sua API.
app.add_middleware(
    CORSMiddleware, # type: ignore
    allow_origins=["*"],  # Permite todas as origens
    allow_credentials=True,
    allow_methods=["*"],  # Permite todos os métodos
    allow_headers=["*"],  # Permite todos os cabeçalhos
)

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

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

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
        
        messages_store.appendleft(message_data)

# --------------------

# --- Parte 3: Iniciando os serviços (E O PING) ---

def start_api_server():
    """Inicia o servidor FastAPI (Uvicorn) em um thread separado."""
    logger.info("Iniciando servidor FastAPI...")
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

# --- 3. NOVA FUNÇÃO DE SELF-PING ---
def self_ping_thread():
    """
    Em plataformas gratuitas (como a Render), os serviços web
    entram em 'sleep' após 15 minutos de inatividade HTTP.
    Este 'ping' a si mesmo a cada 10 minutos evita isso.
    """
    if not RENDER_EXTERNAL_URL:
        logger.warning("RENDER_EXTERNAL_URL não definida. O 'self-ping' está desativado.")
        return

    # Espera 60 segundos para o servidor FastAPI iniciar antes de começar
    logger.info("Auto-ping 'Keep-Alive' será iniciado em 60 segundos.")
    time.sleep(60) 
    
    while True:
        try:
            logger.info("Auto-ping (Keep-Alive) sendo executado...")
            with httpx.Client(timeout=30) as client_ping:
                # Faz uma requisição para o endpoint raiz "/"
                response = client_ping.get(RENDER_EXTERNAL_URL)
            logger.info(f"Auto-ping status: {response.status_code}")
        
        except Exception as e:
            logger.error(f"Falha no auto-ping 'Keep-Alive': {e}")
        
        # Espera 10 minutos (600 segundos) para o próximo ping
        time.sleep(300)
# ------------------------------------

async def main():
    """Função principal para fazer login e iniciar os dois serviços."""
    
    # 1. Inicia o servidor da API em um thread daemon
    api_thread = threading.Thread(target=start_api_server, daemon=True)
    api_thread.start()
    
    # --- 4. INICIA A THREAD DE SELF-PING ---
    # (Apenas se a URL estiver definida)
    if RENDER_EXTERNAL_URL:
        ping_thread = threading.Thread(target=self_ping_thread, daemon=True)
        ping_thread.start()
    # ----------------------------------------
    
    logger.info("Iniciando o cliente Telethon...")
    
    # 2. O client.start() AGORA É NÃO-INTERATIVO!
    await client.start() 
    
    logger.info("Login do Telethon (via sessão) bem-sucedido.")
    logger.info(f"Monitoramento iniciado. API disponível.")
    
    # 3. Mantém o cliente Telethon rodando (bloqueia o thread principal)
    await client.run_until_disconnected()

if __name__ == "__main__":
    with client:

        client.loop.run_until_complete(main())
