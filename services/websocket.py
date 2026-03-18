"""
RYBAT Intelligence Platform - WebSocket Manager
Handles real-time communication with dashboard clients
"""

from collections import defaultdict
from typing import List, Dict, Any, Optional
from fastapi import WebSocket

from utils.logging import get_logger

logger = get_logger(__name__)

# Limits
MAX_CONNECTIONS = 50        # Total across all clients
MAX_CONNECTIONS_PER_IP = 5  # Per source IP


class ConnectionManager:
    """Manages WebSocket connections and broadcasts"""

    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self._ip_counts: Dict[str, int] = defaultdict(int)
        self._conn_ips: Dict[int, str] = {}  # id(ws) -> ip

    async def connect(self, websocket: WebSocket, client_ip: Optional[str] = None) -> bool:
        """
        Accept and register a new WebSocket connection.

        Returns False (and closes with 1008) if the connection cap or
        per-IP limit would be exceeded.
        """
        try:
            # Enforce global cap
            if len(self.active_connections) >= MAX_CONNECTIONS:
                logger.warning(f"WebSocket rejected: global cap ({MAX_CONNECTIONS}) reached")
                await websocket.close(code=1008, reason="Server connection limit reached")
                return False

            # Enforce per-IP cap
            ip = client_ip or "unknown"
            if self._ip_counts[ip] >= MAX_CONNECTIONS_PER_IP:
                logger.warning(f"WebSocket rejected: per-IP cap for {ip}")
                await websocket.close(code=1008, reason="Too many connections from this IP")
                return False

            await websocket.accept()
            self.active_connections.append(websocket)
            self._ip_counts[ip] += 1
            self._conn_ips[id(websocket)] = ip
            logger.info(f"WebSocket client connected ({ip}). Total: {len(self.active_connections)}")
            return True
        except Exception as e:
            logger.error(f"Error accepting WebSocket connection: {e}")
            return False

    def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            ws_id = id(websocket)
            ip = self._conn_ips.pop(ws_id, None)
            if ip and self._ip_counts[ip] > 0:
                self._ip_counts[ip] -= 1
                if self._ip_counts[ip] == 0:
                    del self._ip_counts[ip]
            logger.info(f"WebSocket client disconnected. Total: {len(self.active_connections)}")
    
    async def send_personal_message(self, message: Dict[str, Any], websocket: WebSocket):
        """Send a message to a specific client"""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Error sending personal message: {e}")
            self.disconnect(websocket)
    
    async def broadcast(self, message: Dict[str, Any]):
        """
        Broadcast a message to all connected clients

        Snapshots the connection list before iterating so that
        concurrent connect/disconnect during await points cannot
        mutate the list mid-iteration.

        Args:
            message: Dictionary to send as JSON
        """
        if not self.active_connections:
            return

        # Snapshot to avoid concurrent modification during awaits
        connections = list(self.active_connections)
        disconnected = []
        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting to client: {e}")
                disconnected.append(connection)

        # Clean up disconnected clients
        for connection in disconnected:
            self.disconnect(connection)
    
    async def broadcast_new_signal(self, signal: Dict[str, Any]):
        """Broadcast a new intelligence signal"""
        client_count = len(self.active_connections)
        signal_title = (signal.get('title') or '')[:50]
        if client_count > 0:
            logger.debug(
                f"Broadcasting signal to {client_count} client(s): {signal_title}..."
            )
        else:
            logger.debug(f"No WS clients for broadcast: {signal_title}...")
        await self.broadcast({
            "type": "new_signals",
            "data": [signal]
        })
    
    async def broadcast_report_update(self, content: str):
        """Broadcast an executive report update"""
        await self.broadcast({
            "type": "report_update",
            "content": content
        })
    
    async def broadcast_status_update(self, status: Dict[str, Any]):
        """Broadcast a status update"""
        await self.broadcast({
            "type": "status_update",
            "data": status
        })

    def get_connection_count(self) -> int:
        """Return number of active connections"""
        return len(self.active_connections)


# Singleton instance
manager = ConnectionManager()
