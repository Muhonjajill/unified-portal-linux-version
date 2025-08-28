import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.db.models.functions import Coalesce
from django.db.models import DateTimeField
from core.uttils.serializers import serialize_ticket
from .models import Ticket

class EscalationConsumer(AsyncWebsocketConsumer):
    group_name = "escalations"

    async def connect(self):
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send_latest()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def send_latest(self):
        tickets = await self._get_latest_tickets()
        payload = [serialize_ticket(t) for t in tickets]
        total = await self._get_total_count()
        await self.send(text_data=json.dumps({
            "type": "notifications_list",
            "tickets": payload,   
            "count": total,       
        }))

    @database_sync_to_async
    def _get_latest_tickets(self):
        return list(Ticket.objects.order_by("-created_at")[:5])


    @database_sync_to_async
    def _get_total_count(self):
        return Ticket.objects.count()


    async def escalation_update(self, event):
        # On escalation, refresh the list
        await self.send_latest()

    async def ticket_creation(self, event):
        t = event["ticket"]
        if isinstance(t, dict):
            payload = t
        else:
            ticket = await database_sync_to_async(Ticket.objects.get)(id=t)
            payload = serialize_ticket(ticket)

        # Send single new ticket event
        await self.send(text_data=json.dumps({
            "type": "ticket_creation",
            "ticket": payload,
        }))

    async def escalation_message(self, event):
        # Optional toast-like messages
        msg = event.get("message")
        await self.send(text_data=json.dumps({
            "type": "escalation_message",
            "message": msg if isinstance(msg, str) else json.dumps(msg),
        }))
