# File: app/assistant/manager_registry/manager_instance_handler.py

class ManagerInstanceHandler:
    def __init__(self):
        # { instance_name: instance_object }
        self.instances = {}

        # { manager_type: [instance_name1, instance_name2, ...] }
        self.type_to_instances = {}

    def register(self, name: str, instance, manager_type: str):
        """Registers a new manager instance."""
        self.instances[name] = instance
        self.type_to_instances.setdefault(manager_type, []).append(name)

    def get_instance(self, name: str):
        """Returns a manager instance by name."""
        return self.instances.get(name)

    def list_all(self):
        """Returns all manager instances."""
        return list(self.instances.items())

    def get_instances_by_type(self, manager_type: str):
        """Returns all instances of a given manager type."""
        names = self.type_to_instances.get(manager_type, [])
        return [(name, self.instances[name]) for name in names]

    def find_available_instance(self, manager_type: str):
        """Returns the first non-busy instance of the given type, or None."""
        for name in self.type_to_instances.get(manager_type, []):
            instance = self.instances.get(name)
            if instance and not instance.is_busy():
                return name, instance
        return None, None

    def get_unique_name(self, manager_type: str):
        """Generates a unique instance name for a new manager."""
        base = manager_type
        suffix = 1
        existing_names = set(self.instances.keys())
        while f"{base}{suffix}" in existing_names:
            suffix += 1
        return f"{base}_{suffix}"
