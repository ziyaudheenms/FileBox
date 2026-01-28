import json
from channels.generic.websocket import AsyncWebsocketConsumer

class FileUpdateConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        print("WebSocket connection attempt")
        self.user = self.scope.get("user")
        if self.user:
            print("websocket room to be created for the user:" , self.user.pk)
            self.group_name = f'file_updates_{self.user.pk}'   #creating private group for each user
            await self.channel_layer.group_add(self.group_name , self.channel_name)
            await self.accept()
        else:
            print("error is persisting here")
            await self.close()
    
    async def disconnect(self , close_code): # in the 'close_code' django automatically sets the code for disconnection of the websocket
        await self.channel_layer.group_discard(self.group_name , self.channel_name)

    async def send_file_update(self, event):

        print("trying to send real time update to the frontend")
        payload = {
            "file_id" : event.get("file_id"),
            "status" : event.get("status"),
            "file_url" : event.get("file_url"),
        }
        await self.send(text_data=json.dumps(payload))

    # async def receive(self, text_data):
    #     data = json.loads(text_data)
    #     if data.get('type') == 'ping':
    #         # Optional: Send a pong back to the client
    #         await self.send(text_data=json.dumps({"type": "pong"}))