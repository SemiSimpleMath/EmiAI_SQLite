# stages/wellness_ticket_processor_stage.py
"""
Wellness Ticket Processor Stage

This stage runs early in the pipeline to process accepted wellness tickets.
It reads tickets that have been accepted but not yet processed, maps the
ticket's suggestion_type to a tracked activity, records it, and marks the
ticket as processed.

This keeps the ticket system clean (just CRUD/state) and the health pipeline
handles all wellness-related side effects.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from app.assistant.utils.logging_config import get_logger
from app.assistant.day_flow_manager.manager import BaseStage, StageContext, StageResult

logger = get_logger(__name__)


class WellnessTicketProcessorStage(BaseStage):
    """
    Pipeline stage that processes accepted wellness tickets.
    
    Flow:
    1. Query for accepted tickets where is_wellness_ticket=1 and effects_processed=0
    2. For each ticket, record occurrence for suggestion_type via activity_recorder
    3. Mark ticket as effects_processed=1
    4. Write summary to output resource
    """

    stage_id: str = "wellness_ticket_processor"

    def _output_filename(self) -> str:
        return f"resource_{self.stage_id}_output.json"

    def run(self, ctx: StageContext) -> StageResult:
        """Process unprocessed wellness tickets."""
        now_utc = datetime.now(timezone.utc)
        logger.debug("WellnessTicketProcessorStage: entering run()")
        
        processed_tickets = self._process_pending_wellness_tickets(ctx, now_utc)
        
        # Build output
        output = {
            "last_run_utc": now_utc.isoformat(),
            "tickets_processed": len(processed_tickets),
            "processed_details": processed_tickets,
        }
        
        # Write output resource
        ctx.write_resource(self._output_filename(), output)
        
        if processed_tickets:
            logger.info(f"✅ Processed {len(processed_tickets)} wellness tickets")
        
        return StageResult(
            output=output,
            debug={"tickets_processed": len(processed_tickets)},
        )

    def _process_pending_wellness_tickets(self, ctx: StageContext, now_utc: datetime) -> List[Dict[str, Any]]:
        """
        Find and process all accepted wellness tickets that haven't been processed yet.
        
        Returns list of processed ticket summaries.
        """
        from app.assistant.day_flow_manager.activity_recorder import ActivityRecorder
        from app.assistant.ticket_manager import get_ticket_manager
        
        processed: List[Dict[str, Any]] = []
        recorder = ActivityRecorder(ctx.state)
        manager = get_ticket_manager()

        tickets = manager.claim_accepted_tickets(ticket_type="wellness")
        logger.debug(
            "WellnessTicketProcessorStage: claimed accepted tickets count=%d ids=%s",
            len(tickets),
            [getattr(t, "ticket_id", None) for t in tickets],
        )
        for ticket in tickets:
            logger.debug(
                "WellnessTicketProcessorStage: processing ticket id=%s suggestion_type=%s responded_at=%s state=%s",
                getattr(ticket, "ticket_id", None),
                getattr(ticket, "suggestion_type", None),
                getattr(ticket, "responded_at", None),
                getattr(ticket, "state", None),
            )
            ticket_summary = {
                "ticket_id": ticket.ticket_id,
                "suggestion_type": ticket.suggestion_type,
                "activities_recorded": [],
            }

            activity_name = ticket.suggestion_type
            if not activity_name:
                logger.warning(f"Wellness ticket {ticket.ticket_id} has no suggestion_type; skipping.")
                logger.debug(
                    "WellnessTicketProcessorStage: skip ticket id=%s reason=missing_suggestion_type",
                    ticket.ticket_id,
                )
                manager.set_ticket_processed_state(ticket.id, 1)
                processed.append(ticket_summary)
                continue
            if activity_name not in recorder._defs:
                logger.debug(
                    "WellnessTicketProcessorStage: skip ticket id=%s reason=not_tracked activity=%s",
                    ticket.ticket_id,
                    activity_name,
                )
                manager.set_ticket_processed_state(ticket.id, 1)
                processed.append(ticket_summary)
                logger.debug(
                    f"WellnessTicketProcessor: non-tracked ticket processed {ticket.ticket_id} ({activity_name})"
                )
                continue

            responded_at = ticket.responded_at or now_utc
            logger.debug(
                "WellnessTicketProcessorStage: recording occurrence activity=%s responded_at=%s",
                activity_name,
                responded_at,
            )

            recorder.record_occurrence(
                activity_name,
                timestamp_utc=responded_at,
                increment_count=True,
            )
            ticket_summary["activities_recorded"].append(activity_name)
            logger.debug(
                f"WellnessTicketProcessor: recorded {activity_name} for {ticket.ticket_id} at {responded_at.isoformat()}"
            )

            manager.set_ticket_processed_state(ticket.id, 1)
            processed.append(ticket_summary)
            logger.debug(f"Processed wellness ticket {ticket.ticket_id}: {ticket_summary['activities_recorded']}")

        if processed:
            recorder.write_output_resource(now_utc=now_utc)

        return processed

    def reset_daily(self, ctx: StageContext) -> None:
        """No daily reset needed for this stage."""
        pass
