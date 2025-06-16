import socket
import json
import logging
from typing import Optional, Dict, Tuple

class PeerConnection:
    """
    Gerencia a comunicação de baixo nível com um único peer,
    enviando e recebendo mensagens formatadas.
    """
    def __init__(self, address: Tuple[str, int], logger: logging.Logger, sock: Optional[socket.socket] = None):
        self.address = address
        self.logger = logger
        self.socket = sock
        self._connected = sock is not None
        self._choked_by_peer = True # Começamos 'choked' por padrão

    def connect(self) -> bool:
        """Estabelece a conexão de socket se ainda não estiver conectado."""
        if self._connected:
            return True
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(5)
            self.socket.connect(self.address)
            self._connected = True
            return True
        except (socket.timeout, ConnectionRefusedError, OSError) as e:
            self.logger.error(f"Falha ao conectar a {self.address}: {e}")
            self.close()
            return False

    def send_message(self, message: Dict):
        """Serializa e envia uma mensagem para o peer."""
        if not self.is_connected():
            return
        try:
            msg_json = json.dumps(message)
            msg_bytes = msg_json.encode('utf-8')
            # Precede a mensagem com seu tamanho (4 bytes, big-endian)
            self.socket.sendall(len(msg_bytes).to_bytes(4, 'big') + msg_bytes)
        except (OSError, BrokenPipeError) as e:
            self.logger.warning(f"Erro ao enviar mensagem para {self.address}: {e}. Fechando conexão.")
            self.close()

    def read_message(self) -> Optional[Dict]:
        """Lê e desserializa uma mensagem do peer."""
        if not self.is_connected():
            return None
        try:
            # Lê o tamanho da mensagem
            raw_msglen = self.socket.recv(4)
            if not raw_msglen:
                self.close()
                return None
            msglen = int.from_bytes(raw_msglen, 'big')
            
            # Lê a mensagem completa
            data = self.socket.recv(msglen)
            if not data:
                self.close()
                return None
            
            return json.loads(data.decode('utf-8'))
        except (OSError, json.JSONDecodeError, ConnectionResetError) as e:
            self.logger.warning(f"Erro ao ler mensagem de {self.address}: {e}. Fechando conexão.")
            self.close()
            return None

    def close(self):
        """Fecha a conexão do socket."""
        if self._connected:
            self._connected = False
            if self.socket:
                self.socket.close()
                self.socket = None

    def is_connected(self) -> bool:
        return self._connected

    def set_choked_by_peer(self, status: bool):
        self._choked_by_peer = status

    def is_choked_by_peer(self) -> bool:
        return self._choked_by_peer