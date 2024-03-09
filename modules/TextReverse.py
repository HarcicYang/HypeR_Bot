from lib import Manager, Listener, Segments
import datetime


mapping = {
    "A": "∀", "a": "ɐ",
    "B": "Ɓ", "b": "q",
    "C": "Ɔ", "c": "ɔ",
    "D": "Ɗ", "d": "p",
    "E": "Ǝ", "e": "ǝ",
    "F": "Ⅎ", "f": "ɟ",
    "G": "פ", "g": "ƃ",
    "H": "H", "h": "ɥ",
    "I": "I", "i": "ᴉ",
    "J": "ſ", "j": "ɾ",
    "K": "Ʞ", "k": "ʞ",
    "L": "˥", "l": "l",
    "M": "Ɯ", "m": "ʍ",
    "N": "N", "n": "u",
    "O": "O", "o": "o",
    "P": "b", "p": "b",
    "Q": "b", "q": "b",
    "R": "ɹ", "r": "ɹ",
    "S": "S", "s": "s",
    "T": "┴", "t": "ʇ",
    "U": "Λ", "u": "n",
    "V": "Λ", "v": "ʌ",
    "W": "ʍ", "w": "ꭩ",
    "X": "X", "x": "x",
    "Y": "⅄", "y": "ʎ",
    "Z": "Z", "z": "z"
}


class ModuleClass:
    def __init__(self, actions: Listener.Actions, event: Manager.Event):
        self.actions = actions
        self.event = event

    async def handle(self):
        if self.event.blocked or self.event.servicing:
            return
        try:
            cmd = str(self.event.message)
        except AttributeError:
            return None

        if cmd.startswith(".reverse "):
            cmd = cmd.replace(".reverse ", "", 1)[::-1]

            for i in mapping:
                cmd = cmd.replace(i, mapping[i])

            message = Manager.Message(
                [
                    Segments.Reply(self.event.message_id),
                    Segments.Text(cmd)
                ]
            )

            self.actions.send(group_id=self.event.group_id, user_id=self.event.user_id, message=message)


