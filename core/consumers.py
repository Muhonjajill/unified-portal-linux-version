import json
from channels.generic.websocket import AsyncWebsocketConsumer
from django.utils.timezone import localtime
from channels.db import database_sync_to_async  


class EscalationConsumer(AsyncWebsocketConsumer):
    group_name = "escalations"

    async def connect(self):
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self._send_latest()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def escalation_update(self, event):
        await self._send_latest()

    async def _send_latest(self):
        tickets = await self._get_latest_tickets()   
        payload = [{
            "id": t.id,
            "title": t.title,
            "priority": (t.priority or "").title(),
            "escalated_at": localtime(t.escalated_at).strftime("%Y-%m-%d %H:%M"),
        } for t in tickets]
        await self.send(text_data=json.dumps({"tickets": payload}))

    @database_sync_to_async
    def _get_latest_tickets(self):
        from .models import Ticket
        return list(Ticket.objects.filter(is_escalated=True).order_by("-escalated_at")[:10])

    async def escalation_message(self, event):
        await self.send(text_data=json.dumps(event["message"]))

    async def escalate_ticket(self, event):
        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "escalation_message",
                "message": {
                    "type": "escalation",
                    "ticket_id": event["ticket_id"],
                    "title": event["title"],
                    "priority": (event.get("priority") or "").title(),
                    "escalated_at": event["escalated_at"],
                }
            }
        )