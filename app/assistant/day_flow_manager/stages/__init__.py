"""
Day Flow Pipeline Stages

Each stage implements BaseStage from day_flow_manager.py:
- run(ctx) -> StageResult: Main stage logic
- reset_stage(ctx) -> None: Daily boundary reset behavior
- should_run_stage(ctx) -> Tuple[bool, str]: Gate logic (optional)
- get_stage_config(ctx) -> dict: Load stage's own config file

Computation stages (no LLM cost):
- SleepStage: Computes sleep data, determines day_start
- AFKStatisticsStage: Computes AFK statistics
- ActivityTrackerStage: Updates tracked activity timers

Agent stages (call LLM):
- DailyContextGeneratorStage: Generates daily context summary
- HealthInferenceStage: Infers health/energy state
- DayFlowOrchestratorStage: Decides proactive suggestions
"""

from app.assistant.day_flow_manager.stages.agent_stage import AgentStage
from app.assistant.day_flow_manager.stages.sleep_stage import SleepStage
from app.assistant.day_flow_manager.stages.afk_statistics_stage import AFKStatisticsStage
from app.assistant.day_flow_manager.stages.activity_tracker_stage import ActivityTrackerStage
from app.assistant.day_flow_manager.stages.daily_context_generator_stage import DailyContextGeneratorStage
from app.assistant.day_flow_manager.stages.health_inference_stage import HealthInferenceStage
from app.assistant.day_flow_manager.stages.day_flow_orchestrator_stage import DayFlowOrchestratorStage

__all__ = [
    'AgentStage',
    'SleepStage',
    'AFKStatisticsStage',
    'ActivityTrackerStage',
    'DailyContextGeneratorStage',
    'HealthInferenceStage',
    'DayFlowOrchestratorStage',
]
