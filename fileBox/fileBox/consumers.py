import json
from channels.generic.websocket import AsyncWebsocketConsumer

class FileUpdateConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.user = self.scope.get("user")
        if self.user and self.user.is_authenticated:
            self.group_name = f'file_updates_{self.user.id}'   #creating private group for each user
            await self.channel_layer.group_add(self.group_name , self.channel_name)
            await self.accept()
        else:
            await self.close()
    
    async def disconnect(self):
        await self.channel_layer.group_discard(self.group_name , self.channel_name)

    async def send_file_update(self, event):
        payload = {
            "file_id" : event.get("file_id"),
            "status" : event.get("status"),
            "file_url" : event.get("file_url"),
        }
        await self.send(text_data=json.dumps(payload))