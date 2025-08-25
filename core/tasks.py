from celery import shared_task
from django.utils import timezone
from django.db import transaction
from datetime import timedelta

from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from core.utilss.escalation_constants import ESCALATION_TIME_LIMITS, ESCALATION_FLOW
from core.utilss.escalation_rules import escalate_ticket, send_escalation_email
from core.models import Ticket, EscalationHistory


def send_escalation_notification(ticket):
    """
    Broadcast a WebSocket notification to notify users about ticket escalation.
    """
    channel_layer = get_channel_layer()
    message = {
        "ticket_id": ticket.id,
        "title": ticket.title,
        "priority": ticket.priority,
        "escalated_at": ticket.escalated_at.strftime("%Y-%m-%d %H:%M") if ticket.escalated_at else "",
    }
    async_to_sync(channel_layer.group_send)(
        "escalations",
        {"type": "escalation_message", "message": message}
    )


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def run_auto_escalation(self):
    """
    Periodic task that escalates tickets automatically based on:
      - Critical: Tier 3 immediately, then Tier 4 after 5 minutes.
      - Non‐critical: first escalation after configured hours, then every 10 minutes.
    """
    now = timezone.now()
    tickets = Ticket.objects.filter(status__in=['open', 'in_progress'])

    for t in tickets:
        if not t.priority or not t.created_at:
            continue

        prio = t.priority.lower()

        # ——— CRITICAL ———
        if prio == 'critical':
            # 1) First: Tier 3 immediately
            if not t.escalated_at:
                with transaction.atomic():
                    t.refresh_from_db()
                    t.current_escalation_level = 'Tier 3'
                    t.is_escalated = True
                    t.escalated_at = now
                    t.save()

                    EscalationHistory.objects.create(
                        ticket=t,
                        from_level='Tier 1',
                        to_level='Tier 3',
                        note="1st escalation for critical priority"
                    )
                    send_escalation_notification(t)
                    send_escalation_email(t, 'Tier 3')
            # 2) After 5 minutes: Tier 4
            elif t.current_escalation_level == 'Tier 3' and now - t.escalated_at >= timedelta(minutes=5):
                with transaction.atomic():
                    t.refresh_from_db()
                    t.current_escalation_level = 'Tier 4'
                    t.escalated_at = now
                    t.save()

                    EscalationHistory.objects.create(
                        ticket=t,
                        from_level='Tier 3',
                        to_level='Tier 4',
                        note="2nd escalation for critical priority after 5 minutes"
                    )
                    send_escalation_notification(t)
                    send_escalation_email(t, 'Tier 4')
            continue  # done with critical

        # ——— NON‐CRITICAL ———
        threshold_hours = ESCALATION_TIME_LIMITS.get(prio)
        if threshold_hours is None:
            continue

        # 1) Initial escalation at creation + threshold_hours
        if not t.escalated_at and now - t.created_at >= timedelta(hours=threshold_hours):
            with transaction.atomic():
                t.refresh_from_db()
                escalate_ticket(t)
                t.escalated_at = now
                t.save()

                send_escalation_notification(t)
                # assume escalate_ticket logs history & sends initial emails
            continue  # skip the subsequent block until next run

        # 2) Subsequent escalations every 10 minutes
        if t.escalated_at and now - t.escalated_at >= timedelta(minutes=10):
            current = t.current_escalation_level or 'Tier 1'
            next_level = ESCALATION_FLOW.get(current)
            if next_level:
                with transaction.atomic():
                    t.refresh_from_db()
                    t.current_escalation_level = next_level
                    t.is_escalated = True
                    t.escalated_at = now
                    t.save()

                    EscalationHistory.objects.create(
                        ticket=t,
                        from_level=current,
                        to_level=next_level,
                        note="Subsequent escalation after 10 minutes"
                    )
                    send_escalation_notification(t)
                    send_escalation_email(t, next_level)