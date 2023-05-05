from fastapi import UploadFile
from functools import partial
from hashlib import sha256
from uuid import UUID
import aiofiles
import json
import re
from config import (
    logger
)

_snake_1 = partial(re.compile(r'(.)((?<![^A-Za-z])[A-Z][a-z]+)').sub, r'\1_\2')
_snake_2 = partial(re.compile(r'([a-z0-9])([A-Z])').sub, r'\1_\2')


# ---------------------------------------
# Convert to snake casing (for DB models)
# ---------------------------------------
def snake_case(string: str) -> str:
    return _snake_2(_snake_1(string)).casefold()


# ------------------------------
# Check if string is UUID format
# ------------------------------
def is_uuid(uuid: str) -> bool:
    uuid = str(uuid) if isinstance(uuid, UUID) else uuid
    return re.match(r"^[0-9a-f]{8}-?[0-9a-f]{4}-?4[0-9a-f]{3}-?[89ab][0-9a-f]{3}-?[0-9a-f]{12}$", uuid)


# ---------------------------
# Writes a file to disk async
# ---------------------------
async def save_file(file: UploadFile, file_path: str):
    async with aiofiles.open(file_path, 'wb') as f:
        await f.write(await file.read())


# ---------------------------
# Get SHA256 hash of contents
# ---------------------------
def get_sha256(contents: bytes):
    return sha256(contents).hexdigest()


# -----------------------
# Get SHA256 hash of file
# -----------------------
def get_file_hash(
        file_path: str,
):
    with open(file_path, 'rb') as f:
        file_hash = sha256(f.read()).hexdigest()

    return file_hash


# -------------------
# Clean up LLM output
# -------------------
def sanitize_output(
    str_output: str
):
    # Let's sanitize the JSON
    res = str_output.replace("\n", '')

    # If the first character is "?", remove it. Ran into this issue for some reason.
    if res[0] == '?':
        res = res[1:]

    # check if response is valid json
    try:
        json.loads(res)
    except json.JSONDecodeError:
        raise ValueError(f'LLM response is not valid JSON: {res}')

    if 'message' not in res or 'tags' not in res or 'is_escalate' not in res:
        raise ValueError(f'LLM response is missing required fields: {res}')

    logger.debug(f'Output: {res}')
    return res


# ------------------
# Clean up LLM input
# ------------------
def sanitize_input(
    str_input: str
):
    # Escape single quotes that cause output JSON issues
    str_input = str_input.replace("'", "")

    logger.debug(f'Input: {str_input}')
    return str_input

