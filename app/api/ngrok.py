import os
import sys
import yaml
import requests
import logging
import httpx
import asyncio
from time import sleep
from fastapi import FastAPI, Depends, HTTPException

# ---------
CREDENTIALS_READY = False
RETRY_LIMIT = 10
RETRY_INTERVAL = 15

# ----------------
# Environment vars
# ----------------
NGROK_HOST = os.getenv('NGROK_HOST', 'ngrok')
NGROK_PORT = os.getenv('NGROK_PORT', 4040)
NGROK_INTERNAL_WEBHOOK_HOST = os.getenv('NGROK_INTERNAL_WEBHOOK_HOST', 'rasa-core')
NGROK_INTERNAL_WEBHOOK_PORT = os.getenv('NGROK_INTERNAL_WEBHOOK_PORT', 5005)
NGROK_API_URL = f'http://{NGROK_HOST}:{NGROK_PORT}'
TELEGRAM_ACCESS_TOKEN = os.getenv('TELEGRAM_ACCESS_TOKEN', None)
TELEGRAM_BOTNAME = os.getenv('TELEGRAM_BOTNAME', None)
CREDENTIALS_PATH = os.getenv('CREDENTIALS_PATH', '/app/rasa/credentials.yml')

# -------
# Logging
# -------
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
logger = logging.getLogger(__name__)
logger.debug(f'NGROK_HOST: {NGROK_HOST}:{NGROK_PORT}\nNGROK_API_URL: {NGROK_API_URL}\nNGROK_INTERNAL_WEBHOOK_HOST: {NGROK_INTERNAL_WEBHOOK_HOST}:{NGROK_INTERNAL_WEBHOOK_PORT}')


async def wait_for_ngrok_api():
    while True:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{NGROK_API_URL}/api/tunnels")
                response.raise_for_status()
                logger.debug('ngrok API is online.')
                return True
        except httpx.RequestError:
            logger.debug('ngrok API is offline. Waiting...')
            await asyncio.sleep(RETRY_INTERVAL)


async def get_active_tunnels():
    response = requests.get(f'{NGROK_API_URL}/api/tunnels')
    response.raise_for_status()
    tunnels = response.json()['tunnels']
    return tunnels


async def stop_tunnel(tunnel):
    tunnel_id = tunnel['name']
    response = requests.delete(f'{NGROK_API_URL}/api/tunnels/{tunnel_id}')
    response.raise_for_status()


async def stop_all_tunnels():
    active_tunnels = await get_active_tunnels()
    if not active_tunnels:
        logger.debug('No active tunnels found.')
    else:
        for tunnel in active_tunnels:
            logger.debug(f"Stopping tunnel: {tunnel['name']} ({tunnel['public_url']})")
            await stop_tunnel(tunnel)


async def create_tunnel():
    response = requests.post(f'{NGROK_API_URL}/api/tunnels', json={
        'addr': f'{NGROK_INTERNAL_WEBHOOK_HOST}:{NGROK_INTERNAL_WEBHOOK_PORT}',
        'proto': 'http',
        'name': NGROK_INTERNAL_WEBHOOK_HOST,

    })
    response.raise_for_status()
    return response.json()['public_url']


# ----------------------
# Fetch ngrok public URL
# ----------------------
async def get_ngrok_url():
    return await create_tunnel()


# ----------------------------
# Update Rasa credentials file
# ----------------------------
async def update_credentials_file(ngrok_url):
    global CREDENTIALS_READY
    try:
        with open(CREDENTIALS_PATH, 'r') as file:
            credentials = yaml.safe_load(file)

        credentials['telegram']['webhook_url'] = f"{ngrok_url}/webhooks/telegram/webhook"
        credentials['telegram']['access_token'] = TELEGRAM_ACCESS_TOKEN
        credentials['telegram']['verify'] = TELEGRAM_BOTNAME

        with open(CREDENTIALS_PATH, 'w') as file:
            yaml.safe_dump(credentials, file)

        return True
    except Exception as e:
        logger.warning(f'Error updating {CREDENTIALS_PATH}: {e}')


# ---------------------
# Endpoint dependencies
# ---------------------
async def check_endpoint_availability():
    if not CREDENTIALS_READY:
        raise HTTPException(status_code=403, detail="Endpoint not available yet")
    return True
