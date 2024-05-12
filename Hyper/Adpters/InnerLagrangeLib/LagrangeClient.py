from lagrange.client.client import Client
from lagrange.client.events.group import GroupMessage

client: Client
msg_history: dict[int, GroupMessage] = {}
