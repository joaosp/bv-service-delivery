"""
File Queue Registry for MS Teams File Delivery

Thread-safe queue for managing files that need to be sent to Teams users.
Tools can add files to the queue, and the Teams handler retrieves and sends them.
"""

import threading
from typing import List, Dict, Any, Optional
from pathlib import Path


class FileQueue:
    """Thread-safe queue for files pending Teams delivery"""

    def __init__(self):
        """Initialize the file queue"""
        self._queues: Dict[str, List[Dict[str, Any]]] = {}
        self._lock = threading.Lock()

    def add_file(
        self,
        conversation_id: str,
        file_path: str,
        description: Optional[str] = None,
        priority: str = "normal"
    ):
        """
        Add file to conversation's send queue

        Args:
            conversation_id: Teams conversation ID
            file_path: Absolute path to file
            description: User-friendly description
            priority: Priority level (high, normal, low)
        """
        with self._lock:
            if conversation_id not in self._queues:
                self._queues[conversation_id] = []

            file_info = {
                "file_path": file_path,
                "description": description or Path(file_path).name,
                "priority": priority,
                "file_name": Path(file_path).name
            }

            self._queues[conversation_id].append(file_info)

    def get_files(self, conversation_id: str) -> List[Dict[str, Any]]:
        """
        Get and clear files for conversation

        Args:
            conversation_id: Teams conversation ID

        Returns:
            List of file info dictionaries
        """
        with self._lock:
            files = self._queues.get(conversation_id, [])
            # Clear queue after retrieving
            if conversation_id in self._queues:
                del self._queues[conversation_id]
            return files

    def clear_queue(self, conversation_id: str):
        """
        Clear queue for conversation

        Args:
            conversation_id: Teams conversation ID
        """
        with self._lock:
            if conversation_id in self._queues:
                del self._queues[conversation_id]

    def get_queue_size(self, conversation_id: str) -> int:
        """
        Get number of files in queue for conversation

        Args:
            conversation_id: Teams conversation ID

        Returns:
            Number of files in queue
        """
        with self._lock:
            return len(self._queues.get(conversation_id, []))


# Global singleton instance
file_queue = FileQueue()
