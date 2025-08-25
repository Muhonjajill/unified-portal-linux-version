#escalation_rules.py
from django.utils import timezone  # ✅ correct

#from core.models import EscalationHistory
from django.core.mail import send_mail
from django.conf import settings

# core/utilss/escalation_rules.py
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


CATEGORY_TO_ESCALATION_TYPE = {
    'software': 'technical outage',
    'software update': 'technical outage',
    'hardware error': 'technical outage',
    'network and connection error': 'technical outage',
    'installation and configuration': 'technical outage',
    'repair': 'technical outage',
    'maintenance': 'technical outage',
    'preventive maintenance': 'technical outage',
    'cybersecurity': 'cybersecurity incident',
    'complaint': 'client complaint',
    'sla breach': 'sla breach',
    'other': 'technical outage',
}

ESCALATION_MATRIX = {
    'technical outage': {
        'low': "Tier 1 handles. Escalates to Tier 2 if unresolved in 8 hours. Director alerted.",
        'medium': "Tier 1 updates every 2 hrs. Escalates to Director + Country Manager after 2 hrs.",
        'high': "Auto-escalated. Support alerts Director immediately. MD is briefed.",
        'critical': '"All-hands" mode. Director leads, MD oversees. War room initiated.',
    },
    'cybersecurity incident': {
        'low': "Support investigates. Escalates to Director if compliance risk suspected.",
        'medium': "Escalated to Director and Country Manager. Risk assessment begins.",
        'high': "Protocol triggered. Director and MD notified. Forensics initiated.",
        'critical': "Full incident response team. MD leads client/regulator comms. 24/7 bridge opened.",
    },
    'client complaint': {
        'low': "Handled by Support. Logged as feedback.",
        'medium': "Escalated to Country Manager. Director informed.",
        'high': "Country Manager + Director involved. MD briefed.",
        'critical': "MD and Director lead full service review. All teams mobilized.",
    },
    'sla breach': {
        'low': "Director investigates. Engineer resolves.",
        'medium': "Director investigates. Country Manager briefed.",
        'high': "Director starts RCA. MD informed.",
        'critical': "MD leads executive intervention. Recovery roadmap created.",
    }
}

TIER_MAPPING = {
    'low': 'Tier 1',
    'medium': 'Tier 2',
    'high': 'Tier 3',
    'critical': 'Tier 4',
}

ESCALATION_FLOW = {
    'Tier 1': 'Tier 2',
    'Tier 2': 'Tier 3',
    'Tier 3': 'Tier 4',
    'Tier 4': None,
}

def escalate_ticket(ticket):
    from core.models import EscalationHistory
    from .escalation_rules import send_escalation_email

    # Get the current escalation level, default to 'Tier 1'
    current_level = ticket.current_escalation_level or 'Tier 1'

    # Get the next escalation level based on the current level
    next_level = ESCALATION_FLOW.get(current_level)

    # If no next level is found, we can't escalate further
    if not next_level:
        print(f"Ticket {ticket.id} is already at the highest escalation level: {current_level}")
        return  # Stop here if we can't escalate further

    # Now print after assigning next_level
    print(f"Escalating Ticket {ticket.id} from {current_level} to {next_level}")

    # Proceed with the escalation
    ticket.current_escalation_level = next_level
    ticket.is_escalated = True
    ticket.escalated_at = timezone.now()
    ticket.save()

    # Send WebSocket notification
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        "escalations",
        {
            "type": "escalation_message",
            "message": {
                "id": ticket.id,
                "title": ticket.title,
                "priority": ticket.priority,
                "escalated_at": ticket.escalated_at.strftime("%Y-%m-%d %H:%M"),
            },
        }
    )

    # Log escalation history
    EscalationHistory.objects.create(
        ticket=ticket,
        escalated_by=None,  # System triggered
        from_level=current_level,
        to_level=next_level,
        note=f"Auto-escalated due to time threshold for priority '{ticket.priority}'."
    )

    # Send escalation email
    send_escalation_email(ticket, next_level)


def get_escalation_recipients(level):
    
    emails = settings.ESCALATION_LEVEL_EMAILS.get(level)
    if emails:
        return list(emails)  # convert tuple to list for send_mail
    return [settings.DEFAULT_FROM_EMAIL]

def get_email_for_level(level):
    return [settings.ESCALATION_LEVEL_EMAILS.get(level, (None,))[0]]  # Returns list

def send_escalation_email(ticket, to_level):
    subject = f"[Escalation Notice] Ticket #{ticket.id} escalated to {to_level}"
    message = f"""
    Ticket ID: {ticket.id}
    Title: {ticket.title}
    Priority: {ticket.priority}
    Category: {ticket.problem_category}
    New Escalation Level: {to_level}
    Status: {ticket.status}
    Created At: {ticket.created_at}

    This ticket has been auto-escalated based on your escalation policy.

    Please log in to review.

    - Blue River Technology Solutions
    """
    recipients = get_escalation_recipients(to_level)
    send_mail(subject, message, None, recipients)