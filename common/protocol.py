import json
import struct
from typing import Dict, Any, Tuple, Union

class Protocol:
    """
    Protocolo de comunicação do sistema MiniBit.
    
    Responsável por:
    - Serializar mensagens para envio na rede
    - Desserializar mensagens recebidas
    - Definir tipos padrão de mensagens
    
    O formato utiliza um cabeçalho de 4 bytes com o tamanho seguido
    pela mensagem em formato JSON contendo tipo e payload.
    """
    
    # Constantes para tipos de mensagem
    REGISTER = "REGISTER"
    PEER_LIST = "PEER_LIST"
    REQUEST_BLOCK = "REQUEST_BLOCK"
    BLOCK_DATA = "BLOCK_DATA"
    HAVE_BLOCKS = "HAVE_BLOCKS"
    UNCHOKE = "UNCHOKE"
    CHOKE = "CHOKE"
    
    @staticmethod
    def create_message(type: str, payload: Dict[str, Any]) -> bytes:
        """
        Serializa uma mensagem para transmissão na rede.
        """
        message = {
            "type": type,
            "payload": payload
        }
        
        json_data = json.dumps(message).encode('utf-8')
        
        message_length = len(json_data)
        header = struct.pack('>I', message_length)
        
        return header + json_data
    
    @staticmethod
    def parse_message(data: bytes) -> Tuple[str, Dict[str, Any]]:
        """
        Desserializa uma mensagem recebida.
        """
        try:
            message = json.loads(data.decode('utf-8'))
            
            if "type" not in message or "payload" not in message:
                raise ValueError("Formato de mensagem inválido")
            
            return message["type"], message["payload"]
            
        except json.JSONDecodeError:
            raise ValueError("Erro ao decodificar mensagem JSON")
    
    @staticmethod
    def read_message_from_stream(stream) -> Union[Tuple[str, Dict[str, Any]], None]:
        """
        Lê uma mensagem completa de um stream de dados.
        """
        try:
            header = stream.read(4)
            if len(header) < 4:
                return None
            
            message_length = struct.unpack('>I', header)[0]
            
            data = stream.read(message_length)
            if len(data) < message_length:
                return None
                
            return Protocol.parse_message(data)
            
        except Exception:
            return None