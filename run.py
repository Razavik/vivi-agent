try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from src.web.server import start_server

if __name__ == "__main__":
    start_server()
