from pathlib import Path
from app.assistant.utils.config_loader import load_config

class ManagerRegistry:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self._configs = {}
        self._instances = {}

    def preload_all(self):
        for subdir in self.base_dir.iterdir():
            if subdir.is_dir() and (subdir / "config.yaml").exists():
                name = subdir.name
                config_path = subdir / "config.yaml"
                config = load_config(config_path)
                self._configs[name] = config

    def get(self, name: str):
        return self._configs.get(name)

    def list_available(self):
        return list(self._configs.keys())

    def get_manager_config(self, name):
        return self._configs[name]

    def all_configs(self):
        return self._configs

    def register_instance(self, name: str, instance):
        self._instances[name] = instance

    def get_instance(self, name: str):
        return self._instances.get(name)

    def list_instances(self):
        return list(self._instances.keys())

    def all_instances(self):
        return self._instances
