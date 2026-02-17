import os, secrets, datetime
import psycopg2

def generate_token():
    return secrets.token_hex(32)

def token_expiration(hours=24):
    return datetime.datetime.utcnow() + datetime.timedelta(hours=hours)