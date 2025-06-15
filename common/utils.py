"""
utils.py - Funções utilitárias para a aplicação

Este módulo fornece funções utilitárias comuns que podem ser usadas em
diferentes partes da aplicação, incluindo operações com arquivos, manipulação
de strings, logging e gerenciamento de configuração.
"""

import os
import json
import logging
import datetime
from typing import Dict, Any, Optional, List, Union


# Operações com arquivos
def read_shared_file(filename: str = "shared_file.txt") -> Dict[str, str]:
    """
    Lê o arquivo compartilhado e converte seu conteúdo em um dicionário.
    
    Args:
        filename (str): Nome do arquivo compartilhado a ser lido
        
    Returns:
        Dict[str, str]: Dicionário de pares chave-valor do arquivo
    """
    data = {}
    file_path = os.path.join(os.path.dirname(__file__), "data", filename)
    
    try:
        with open(file_path, "r") as file:
            for line in file:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                    
                if "=" in line:
                    key, value = line.split("=", 1)
                    data[key.strip()] = value.strip()
    except FileNotFoundError:
        logging.error(f"Arquivo compartilhado não encontrado: {filename}")
    except Exception as e:
        logging.error(f"Erro ao ler arquivo compartilhado: {e}")
        
    return data


def write_to_shared_file(data: Dict[str, str], filename: str = "shared_file.txt") -> bool:
    """
    Escreve dados do dicionário no arquivo compartilhado.
    
    Args:
        data (Dict[str, str]): Dicionário de pares chave-valor para escrever
        filename (str): Nome do arquivo compartilhado para escrita
        
    Returns:
        bool: True se for bem-sucedido, False caso contrário
    """
    file_path = os.path.join(os.path.dirname(__file__), "data", filename)
    
    try:
        # Lê o conteúdo existente para preservar comentários e estrutura
        existing_lines = []
        try:
            with open(file_path, "r") as file:
                existing_lines = file.readlines()
        except FileNotFoundError:
            pass
            
        # Atualiza valores no conteúdo existente
        updated_lines = []
        updated_keys = set()
        
        for line in existing_lines:
            if "=" in line and not line.strip().startswith("#"):
                key = line.split("=", 1)[0].strip()
                if key in data:
                    updated_lines.append(f"{key}={data[key]}\n")
                    updated_keys.add(key)
                else:
                    updated_lines.append(line)
            else:
                updated_lines.append(line)
        
        # Adiciona novas chaves que não estavam no arquivo original
        for key, value in data.items():
            if key not in updated_keys:
                updated_lines.append(f"{key}={value}\n")
        
        # Escreve de volta no arquivo
        with open(file_path, "w") as file:
            file.writelines(updated_lines)
        
        return True
    except Exception as e:
        logging.error(f"Erro ao escrever no arquivo compartilhado: {e}")
        return False


# Funções de configuração
def load_config(config_file: str = "config.json") -> Dict[str, Any]:
    """
    Carrega configuração de um arquivo JSON.
    
    Args:
        config_file (str): Caminho para o arquivo de configuração
        
    Returns:
        Dict[str, Any]: Dicionário de configuração
    """
    try:
        with open(config_file, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        logging.warning(f"Arquivo de configuração não encontrado: {config_file}")
        return {}
    except json.JSONDecodeError:
        logging.error(f"JSON inválido no arquivo de configuração: {config_file}")
        return {}


# Utilitários para strings
def parse_boolean(value: Union[str, bool]) -> bool:
    """
    Converte um valor string para booleano.
    
    Args:
        value: Valor string ou booleano para converter
        
    Returns:
        bool: Valor booleano convertido
    """
    if isinstance(value, bool):
        return value
        
    return value.lower() in ("sim", "yes", "true", "t", "1", "on")


# Utilitários de logging
def setup_logging(log_level: str = "INFO", log_file: Optional[str] = None) -> None:
    """
    Configura o sistema de logging.
    
    Args:
        log_level (str): Nível de logging (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file (Optional[str]): Caminho para arquivo de log, se None loga apenas no console
    """
    level = getattr(logging, log_level.upper(), logging.INFO)
    
    config = {
        "level": level,
        "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        "datefmt": "%Y-%m-%d %H:%M:%S",
    }
    
    if log_file:
        config["filename"] = log_file
        config["filemode"] = "a"
        
    logging.basicConfig(**config)


# Utilitários de data/hora
def get_timestamp() -> str:
    """
    Obtém o timestamp atual como string.
    
    Returns:
        str: Timestamp atual em formato ISO
    """
    return datetime.datetime.now().isoformat()


def format_date(date_obj: Optional[datetime.datetime] = None, 
                format_str: str = "%Y-%m-%d") -> str:
    """
    Formata um objeto de data como string.
    
    Args:
        date_obj (Optional[datetime.datetime]): Objeto de data para formatar, 
                                               padrão é a data atual
        format_str (str): String de formato
        
    Returns:
        str: String de data formatada
    """
    if date_obj is None:
        date_obj = datetime.datetime.now()
    return date_obj.strftime(format_str)


# Tratamento de variáveis de ambiente
def get_env_var(name: str, default: Any = None) -> Any:
    """
    Obtém variável de ambiente com um valor padrão.
    
    Args:
        name (str): Nome da variável de ambiente
        default (Any): Valor padrão se não for encontrada
        
    Returns:
        Any: Valor da variável de ambiente ou o valor padrão
    """
    return os.environ.get(name, default)


if __name__ == "__main__":
    # Exemplo de uso
    setup_logging(log_level="DEBUG")
    config = load_config()
    shared_data = read_shared_file()
    logging.info(f"Dados do arquivo compartilhado: {shared_data}")