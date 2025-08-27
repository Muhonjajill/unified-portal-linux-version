import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils.timezone import localtime
from .models import Ticket

class EscalationConsumer(AsyncWebsocketConsumer):
    group_name = "escalations"

    async def connect(self):
        # Join group and send the latest escalations immediately
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send_latest_escalations()

    async def disconnect(self, close_code):
        # Leave group
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def send_latest_escalations(self):
        tickets = await self._get_latest_tickets()
        payload = [
            {
                "id": t.id,
                "title": t.title,
                "priority": (t.priority or "").title(),
                "escalated_at": localtime(t.escalated_at).strftime("%Y-%m-%d %H:%M"),
            }
            for t in tickets
        ]
        # Use send() with json.dumps()
        await self.send(text_data=json.dumps({"tickets": payload}))

    @database_sync_to_async
    def _get_latest_tickets(self):
        # Fetch the 5 most recent escalated tickets
        return list(
            Ticket.objects
                  .filter(is_escalated=True)
                  .order_by("-escalated_at")[:5]
        )

    async def escalation_update(self, event):
        """
        Handler for broadcasts of type 'escalation.update'.
        Re-fetches and sends down the full latest 5 escalations.
        """
        await self.send_latest_escalations()

    async def ticket_creation(self, event):
        """
        Handler for broadcasts of type 'ticket.creation'.
        Sends a single new-ticket notification.
        """
        ticket = event["ticket"]
        # Use send() with json.dumps()
        await self.send(text_data=json.dumps({
            "type": "ticket_creation",
            "ticket_id": ticket["id"],
            "title": ticket["title"],
            "priority": ticket["priority"].title(),
            "created_at": ticket["created_at"],
        }))
    
    # Add handler for 'escalation_message' type
    async def escalation_message(self, event):
        """
        Handler for 'escalation_message' type. This can be used to process specific escalation messages
        if needed.
        """
        # Process the incoming message (event) and send a response
        await self.send(text_data=json.dumps({
            "type": "escalation_message",
            "message": event["message"]
        }))
