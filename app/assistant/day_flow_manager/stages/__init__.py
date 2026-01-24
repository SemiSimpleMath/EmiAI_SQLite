"""
Pipeline Stages

Each stage implements BaseStage from manager.py:
- run(ctx) -> StageResult: Main stage logic
- reset_daily(ctx) -> None: Daily 5AM reset behavior
- get_stage_config(ctx) -> dict: Load stage's own config file

Processor stages (run first):
- WellnessTicketProcessorStage: Processes accepted wellness tickets

Computation stages:
- SleepStage: Computes sleep data from AFK events

Agent stages:
- ActivityTrackerStage: Detects activities from chat/calendar/tickets
- DailyContextGeneratorStage: Generates daily context summary
- HealthInferenceStage: Infers health/energy state
- DayFlowOrchestratorStage: Decides proactive suggestions

Note: AFK statistics is NOT a stage - it's part of the AFK manager subsystem
and updates its resource file directly when AFK state changes.
"""

from app.assistant.day_flow_manager.stages.agent_stage import AgentStage
from app.assistant.day_flow_manager.stages.wellness_ticket_processor_stage import WellnessTicketProcessorStage
from app.assistant.day_flow_manager.stages.sleep_stage import SleepStage
from app.assistant.day_flow_manager.stages.activity_tracker_stage import ActivityTrackerStage
from app.assistant.day_flow_manager.stages.daily_context_generator_stage import DailyContextGeneratorStage
from app.assistant.day_flow_manager.stages.health_inference_stage import HealthInferenceStage
from app.assistant.day_flow_manager.stages.day_flow_orchestrator_stage import DayFlowOrchestratorStage

__all__ = [
    'AgentStage',
    'WellnessTicketProcessorStage',
    'SleepStage',
    'ActivityTrackerStage',
    'DailyContextGeneratorStage',
    'HealthInferenceStage',
    'DayFlowOrchestratorStage',
]
