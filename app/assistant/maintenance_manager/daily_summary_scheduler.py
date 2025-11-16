from datetime import datetime, timezone
from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.utils.pydantic_classes import Message
from app.assistant.utils.logging_config import get_maintenance_logger
from app.assistant.maintenance_manager.daily_summary_storage import DailySummaryStorage

logger = get_maintenance_logger(__name__)

class DailySummaryScheduler:
    """
    Handles the daily summary generation at 7am every morning.
    """
    
    def __init__(self):
        self.factory = DI.multi_agent_manager_factory
        self.storage = DailySummaryStorage()
    
    def run_daily_summary(self):
        """
        Generate the daily summary using the daily_summary_manager.
        This is called by the scheduler every morning at 7am.
        """
        try:
            logger.info("🕖 Starting daily summary generation...")
            
            # Preload all managers to ensure they're available
            manager_registry = DI.manager_registry

            # Create the daily summary manager
            manager = self.factory.create_manager('daily_summary_manager')
            
            # Create the initial message
            message = Message(
                data_type="agent_activation",
                sender="Daily Summary Scheduler",
                receiver="Delegator",  # This kicks off the agent loop
                content="Generate daily summary",
                task="Generate comprehensive daily summary including calendar events, todo tasks, and scheduling recommendations."
            )
            
            # Run the manager using request_handler
            result = manager.request_handler(message)
            
            # Extract the actual data from the ToolResult
            if hasattr(result, 'data') and result.data is not None:
                summary_data = result.data
            else:
                # Fallback to content if data is not available
                summary_data = result.content if hasattr(result, 'content') else result
            
            # Save the result to storage
            try:
                saved_path = self.storage.save_daily_summary(summary_data)
                logger.info(f"💾 Daily summary saved to: {saved_path}")
            except Exception as save_error:
                logger.error(f"❌ Failed to save daily summary: {save_error}")

            logger.info("✅ Daily summary generated successfully")
            logger.info(f"📊 Summary result: {result}")
            
            return {
                "success": True,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "result": result,
                "saved_path": saved_path if 'saved_path' in locals() else None
            }
            
        except Exception as e:
            logger.error(f"❌ Error generating daily summary: {e}")
            return {
                "success": False,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": str(e)
            }


if __name__ == "__main__":
    import app.assistant.tests.test_setup # This is just run for the import
    logger.info("initialize_system() is running...")
    print("inintialize system...")
    factory = DI.multi_agent_manager_factory


    manager_registry = DI.manager_registry
    manager_registry.preload_all()

    daily_summary_scheduler = DailySummaryScheduler()
    daily_summary_scheduler.run_daily_summary()