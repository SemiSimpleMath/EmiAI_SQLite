# app/services/socket_manager.py
from app.assistant.ServiceLocator.service_locator import DI


class SocketManager:
    def __init__(self):
        self.socket_id = None

    def update_connection(self, socket_id):
        self.socket_id = socket_id

    def get_connection(self):
        return self.socket_id, DI.socket_io
