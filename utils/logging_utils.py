import logging
import os

def setup_peer_logger(peer_id: str) -> logging.Logger:
    """Configures and returns a logger for a peer"""
    logger = logging.getLogger(f"Peer-{peer_id}")
    logger.setLevel(logging.INFO)
    
    if not logger.handlers:
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(
            logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        )
        logger.addHandler(console_handler)
        
        # File handler
        file_handler = logging.FileHandler(f"peer-{peer_id}.log")
        file_handler.setFormatter(
            logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        )
        logger.addHandler(file_handler)
    
    return logger