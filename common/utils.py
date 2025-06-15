import logging
import os
import json
from typing import Any, Optional

def setup_logging(log_level: str = "INFO", log_file: Optional[str] = None) -> None:
    """Configura o logging global do projeto."""
    handlers = [logging.StreamHandler()]
    if log_file:
        handlers.append(logging.FileHandler(log_file))
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=handlers
    )

def load_config(config_path: str = "config.json") -> dict:
    """Carrega configurações do projeto a partir de um arquivo JSON."""
    if not os.path.exists(config_path):
        logging.warning(f"Arquivo de configuração {config_path} não encontrado. Usando configuração vazia.")
        return {}
    with open(config_path, "r") as f:
        return json.load(f)

def get_env_var(name: str, default: Any = None) -> Any:
    """Obtém uma variável de ambiente, com valor padrão."""
    return os.environ.get(name, default)

def read_json_file(path: str) -> Any:
    """Lê um arquivo JSON e retorna seu conteúdo."""
    with open(path, "r") as f:
        return json.load(f)

def write_json_file(path: str, data: Any) -> None:
    """Escreve dados em um arquivo JSON."""
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def ensure_dir_exists(path: str) -> None:
    """Garante que um diretório existe."""
    os.makedirs(path, exist_ok=True)

def log_and_raise(msg: str, exc: Exception) -> None:
    """Loga uma mensagem de erro e lança uma exceção."""
    logging.error(msg)
    raise exc(msg)