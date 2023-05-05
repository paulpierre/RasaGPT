from fastapi import (
    HTTPException,
    FastAPI,
    Depends,
)
import requests
import logging
import asyncio
import httpx
import yaml
import sys
import os

# ---------
# Constants
# ---------
CREDENTIALS_READY = False
RETRY_LIMIT = 10
RETRY_INTERVAL = 15

# ----------------
# Environment vars
# ----------------
NGROK_HOST = os.getenv("NGROK_HOST", "ngrok")
NGROK_PORT = os.getenv("NGROK_PORT", 4040)
NGROK_INTERNAL_WEBHOOK_HOST = os.getenv("NGROK_INTERNAL_WEBHOOK_HOST", "rasa-core")
NGROK_INTERNAL_WEBHOOK_PORT = os.getenv("NGROK_INTERNAL_WEBHOOK_PORT", 5005)
NGROK_API_URL = f"http://{NGROK_HOST}:{NGROK_PORT}"
TELEGRAM_ACCESS_TOKEN = os.getenv("TELEGRAM_ACCESS_TOKEN", None)
TELEGRAM_BOTNAME = os.getenv("TELEGRAM_BOTNAME", None)
CREDENTIALS_PATH = os.getenv("CREDENTIALS_PATH", "/app/rasa/credentials.yml")

# -------
# Logging
# -------
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
logger = logging.getLogger(__name__)
logger.debug(
    f"NGROK_HOST: {NGROK_HOST}:{NGROK_PORT}\nNGROK_API_URL: {NGROK_API_URL}\nNGROK_INTERNAL_WEBHOOK_HOST: {NGROK_INTERNAL_WEBHOOK_HOST}:{NGROK_INTERNAL_WEBHOOK_PORT}"
)


# ---------------------------------
# Wait for ngrok API to come online
# ---------------------------------
async def wait_for_ngrok_api():

    while True:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{NGROK_API_URL}/api/tunnels")
                response.raise_for_status()
                logger.debug("ngrok API is online.")
                return True
        except httpx.RequestError:
            logger.debug("ngrok API is offline. Waiting...")
            await asyncio.sleep(RETRY_INTERVAL)


# -------------------------------------
# Fetch list of active tunnels on ngrok
# -------------------------------------
async def get_active_tunnels():
    try:
        response = requests.get(f"{NGROK_API_URL}/api/tunnels")
        response.raise_for_status()
        tunnels = response.json()["tunnels"]
    except requests.exceptions.HTTPError:
        tunnels = []
    return tunnels


# -----------------
# Stop ngrok tunnel
# -----------------
async def stop_tunnel(tunnel):
    tunnel_id = tunnel["name"]
    response = requests.delete(f"{NGROK_API_URL}/api/tunnels/{tunnel_id}")
    response.raise_for_status()


# ----------------------
# Stop all ngrok tunnels
# ----------------------
async def stop_all_tunnels():
    active_tunnels = await get_active_tunnels()
    if not active_tunnels:
        logger.debug("No active tunnels found.")
    else:
        for tunnel in active_tunnels:
            logger.debug(f"Stopping tunnel: {tunnel['name']} ({tunnel['public_url']})")
            await stop_tunnel(tunnel)


# -------------------------------------
# Get the first ngrok tunnel w/ retries
# -------------------------------------
async def get_tunnel(retry=0):
    if retry > RETRY_LIMIT:
        raise Exception(
            f"Could not create ngrok tunnel. Exceed retry limit of {RETRY_LIMIT} attempts."
        )

    active_tunnels = await get_active_tunnels()
    if len(active_tunnels) == 0:
        logger.debug(f"No active tunnels found. Trying again in {RETRY_INTERVAL}s..")
        await asyncio.sleep(RETRY_INTERVAL)
        retry += 1
        return await get_tunnel(retry=retry)
    else:
        return active_tunnels[0]["public_url"]


# -------------------
# Create ngrok tunnel
# -------------------
async def create_tunnel():
    response = requests.post(
        f"{NGROK_API_URL}/api/tunnels",
        json={
            "addr": f"{NGROK_INTERNAL_WEBHOOK_HOST}:{NGROK_INTERNAL_WEBHOOK_PORT}",
            "proto": "http",
            "name": NGROK_INTERNAL_WEBHOOK_HOST,
        },
    )
    try:
        response.raise_for_status()
        return response.json()["public_url"]
    except requests.exceptions.HTTPError as e:
        logger.warning(f"Error creating ngrok tunnel: {e}")
        return False


# ----------------------------
# Update Rasa credentials file
# ----------------------------
async def update_credentials_file(ngrok_url):
    global CREDENTIALS_READY
    try:
        with open(CREDENTIALS_PATH, "r") as file:
            credentials = yaml.safe_load(file)

        credentials["custom_telegram.CustomTelegramInput"][
            "webhook_url"
        ] = f"{ngrok_url}/webhooks/telegram/webhook"
        credentials["custom_telegram.CustomTelegramInput"][
            "access_token"
        ] = TELEGRAM_ACCESS_TOKEN
        credentials["custom_telegram.CustomTelegramInput"]["verify"] = TELEGRAM_BOTNAME

        with open(CREDENTIALS_PATH, "w") as file:
            yaml.safe_dump(credentials, file)

        CREDENTIALS_READY = True
    except Exception as e:
        logger.warning(f"Error updating {CREDENTIALS_PATH}: {e}")
        sys.exit(1)


# -----------------
# FastAPI endpoints
# -----------------

app = FastAPI()


# -------------
# Startup event
# -------------
@app.on_event("startup")
async def startup_event():
    env = os.getenv("ENV", None)
    if env and env.lower() in ["dev", "development", "local"]:
        await wait_for_ngrok_api()
        url = await get_tunnel()
        if not url:
            logger.debug("No active tunnels found. Creating one...")
            url = await create_tunnel()
            logger.debug(f"Tunnel url: {url}")
        await update_credentials_file(url)
    else:
        logger.debug("Not in dev environment. Skipping.")


# ---------------------
# Endpoint dependencies
# ---------------------
async def check_endpoint_availability():
    if not CREDENTIALS_READY:
        raise HTTPException(status_code=403, detail="Endpoint not available yet")
    return True


# ---------------------
# Health check endpoint
# ---------------------
# This endpoint is used by docker-compose to check if the
# container is ready. If it is ready, Rasa core can start
@app.get("/", dependencies=[Depends(check_endpoint_availability)])
async def health_check():
    return {"status": "ok"}
