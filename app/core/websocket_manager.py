"""
WebSocket connection manager for true model-level streaming
"""

import asyncio
import json
from typing import Dict, Set
from fastapi import WebSocket, WebSocketDisconnect
import logging

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections for TTS streaming"""

    def __init__(self):
        # Active connections: {connection_id: WebSocket}
        self.active_connections: Dict[str, WebSocket] = {}
        # Connection states: {connection_id: state}
        self.connection_states: Dict[str, str] = {}
        # Lock for thread-safe operations
        self.lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, connection_id: str):
        """Accept and register a new WebSocket connection"""
        await websocket.accept()
        async with self.lock:
            self.active_connections[connection_id] = websocket
            self.connection_states[connection_id] = "connected"
        logger.info(f"WebSocket connection established: {connection_id}")
        logger.info(f"Total active connections: {len(self.active_connections)}")

    async def disconnect(self, connection_id: str):
        """Remove a WebSocket connection"""
        async with self.lock:
            if connection_id in self.active_connections:
                del self.active_connections[connection_id]
            if connection_id in self.connection_states:
                del self.connection_states[connection_id]
        logger.info(f"WebSocket connection closed: {connection_id}")
        logger.info(f"Total active connections: {len(self.active_connections)}")

    async def send_text(self, connection_id: str, message: str):
        """Send a text message to a specific connection"""
        if connection_id in self.active_connections:
            try:
                await self.active_connections[connection_id].send_text(message)
            except Exception as e:
                logger.error(f"Error sending text to {connection_id}: {e}")
                await self.disconnect(connection_id)

    async def send_bytes(self, connection_id: str, data: bytes):
        """Send binary data to a specific connection"""
        if connection_id in self.active_connections:
            try:
                await self.active_connections[connection_id].send_bytes(data)
            except Exception as e:
                logger.error(f"Error sending bytes to {connection_id}: {e}")
                await self.disconnect(connection_id)

    async def send_json(self, connection_id: str, data: dict):
        """Send JSON data to a specific connection"""
        if connection_id in self.active_connections:
            try:
                await self.active_connections[connection_id].send_json(data)
            except Exception as e:
                logger.error(f"Error sending JSON to {connection_id}: {e}")
                await self.disconnect(connection_id)

    async def broadcast_text(self, message: str):
        """Broadcast a text message to all connected clients"""
        disconnected = []
        for connection_id, websocket in self.active_connections.items():
            try:
                await websocket.send_text(message)
            except Exception as e:
                logger.error(f"Error broadcasting text to {connection_id}: {e}")
                disconnected.append(connection_id)

        # Clean up disconnected clients
        for connection_id in disconnected:
            await self.disconnect(connection_id)

    async def broadcast_json(self, data: dict):
        """Broadcast JSON data to all connected clients"""
        disconnected = []
        for connection_id, websocket in self.active_connections.items():
            try:
                await websocket.send_json(data)
            except Exception as e:
                logger.error(f"Error broadcasting JSON to {connection_id}: {e}")
                disconnected.append(connection_id)

        # Clean up disconnected clients
        for connection_id in disconnected:
            await self.disconnect(connection_id)

    def get_connection_count(self) -> int:
        """Get the number of active connections"""
        return len(self.active_connections)

    def get_connection_state(self, connection_id: str) -> str:
        """Get the state of a specific connection"""
        return self.connection_states.get(connection_id, "unknown")

    def update_connection_state(self, connection_id: str, state: str):
        """Update the state of a connection"""
        if connection_id in self.connection_states:
            self.connection_states[connection_id] = state
            logger.debug(f"Connection {connection_id} state updated to: {state}")

    def is_connected(self, connection_id: str) -> bool:
        """Check if a connection is active"""
        return connection_id in self.active_connections


# Global connection manager instance
manager = ConnectionManager()


def get_connection_manager() -> ConnectionManager:
    """Get the global connection manager instance"""
    return manager
