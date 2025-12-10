# app/bootstrap.py
from pathlib import Path

from app.assistant.agent_registry.agent_factory import AgentFactory
from app.assistant.agent_registry.agent_registry import AgentRegistry
from app.assistant.lib.tool_registry.tool_registry import ToolRegistry
from app.assistant.manager_registry.manager_registry import ManagerRegistry
from app.assistant.multi_agent_manager_factory.MultiAgentManagerFactory import MultiAgentManagerFactory
from app.assistant.lib.data_conversion_module.DataConversion import DataConversionModule
from app.assistant.global_blackboard.global_blackboard import GlobalBlackBoard
from app.resource_manager.resource_manager import ResourceManager
from app.assistant.ServiceLocator.service_locator import ServiceLocator, DI

from app.assistant.scheduler.orchestrator.scheduler_service import SchedulerService

config_path = "app/assistant/scheduler/config/events_config.yaml"
from app.assistant.utils.logging_config import get_logger
logger = get_logger(__name__)

from app.assistant.event_handler_hub.event_handler_hub import EventHandlerHub

def initialize_services(app):
    """
    Initializes core services like event bus, agent managers, data conversion, and scheduler.
    """

    event_hub =EventHandlerHub()
    ServiceLocator.register('event_hub', event_hub)

    # Register user settings manager
    from app.assistant.user_settings_manager.user_settings import UserSettingsManager
    user_settings = UserSettingsManager()
    ServiceLocator.register('user_settings', user_settings)
    logger.info("✅ User settings manager initialized")

    ServiceLocator.register('agent_registry', AgentRegistry())
    ServiceLocator.register('tool_registry', ToolRegistry())
    DI.tool_registry.load_tools()
    DI.agent_registry.load_agents()
    ServiceLocator.register('agent_factory', AgentFactory(agent_registry=DI.agent_registry, tool_registry=DI.tool_registry))
    base_path = Path(__file__).resolve().parents[0] / "assistant" / "multi_agents"
    manager_registry = ManagerRegistry(base_path)
    ServiceLocator.register('manager_registry', manager_registry)
    manager_factory = MultiAgentManagerFactory()
    ServiceLocator.register("multi_agent_manager_factory", manager_factory)

    data_conversion_module = DataConversionModule()
    ServiceLocator.register("data_conversion_module", data_conversion_module)

    global_blackboard = GlobalBlackBoard()
    ServiceLocator.register("global_blackboard", global_blackboard)

    # Initialize ResourceManager and auto-load all resources
    resource_manager = ResourceManager()
    ServiceLocator.register("resource_manager", resource_manager)
    resource_manager.load_all_from_directory("resources")

    # Initialize Entity Catalog for fast entity detection
    from app.assistant.entity_management.entity_catalog import EntityCatalog
    entity_catalog = EntityCatalog.instance()
    ServiceLocator.register("entity_catalog", entity_catalog)
    logger.info("✅ Entity catalog initialized")

    # Initialize scheduler service (auto-starts via TimingEngine.__init__)
    # APScheduler's BackgroundScheduler runs in its own background threads automatically
    scheduler_service = SchedulerService(app)
    app.scheduler_service = scheduler_service
    ServiceLocator.register('scheduler', scheduler_service)


    print("✅ EventHandlerHub started in the background.")

    return DI
