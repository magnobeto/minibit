import socket
import json
import struct
import logging
from typing import Tuple, Optional, Dict, Any, BinaryIO

class PeerConnection:
    """
    Gerencia a conexão com um peer específico no sistema P2P.
    Responsável pela comunicação, enviando e recebendo mensagens de blocos.
    """
    
    # Definição de tipos de mensagens
    MSG_REQUEST_BLOCK = 1
    MSG_BLOCK_DATA = 2
    MSG_HAVE_BLOCKS = 3
    MSG_CHOKE = 4
    MSG_UNCHOKE = 5
    MSG_REGISTER = 6
    
    def __init__(self, peer_address: Tuple[str, int], peer_id: str = None):
        """
        Inicializa uma conexão com um peer.
        
        Args:
            peer_address: Tupla com (host, porta) do peer
            peer_id: Identificador do peer (opcional)
        """
        self.peer_address = peer_address
        self.peer_id = peer_id
        self.socket: Optional[socket.socket] = None
        self.file_stream: Optional[BinaryIO] = None
        self.connected = False
        self.choked = True  # Por padrão, começamos choked
        
        # Configuração de logger
        self.logger = logging.getLogger(f"PeerConn-{peer_id if peer_id else 'Unknown'}")
        
    def connect(self, timeout: int = 5) -> bool:
        """
        Estabelece conexão com o peer.
        
        Args:
            timeout: Tempo máximo de espera para conexão em segundos
            
        Returns:
            True se a conexão foi bem-sucedida, False caso contrário
        """
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(timeout)
            self.socket.connect(self.peer_address)
            self.file_stream = self.socket.makefile(mode='rb')
            self.connected = True
            self.logger.info(f"Conexão estabelecida com {self.peer_address}")
            return True
        except Exception as e:
            self.logger.error(f"Erro ao conectar a {self.peer_address}: {str(e)}")
            self.close()
            return False
    
    def register(self, own_id: str, blocks: list) -> bool:
        """
        Registra-se com o peer, enviando ID e blocos disponíveis.
        
        Args:
            own_id: ID deste peer
            blocks: Lista de blocos disponíveis
            
        Returns:
            True se o registro foi bem-sucedido, False caso contrário
        """
        if not self.connected:
            if not self.connect():
                return False
                
        try:
            payload = {
                "peer_id": own_id,
                "blocks": blocks
            }
            self._send_message(self.MSG_REGISTER, payload)
            
            # Espera resposta com HAVE_BLOCKS
            msg_type, response = self._read_message()
            if msg_type == self.MSG_HAVE_BLOCKS and "blocks" in response:
                # Atualizar informações do peer
                self.peer_id = response.get("peer_id", self.peer_id)
                return True
            return False
            
        except Exception as e:
            self.logger.error(f"Erro ao registrar com peer: {str(e)}")
            return False
    
    def request_block(self, block_id: str) -> Optional[bytes]:
        """
        Solicita um bloco específico do peer e aguarda resposta.
        
        Args:
            block_id: ID do bloco solicitado
            
        Returns:
            Dados do bloco ou None se não foi possível obter
        """
        if not self.connected or self.choked:
            return None
            
        try:
            # Envia solicitação
            payload = {"block_id": block_id}
            self._send_message(self.MSG_REQUEST_BLOCK, payload)
            
            # Aguarda resposta
            msg_type, response = self._read_message()
            if msg_type == self.MSG_BLOCK_DATA and response.get("block_id") == block_id:
                return response.get("data")
            
            return None
            
        except Exception as e:
            self.logger.error(f"Erro ao solicitar bloco {block_id}: {str(e)}")
            self.close()
            return None
    
    def send_block(self, block_id: str, data: bytes) -> bool:
        """
        Envia um bloco para o peer.
        
        Args:
            block_id: ID do bloco
            data: Dados binários do bloco
            
        Returns:
            True se o bloco foi enviado com sucesso, False caso contrário
        """
        if not self.connected:
            return False
            
        try:
            payload = {
                "block_id": block_id,
                "data": data
            }
            self._send_message(self.MSG_BLOCK_DATA, payload)
            return True
            
        except Exception as e:
            self.logger.error(f"Erro ao enviar bloco {block_id}: {str(e)}")
            self.close()
            return False
    
    def send_have_blocks(self, blocks: list) -> bool:
        """
        Notifica o peer sobre os blocos disponíveis.
        
        Args:
            blocks: Lista de IDs de blocos disponíveis
            
        Returns:
            True se a mensagem foi enviada com sucesso, False caso contrário
        """
        if not self.connected:
            return False
            
        try:
            payload = {"blocks": blocks}
            self._send_message(self.MSG_HAVE_BLOCKS, payload)
            return True
            
        except Exception as e:
            self.logger.error(f"Erro ao enviar HAVE_BLOCKS: {str(e)}")
            self.close()
            return False
    
    def send_choke(self) -> bool:
        """
        Envia uma mensagem CHOKE para o peer.
        
        Returns:
            True se a mensagem foi enviada com sucesso, False caso contrário
        """
        if not self.connected:
            return False
            
        try:
            self._send_message(self.MSG_CHOKE, {})
            return True
        except Exception as e:
            self.logger.error(f"Erro ao enviar CHOKE: {str(e)}")
            self.close()
            return False
    
    def send_unchoke(self) -> bool:
        """
        Envia uma mensagem UNCHOKE para o peer.
        
        Returns:
            True se a mensagem foi enviada com sucesso, False caso contrário
        """
        if not self.connected:
            return False
            
        try:
            self._send_message(self.MSG_UNCHOKE, {})
            return True
        except Exception as e:
            self.logger.error(f"Erro ao enviar UNCHOKE: {str(e)}")
            self.close()
            return False
    
    def read_message(self) -> Tuple[int, Dict[str, Any]]:
        """
        Lê a próxima mensagem do peer.
        
        Returns:
            Tupla com (tipo_da_mensagem, payload)
        
        Raises:
            Exception: Se ocorrer um erro na leitura
        """
        if not self.connected:
            raise Exception("Não conectado ao peer")
            
        return self._read_message()
    
    def close(self) -> None:
        """
        Fecha a conexão com o peer.
        """
        self.connected = False
        
        if self.file_stream:
            try:
                self.file_stream.close()
            except:
                pass
            self.file_stream = None
            
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
    
    def set_choked_status(self, choked: bool) -> None:
        """
        Define o status de choked da conexão.
        
        Args:
            choked: True se choked, False se unchoked
        """
        self.choked = choked
    
    def is_connected(self) -> bool:
        """
        Verifica se a conexão está ativa.
        
        Returns:
            True se conectado, False caso contrário
        """
        return self.connected
    
    def is_choked(self) -> bool:
        """
        Verifica se a conexão está em estado choked.
        
        Returns:
            True se choked, False caso contrário
        """
        return self.choked
    
    def _send_message(self, msg_type: int, payload: Dict[str, Any]) -> None:
        """
        Envia uma mensagem para o peer.
        
        Args:
            msg_type: Tipo da mensagem
            payload: Dados da mensagem
            
        Raises:
            Exception: Se ocorrer um erro no envio
        """
        # Serializa o payload
        payload_bytes = json.dumps(payload).encode('utf-8')
        
        # Cria o cabeçalho: [tamanho(4)][tipo(1)][payload...]
        header = struct.pack('>IB', len(payload_bytes), msg_type)
        
        # Envia o cabeçalho e o payload
        try:
            self.socket.sendall(header + payload_bytes)
        except Exception as e:
            self.logger.error(f"Erro ao enviar mensagem: {str(e)}")
            self.close()
            raise
    
    def _read_message(self) -> Tuple[int, Dict[str, Any]]:
        """
        Lê uma mensagem do stream do socket.
        
        Returns:
            Tupla com (tipo_da_mensagem, payload)
            
        Raises:
            Exception: Se ocorrer um erro na leitura
        """
        try:
            # Lê o cabeçalho
            header = self.file_stream.read(5)
            if len(header) < 5:
                raise Exception("Conexão fechada durante leitura do cabeçalho")
                
            # Extrai tamanho e tipo
            payload_size, msg_type = struct.unpack('>IB', header)
            
            # Lê o payload
            payload_bytes = self.file_stream.read(payload_size)
            if len(payload_bytes) < payload_size:
                raise Exception("Conexão fechada durante leitura do payload")
                
            # Decodifica o payload
            payload = json.loads(payload_bytes.decode('utf-8'))
            return msg_type, payload
            
        except json.JSONDecodeError as e:
            self.logger.error(f"Erro ao decodificar JSON: {str(e)}")
            raise Exception(f"Formato de mensagem inválido: {str(e)}")
            
        except Exception as e:
            self.logger.error(f"Erro ao ler mensagem: {str(e)}")
            self.close()
            raise