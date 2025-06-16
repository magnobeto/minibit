from typing import Dict, Set, Tuple, Optional, Any
import logging
import threading
import time
from peer.peer_connection import PeerConnection
from peer.block_manager import BlockManager

class PeerHelper:
    """Helper class to manage peer operations and state"""
    
    def __init__(self, logger: logging.Logger, block_manager: Optional[BlockManager] = None):
        """
        Initialize PeerHelper
        Args:
            logger: Logger instance
            block_manager: Optional BlockManager instance
        """
        self.logger = logger
        self.block_manager = block_manager or BlockManager()
        self._peers: Dict[str, Dict] = {}
        self._connections: Dict[str, PeerConnection] = {}
        self._peers_lock = threading.Lock()
        self._connections_lock = threading.Lock()
        self._running = False

    def handle_connection(self, peer_id: str, peer_addr: Tuple[str, int], 
                         blocks: Set[str], connection: PeerConnection) -> None:
        """Handle new peer connection"""
        with self._peers_lock, self._connections_lock:
            self._peers[peer_id] = {
                "address": peer_addr,
                "available_blocks": blocks,
                "last_seen": time.time()
            }
            self._connections[peer_id] = connection

    def handle_message(self, peer_id: str, msg_type: str, payload: Dict) -> None:
        """Handle incoming messages from peers"""
        if msg_type == PeerConnection.MSG_HAVE_BLOCKS:
            self.update_peer_blocks(peer_id, set(payload.get("blocks", [])))
        elif msg_type == PeerConnection.MSG_REQUEST_BLOCK:
            self._handle_block_request(peer_id, payload.get("block_id"))
        # ...handle other message types...

    def _handle_block_request(self, peer_id: str, block_id: str) -> None:
        """Handle block request from a peer"""
        if block_id in self.block_manager.get_blocks():
            block_data = self.block_manager.read_block(block_id)
            with self._connections_lock:
                if peer_id in self._connections:
                    self._connections[peer_id].send_message(
                        PeerConnection.MSG_BLOCK_DATA,
                        {"block_id": block_id, "data": block_data}
                    )

    def broadcast_block(self, block_id: str) -> None:
        """Broadcast new block to all peers"""
        blocks = list(self.block_manager.get_blocks())
        self.broadcast_message(
            PeerConnection.MSG_HAVE_BLOCKS,
            {"blocks": blocks}
        )

    def broadcast_message(self, msg_type: str, payload: Dict) -> None:
        """Broadcast message to all connected peers"""
        with self._connections_lock:
            for conn in self._connections.values():
                try:
                    conn.send_message(msg_type, payload)
                except Exception as e:
                    self.logger.error(f"Error broadcasting: {e}")

    def cleanup(self) -> None:
        """Clean up all connections"""
        with self._connections_lock:
            for conn in self._connections.values():
                conn.close()
            self._connections.clear()
        
        with self._peers_lock:
            self._peers.clear()