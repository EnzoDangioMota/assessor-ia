import os
from dotenv import load_dotenv
import psycopg2

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")  

def get_conn():
    """Abre e devolve uma conexão com o postgres. Quem abre é responsável por fechar"""
    return psycopg2.connect(DATABASE_URL)