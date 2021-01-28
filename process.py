from __future__ import annotations # For return types

from pathlib import Path
from typing import List, Optional, OrderedDict
from collections import OrderedDict
from datetime import datetime
import json


known_message_subtypes = [
    "bot_message", # A message was posted by an app or integration
    "me_message", # A message was sent with the /me slash command
    "message_changed", # A message was changed
    "message_deleted", # A message was deleted
    "channel_join", # A member joined a channel
    "channel_leave", # A member left a channel
    "channel_topic", # A channel topic was updated
    "channel_purpose", # A channel purpose was updated
    "channel_name", # A channel was renamed
    "channel_archive", # A channel was archived
    "channel_unarchive", # A channel was unarchived
    "group_join", # A member joined a group
    "group_leave", # A member left a group
    "group_topic", # A group topic was updated
    "group_purpose", # A group purpose was updated
    "group_name", # A group was renamed
    "group_archive", # A group was archived
    "group_unarchive", # A group was unarchived
    "file_share", # A file was shared into a channel
    "file_reply", # A reply was added to a file
    "file_mention", # A file was mentioned in a channel
    "pinned_item", # An item was pinned in a channel
    "unpinned_item", #An item was unpinned from a channel
]


class Message:
    def __init__(self, text: str, user: str, ts: str, thread_ts: Optional[str]) -> None:
        self.text = text
        self.user = user
        self.ts = ts
        self.thread_ts = thread_ts

    def to_markdown_s(self) -> str:
        """Creates a markdown formatted string for this message"""
        utc = datetime.utcfromtimestamp(float(self.ts)).strftime('%Y-%m-%d %H:%M:%S') + " UTC"
        return (
            f"**{self.user}:** {self.text} *[{utc}]*"
        )

    @staticmethod
    def create_many(filename: Path) -> List[Message]:
        """
        Generate a list of messages from a single slack export json file.
        The name of the file is the date of the conversations.
        """
        messages: List[Message] = []
        date = filename.stem

        with open(filename, "r") as f:
            data = json.load(f)

        for item in data:

            item_attrs = item.keys()

            # Don't include meta messages
            if "subtype" in item_attrs:
                continue
            
            # Ensure required attributes exist
            required_attrs = ["text", "user", "ts"]
            for attr in required_attrs:
                if not attr in item_attrs:
                    print(f"WARNING: message in file {filename} does not have required attribute '{attr}'. Skipping. JSON is: {item}")
                    continue

            # Get message attributes
            text, user, ts = (item.get(attr, ) for attr in required_attrs)
            
            # Get optional attributes. In this case, just the thread time stamp
            thread_ts = item.get("thread_ts", None)

            # Add message to list of valid messages
            messages.append(Message(text, user, ts, thread_ts))

        return messages


class Thread(Message):
    def __init__(self, text: str, user: str, ts: str, thread_ts: str) -> None:
        super().__init__(text, user, ts, thread_ts)
        self.thread_id = thread_ts
        self.replies: List[Message] = []

    def add_reply(self, reply: Message) -> None:
        self.replies.append(reply)

    def to_markdown(self, filepath: Path) -> None:
        """Generates markdown for this thread"""
        with open(filepath, "w") as f:
            # Write the header
            f.write("# A generated thread\n")
            f.write(self.to_markdown_s() + "\n")
            f.write("## Replies\n")
            for reply in self.replies:
                f.write(reply.to_markdown_s() + "\n\n")


    @staticmethod
    def create(m: Message) -> Thread:
        """Initialize a thread with a head message"""
        if m.thread_ts is None:
            raise AttributeError(f"Message must have 'thread_ts' to be initialized to a thread. Message: {m}")
        return Thread(m.text, m.user, m.ts, m.thread_ts)


class Channel:
    def __init__(self, messages: List[Message], threads: List[Thread]) -> None:
        self.messages = messages
        self.threads = threads

    @staticmethod
    def create(channel_folder: Path) -> Channel:
        messages: List[Message] = []
        for filename in channel_folder.glob("*.json"):
            file_messages = Message.create_many(filename)
            messages.extend(file_messages)

        threads = Channel._make_threads(messages)

        return Channel(messages, threads)

    @staticmethod
    def _make_threads(messages: List[Message]) -> List[Thread]:
        """Create threads by appending messages as replies of an original message"""
        threads: OrderedDict[str, Thread] = OrderedDict() # thread_ts, thread_head
        for m in messages:
            if m.thread_ts is not None:

                # Add this message to an existing thread if possible
                if m.thread_ts in threads.keys():
                    threads[m.thread_ts].add_reply(m)

                # Create a new thread if it does not already exist
                else:
                    threads[m.thread_ts] = Thread.create(m)

        return list(threads.values())




if __name__ == "__main__":

    folder = Path.cwd() / "export/help"

    channel = Channel.create(folder)

    print(f"Found {len(channel.messages)} messages with {len(channel.threads)} discrete threads")

    outdir = Path.cwd() / "md" # for 'markdown'
    outdir.mkdir(exist_ok=True)

    for thread in channel.threads:
        thread.to_markdown(outdir / f"{thread.thread_id}.md")
