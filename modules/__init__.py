import lib
from modules import Chat, DataBaseManager, Memes, GroupManager, WebsiteServices, Alert, Welcome, Info

funcs: list[type(lib)] = \
    [Chat,
     DataBaseManager,
     Memes,
     GroupManager,
     WebsiteServices,
     Alert,
     Welcome,
     Info
     ]
