#escalation_rules.py
from django.utils import timezone  # ✅ correct
from datetime import timedelta
from core.models import Zone
from core.models import EscalationHistory



#from core.models import EscalationHistory
from django.core.mail import send_mail
from django.conf import settings

# core/utilss/escalation_rules.py
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from core.uttils.serializers import serialize_ticket

import logging

# Initialize the logger
logger = logging.getLogger(__name__)


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

CATEGORY_TO_ESCALATION_TYPE = {
    'Hardware Related': 'technical outage',
    'Software Related': 'technical outage',
    'Cash Reconciliation': 'technical outage',
    'Power and Network': 'technical outage',
    'De-/Installation /Maintenance': 'technical outage',
    'Safe': 'technical outage',
    'SLA Related': 'SLA Breach',
    'Other': 'Client Complaint'
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

def send_unassigned_ticket_notification(ticket):
    """Send periodic notifications if ticket is not assigned within the threshold."""
    now = timezone.now()

    # Notification condition if the ticket is unassigned
    if not ticket.assigned_to and now >= ticket.created_at + timedelta(minutes=2):
        # Send a WebSocket notification to inform users about unassigned tickets
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            "escalations",  # Group name
            {
                "type": "unassigned_ticket_notification",
                "ticket": serialize_ticket(ticket),  
            }
        )


def send_ticket_assignment_notification(ticket):
    """Send notification to admins or assigned staff to assign the ticket."""
    message = f"Ticket #{ticket.id} is not assigned yet. Please assign it within 2 hours."
    send_mail("Unassigned Ticket Reminder", message, None, [settings.ADMIN_EMAIL])

    # WebSocket notification
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        "ticket_notifications",
        {"type": "ticket_assignment_notification", "message": message}
    )

""" 
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

"""

def escalate_ticket(ticket):
    """Escalate ticket based on its zone and priority."""
    now = timezone.now()
    escalation_time = None
    escalation_level = ticket.current_escalation_level or 'Tier 1'

    # Check if zone is defined
    if not ticket.zone:
        logger.warning(f"Ticket {ticket.id} has no zone defined. Assigning default zone 'A'.")
        try:
            # Attempt to fetch the Zone instance by label
            ticket.zone = Zone.objects.get(name='Zone A')  # Adjust as needed for dynamic zones
        except Zone.DoesNotExist:
            # Create the zone if it doesn't exist
            ticket.zone = Zone.objects.create(name='Zone A')  # Default zone creation if not found

    # Log ticket details before escalation
    logger.debug(f"Escalating Ticket {ticket.id}: Current Level: {escalation_level}, Priority: {ticket.priority}, Zone: {ticket.zone.name}")

    # Set escalation time based on the zone
    if ticket.zone.name == 'Zone A':
        escalation_time = timedelta(minutes=5)
    elif ticket.zone.name == 'Zone B':
        escalation_time = timedelta(minutes=10)
    elif ticket.zone.name == 'Zone C':
        escalation_time = timedelta(minutes=15)

    if not escalation_time:
        logger.info(f"Ticket {ticket.id} has no defined escalation time based on zone {ticket.zone.name}. No escalation.")
        return  # No escalation for unknown zones

    # Log when we are checking the escalation time condition
    logger.debug(f"Ticket {ticket.id}: Created at {ticket.created_at}. Checking if it exceeds {ticket.created_at + escalation_time}. Now: {now}")
    
    if now >= ticket.created_at + escalation_time:
        logger.info(f"Ticket {ticket.id} exceeds escalation time. Proceeding with escalation.")

        # Escalate based on the priority and zone
        next_level = None
        if ticket.priority == 'critical':
            if escalation_level == 'Tier 3':
                next_level = 'Tier 4'  # Directly set next level for critical priority
            else:
                next_level = ESCALATION_FLOW.get(escalation_level)  # Check for next level if not critical
        else:
            next_level = ESCALATION_FLOW.get(escalation_level)  # Get next level for non-critical priorities

        if next_level:
            # Log the level change
            logger.info(f"Ticket {ticket.id} escalated from {ticket.current_escalation_level} to {next_level}")

            # Save the escalation changes
            ticket.current_escalation_level = next_level
            ticket.is_escalated = True
            ticket.escalated_at = now
            ticket.save()

            # Send escalation email
            send_escalation_email(ticket, next_level)

            # Log escalation history
            EscalationHistory.objects.create(
                ticket=ticket,
                from_level=escalation_level,
                to_level=next_level,
                note=f"Auto-escalated based on zone {ticket.zone.name} and priority {ticket.priority}."
            )
        else:
            logger.info(f"Ticket {ticket.id} cannot be escalated further, already at the highest level.")

    else:
        logger.info(f"Ticket {ticket.id} has not yet exceeded escalation time. No escalation needed.")


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