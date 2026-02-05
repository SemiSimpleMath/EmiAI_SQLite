# app/assistant/initialize_system.py

import threading
import time


from app.assistant.ServiceLocator.service_locator import DI, ServiceLocator
from app.assistant.emi_event_relay.emi_event_relay import EmiEventRelay
from app.assistant.maintenance_manager.maintenance_manager import MaintenanceManager
from app.assistant.manager_registry.manager_instance_handler import ManagerInstanceHandler
from app.assistant.slack_interface.slack_interface import SlackInterface
from app.assistant.system_state_monitor.system_state_monitor import SystemStateMonitor
from app.assistant.ui_tool_caller.ui_tool_caller import UIToolCaller
from app.assistant.progress_curator import ProgressCurator
from app.services.socket_manager import SocketManager
from app.assistant.validation.agent_validator import validate_all

from app.assistant.utils.logging_config import get_logger
logger = get_logger(__name__)


def initialize_system():

    logger.info("initialize_system() is running...")
    print("inintialize system...")
    logger.info(f"Active threads count at start of initialize: {threading.active_count()}")
    print(f"Active threads count at start of initialize: {threading.active_count()}")
    multi_agent_manager_factory = DI.multi_agent_manager_factory

    preload_start = time.time()
    manager_registry = DI.manager_registry
    manager_registry.preload_all()
    preload_end = time.time()
    elapsed_time = preload_end - preload_start  # Compute time difference

    logger.info(f"✅ Preloading completed in {elapsed_time:.2f} seconds.")
    print(f"✅ Preloading completed in {elapsed_time:.2f} seconds.")

    agent_registry = DI.agent_registry
    validate_all(agent_registry)


    # Create and register the SocketManager
    socket_manager = SocketManager()
    ServiceLocator.register('socket_manager', socket_manager)

    # Relay AFK state changes to the music client (frontend decides whether to pause/resume).
    from app.assistant.afk_manager.music_afk_relay import MusicAfkRelay
    ServiceLocator.register("music_afk_relay", MusicAfkRelay())

    event_relay = EmiEventRelay()
    ServiceLocator.register('event_relay', event_relay)

    progress_curator = ProgressCurator()
    ServiceLocator.register("progress_curator", progress_curator)
    ui_tool_caller = UIToolCaller()
    ServiceLocator.register('ui_tool_caller', ui_tool_caller)

    print("\n\nLoading manager_instance_handler.\n\n")
    ServiceLocator.register('manager_instance_handler', ManagerInstanceHandler())

    print("\n\nLoading emi_agent:")
    emi_agent = DI.agent_factory.create_agent('emi_agent', DI.global_blackboard)
    ServiceLocator.register('emi_agent', emi_agent)
    print("\n\n")

    print("\n\nLoading emi_audio_agent:")
    emi_agent = DI.agent_factory.create_agent('emi_audio_agent', DI.global_blackboard)
    ServiceLocator.register('emi_audio_agent', emi_agent)
    print("\n\n")

    print("\n\nLoading team_selector_manager")
    team_selector_manager = multi_agent_manager_factory.create_manager("team_selector_manager")
    ServiceLocator.register('team_selector_manager', team_selector_manager)

    print("\n\nLoading emi_result_handler:")
    emi_result_handler = DI.agent_factory.create_agent('emi_result_handler', DI.global_blackboard)
    ServiceLocator.register('emi_result_handler', emi_result_handler)

    print("\n\nLoading emi_reminder_handler:")
    emi_reminder_handler = DI.agent_factory.create_agent('emi_reminder_handler', DI.global_blackboard)
    ServiceLocator.register('emi_reminder_handler', emi_reminder_handler)

    print("\n\nLoading ask_user:")
    ask_user = DI.agent_factory.create_agent('ask_user', DI.global_blackboard)
    ServiceLocator.register('ask_user', ask_user)

    print("\n\nLoading notify_user:")
    notify_user = DI.agent_factory.create_agent('notify_user', DI.global_blackboard)
    ServiceLocator.register('notify_user', notify_user)

    maintenance_manager = MaintenanceManager()
    ServiceLocator.register('maintenance_manager', maintenance_manager)

    # SlackInterface automatic polling
    slack_interface = SlackInterface()
    ServiceLocator.register("slack_interface", slack_interface)
    print("Running slack_interface")

    logger.info(f"Active threads count at end of initialize: {threading.active_count()}")
    print(f"Active threads count at end of initialize: {threading.active_count()}")


    # SystemStateMonitor automatic runs (autoplanner)
    system_state_monitor = SystemStateMonitor()
    ServiceLocator.register("system_state_monitor", system_state_monitor)
    print("Initialized system_state_monitor")

    return
