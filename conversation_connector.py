import aiohttp
import asyncio
import httpx
import json
import urllib

from conversation_creator import ConversationCreator
from chathub_request_constructor import ChathubRequestConstructor
from message_parser import MessageParser
from logger.logger import logger


http_proxy = "http://localhost:11111"  # Replace with yours


class ConversationConnectRequestHeadersConstructor:
    def __init__(self):
        self.construct()

    def construct(self):
        self.request_headers = {
            "Accept-Encoding": " gzip, deflate, br",
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
            "Cache-Control": "no-cache",
            "Connection": "Upgrade",
            "Host": "sydney.bing.com",
            "Origin": "https://www.bing.com",
            "Pragma": "no-cache",
            "Sec-Websocket-Extensions": "permessage-deflate; client_max_window_bits",
            "Sec-Websocket-Version": "13",
            "Upgrade": "websocket",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
        }


class ConversationConnector:
    def __init__(
        self,
        conversation_style="precise",
        sec_access_token=None,
        client_id=None,
        conversation_id=None,
        invocation_id=0,
        cookies={},
    ):
        self.conversation_style = conversation_style
        self.sec_access_token = sec_access_token
        self.quotelized_sec_access_token = urllib.parse.quote(self.sec_access_token)
        self.client_id = client_id
        self.conversation_id = conversation_id
        self.invocation_id = invocation_id
        self.cookies = cookies
        self.ws_url = (
            f"wss://sydney.bing.com/sydney/ChatHub"
            f"?sec_access_token={self.quotelized_sec_access_token}"
        )

    async def wss_send(self, message):
        serialized_websocket_message = json.dumps(message, ensure_ascii=False) + "\x1e"
        await self.wss.send_str(serialized_websocket_message)

    async def init_handshake(self):
        await self.wss_send({"protocol": "json", "version": 1})
        await self.wss.receive_str()
        await self.wss_send({"type": 6})

    async def init_wss_connection(self):
        self.aiohttp_session = aiohttp.ClientSession(cookies=self.cookies)
        request_headers_constructor = ConversationConnectRequestHeadersConstructor()
        self.wss = await self.aiohttp_session.ws_connect(
            self.ws_url,
            headers=request_headers_constructor.request_headers,
            proxy=http_proxy,
        )
        await self.init_handshake()

    async def send_chathub_request(self, prompt):
        chathub_request_constructor = ChathubRequestConstructor(
            prompt=prompt,
            conversation_style=self.conversation_style,
            client_id=self.client_id,
            conversation_id=self.conversation_id,
            invocation_id=self.invocation_id,
        )
        self.connect_request_payload = chathub_request_constructor.request_payload
        await self.wss_send(self.connect_request_payload)

    async def stream_chat(self, prompt=""):
        await self.init_wss_connection()
        await self.send_chathub_request(prompt)

        message_parser = MessageParser()
        while not self.wss.closed:
            response_lines_str = await self.wss.receive_str()

            if isinstance(response_lines_str, str):
                response_lines = response_lines_str.split("\x1e")
            else:
                continue

            for line in response_lines:
                if not line:
                    continue

                data = json.loads(line)

                # Stream: Meaningful Messages
                if data.get("type") == 1:
                    message_parser.parse(data)
                # Stream: List of all messages in the whole conversation
                elif data.get("type") == 2:
                    if data.get("item"):
                        item = data.get("item")
                        logger.note("\n[Saving chat messages ...]")
                # Stream: End of Conversation
                elif data.get("type") == 3:
                    logger.success("[Finished]")
                    self.invocation_id += 1
                    await self.wss.close()
                    await self.aiohttp_session.close()
                    break
                # Stream: Heartbeat Signal
                elif data.get("type") == 6:
                    continue
                # Stream: Not Monitored
                else:
                    continue
