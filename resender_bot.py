import sqlite3
from datetime import datetime

import asyncio
import time
from telethon import TelegramClient, events
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest, GetHistoryRequest, GetDialogsRequest
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.errors.rpcerrorlist import InviteRequestSentError, FloodWaitError, InviteHashExpiredError
from telethon.tl.types import InputPeerEmpty, InputPeerUser
from telethon.types import Channel, Chat
from telethon.errors import SessionPasswordNeededError

class TelegramSender:
    def __init__(self, api_id, api_hash, session_file, proxy_ip, proxy_port, proxy_login, proxy_password, app_version, device, chat_id):
        self.api_id = api_id
        self.api_hash = api_hash
        self.proxy = {
                    'proxy_type': 'socks5',
                    'addr': proxy_ip,
                    'port': proxy_port,
                    'username': proxy_login,
                    'password': proxy_password,
                    'rdns': True
                }
        self.session_file = session_file
        self.app_version = app_version
        self.device = device
        self.client = TelegramClient(self.session_file, self.api_id, self.api_hash, proxy=self.proxy,app_version=self.app_version, device_model=self.device)
        self.chat_id = chat_id
        self.db = sqlite3.connect('messages.db')

    async def get_last_message_id(self, dialog_id):
        cursor = self.db.cursor()
        cursor.execute("SELECT last_message_id FROM last_messages WHERE dialog_id = ?", (dialog_id,))
        result = cursor.fetchone()
        return result[0] if result else 0

    async def update_last_message_id(self, dialog_id, last_message_id):
        print(f'сохранил в бд {dialog_id} {last_message_id}')
        cursor = self.db.cursor()
        cursor.execute("REPLACE INTO last_messages (dialog_id, last_message_id) VALUES (?, ?)", (dialog_id, last_message_id))
        self.db.commit()

    async def client_authorized(self):
        await self.client.connect()
        authorized = await self.client.is_user_authorized()
        await self.client.disconnect()
        return authorized

    async def start(self):
        if await self.client_authorized():
            await self.client.start()
        else:
            raise SessionPasswordNeededError('Сессия не авторизована')

    async def stop(self):
        await self.client.disconnect()

    async def check_chat(self):
        chat = await self.client.get_entity(self.chat_id)
        await self.client.send_message(chat, '*Тестовое сообщение*', parse_mode='Markdown')

    async def subscribe_to_chat(self, url):
        chat_urls = url.split('\n')
        for uri in chat_urls:
            try:
                chat_name = await self.client.get_entity(uri)
            except:
                chat_name = uri.split('/')[-1]
                if chat_name[0] == '+' or chat_name[0] == '-':
                    chat_name = chat_name[1:]
                print(chat_name)
            try:
                await self.client(JoinChannelRequest(chat_name))
            except ValueError:
                await self.client(ImportChatInviteRequest(chat_name))
            except InviteRequestSentError as e:
                print(e)
            except FloodWaitError:
                await asyncio.sleep(30)
            except InviteHashExpiredError:
                pass

            await asyncio.sleep(10)
        return len(chat_urls)

    async def get_dialogs(self, chat_entity):
        current_dialogs = await self.client(GetDialogsRequest(
            offset_date=None,
            offset_id=0,
            offset_peer=InputPeerEmpty(),
            limit=200,
            hash=0,
        ))
        dialogs = []
        
        for dialog in current_dialogs.chats:
            if (isinstance(dialog, Channel) or isinstance(dialog, Chat)) and dialog != chat_entity:
                dialogs.append(dialog)
        return dialogs

    async def get_chat_url(self):
        pass

    async def new_message_handler(self):
        chat_entity = await self.client.get_entity(self.chat_id)
        while True:
            try:
                conn = sqlite3.connect('messages.db')
                cursor = conn.cursor()
                now = datetime.now()
                session_name = self.session_file.split('/')[1]
                if now.minute >= 0 and now.minute <= 1:
                    cursor.execute("SELECT chat_url FROM chats WHERE session_filename = ?", (session_name,))
                    result = cursor.fetchall()
                    if len(result) > 0:
                        print('Подписываюсь на ', result[0][0])
                        url = result[0][0]
                        try:
                            await self.subscribe_to_chat(url)
                        except:
                            pass
                        finally:
                            cursor.execute("DELETE FROM chats WHERE chat_url = ?", (url,))
                        conn.commit()
                    else:
                        pass
                    
                else:
                    pass

                dialogs = await self.get_dialogs(chat_entity)
                
                query = """
                        UPDATE accounts
                        SET count_chats = ?
                        WHERE session_filename = ?
                        """
                
                cursor.execute(query, (len(dialogs), session_name))
                conn.commit()
                cursor.execute("SELECT keyword FROM accounts WHERE session_filename = ?", (session_name,))
                result = cursor.fetchone()
                if result[0] == None:
                    keywords = []
                elif result[0] == '*':
                    keywords = []
                else:
                    keywords = result[0].split('\n')
                    print(keywords)
                print(keywords)
                conn.close()
                for dialog in dialogs:
                    last_message_id = await self.get_last_message_id(dialog.id)
                    messages = await self.client(GetHistoryRequest(
                        peer=dialog,
                        limit=1,
                        offset_date=None,
                        offset_id=0,
                        max_id=0,
                        min_id=0,
                        add_offset=0,
                        hash=0
                    ))

                    if messages.messages:
                        last_message = messages.messages[0]
                        # print(last_message)
                        if last_message.id != last_message_id:
                            try:
                                message_text = str(last_message.message).lower()
                                if keywords != []:
                                    if any(keyword.strip() in message_text for keyword in keywords):
                                        await self.client.forward_messages(self.chat_id, [last_message.id], dialog.id)
                                        await self.update_last_message_id(dialog.id, last_message.id)
                                else:
                                    await self.client.forward_messages(self.chat_id, [last_message.id], dialog.id)
                                    await self.update_last_message_id(dialog.id, last_message.id)
                                
                                await self.client.send_message(self.chat_id, f'https://t.me/c/{dialog.id}/{last_message.id}')
                                
                            except Exception as e:
                                print(e)
            except ConnectionError:
                print('остановил пересылку')
                break
            except Exception as e:
                print(e)
            await asyncio.sleep(30)

async def main():
    proxy = {
        'proxy_type': 'socks5',
        'addr': '185.66.12.171',
        'port': 49155,
        'username': 'tka4enko_D',
        'password': ':SdgvE7SR5J',
        'rdns': True
    }
    api_id =  "23173432"
    api_hash = '69985de08428ef336082a1f8f3f24663'
    tg_bot = TelegramSender(api_id=api_id, api_hash=api_hash, session_file='sessions/639510002411.session', proxy_ip='185.66.12.171', proxy_login='tka4enko_D', proxy_password='SdgvE7SR5J', proxy_port=49155, app_version='3.4.3 x64', device='Accent Pearl A4', chat_id=int('-973800427'))
    await tg_bot.start()
    await tg_bot.new_message_handler()
    # await tg_bot.subscribe_to_chat('https://t.me/QuizPleaseMia')

if __name__ == "__main__":
    asyncio.run(main())


    