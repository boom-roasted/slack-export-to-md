from __future__ import annotations # For return types

from pathlib import Path
from typing import Dict, List, Optional, OrderedDict, Union
from collections import OrderedDict
from datetime import datetime
import json
import re


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

    def to_markdown_s(self, users: Optional[Dict[str, User]] = None) -> str:
        """Creates a markdown formatted string for this message"""
        utc = datetime.utcfromtimestamp(float(self.ts)).strftime('%Y-%m-%d %H:%M:%S') + " UTC"

        # Use a users initials instead of their ID everywhere possible
        if users is not None:
            name = users[self.user].initials
            text = re.sub("<@(U[A-Z0-9]{1,})>", lambda x: f"**@{users[x.group(1)].initials}**", self.text)
        else:
            name = self.user
            text = self.text
        return f"**{name}:** {text} *[{utc}]*"

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
            text, user, ts = (item.get(attr) for attr in required_attrs)
            
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

    def to_markdown_s(self, users: Optional[Dict[str, User]] = None) -> str:
        return (
            f"## {super().to_markdown_s(users)}\n\n"
            + "### Replies\n"
            + "\n\n".join([reply.to_markdown_s(users) for reply in self.replies])
        )

    @staticmethod
    def create(m: Message) -> Thread:
        """Initialize a thread with a head message"""
        if m.thread_ts is None:
            raise AttributeError(f"Message must have 'thread_ts' to be initialized to a thread. Message: {m}")
        return Thread(m.text, m.user, m.ts, m.thread_ts)


class User:
    def __init__(self, id: str, name: str, real_name: str, real_name_normalized: str) -> None:
        self.id = id
        self.name = name
        self.real_name = real_name
        self.real_name_normalized = real_name_normalized
        self.initials = "".join([part[0] for part in real_name_normalized.split(" ") if not part[0] == "("])

    @staticmethod
    def create(user: dict) -> User:
        """Create a User from the dict containing a single user's information in a slack export"""
        attrs = user.keys()
        required_attrs = ["id", "name", "profile"]

        for attr in required_attrs:
            if not attr in attrs:
                raise AttributeError(f"User definition does not contain necessary attribute: {attr}. Definition: {user}")

        id, name, profile = (user.get(attr) for attr in required_attrs)

        if not isinstance(profile, dict):
            raise AttributeError(f"Expected user profile to be a dict, not {type(profile)}.")

        required_profile_attrs = ["real_name", "real_name_normalized"]

        for attr in required_profile_attrs:
            if not attr in profile.keys():
                raise AttributeError(f"User profile must contain a '{attr}' field. Got profile: {profile}")

        real_name, real_name_normalized = (profile.get(attr) for attr in required_profile_attrs)

        return User(str(id), str(name), str(real_name), str(real_name_normalized))

    @staticmethod
    def create_map(filename: Path) -> Dict[str, User]:
        users: Dict[str, User] = {} # user id, user
        with open(filename, "r") as f:
            data = json.load(f)

        for user_data in data:
            user = User.create(user_data)
            users[user.id] = user

        return users


class Channel:
    
    def __init__(self, name: str, messages: List[Message], threads: List[Thread], threaded_messages: List[Union[Thread, Message]]) -> None:
        self.name = name
        self.messages = messages
        self.threads = threads
        self.threaded_messages = threaded_messages

    def to_markdown(self, filename: Path) -> None:
        with open(filename, "w") as f:
            f.write(f"# {self.name} channel, in markdown\n\n")
            for m in self.threaded_messages:
                f.write(m.to_markdown_s(users) + "\n\n")
                if isinstance(m, Thread):
                    f.write("---\n\n") # Visually close out threads

    @staticmethod
    def create(channel_folder: Path) -> Channel:
        name = channel_folder.name
        messages: List[Message] = []
        for filename in channel_folder.glob("*.json"):
            file_messages = Message.create_many(filename)
            messages.extend(file_messages)

        threads = Channel._make_threads(messages)
        threaded_messages = Channel._make_threaded_messages(messages, threads)

        return Channel(name, messages, threads, threaded_messages)

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

    @staticmethod
    def _make_threaded_messages(messages: List[Message], threads: List[Thread]) -> List[Union[Thread, Message]]:
        """Combine all messages with threaded messages create one list in chronological order both"""
        # Remove threads from messages list since they will be added back in self-contained threads
        messages_only = [m for m in messages if m.thread_ts is None]

        # Combine messages with threads
        threaded_messages = messages_only + threads # type: ignore

        # Sort by timestamp
        return sorted(threaded_messages, key=lambda x: x.ts)


if __name__ == "__main__":

    # Parse command line arguments
    import sys
    if len(sys.argv) == 0:
        print("slack-export-to-md: nothing to do :)")
        print("slack-export-to-md [-h | --help] for help")
        sys.exit(0)
    if len(sys.argv) == 1 and sys.argv[0] in ("-h", "--help"):
        print("slack-export-to-md <export-dir> <glob>")
        print("---")
        print("Where export-dir is the directory of the unzipped slack export")
        print("and glob is a pattern matching the names of the channels to convert to md.")
        print("")
        print("This program expects to find a file named 'users.json' within the export directory.")
        print("Output will be written to a directory named 'md' next to the export directory.")
        print("")
        print("slack-export-to-md [-h | --help] to display this message and exit.")
        sys.exit(0)
    if len(sys.argv) != 3:
        print(f"Expected two arguments, got {len(sys.argv) - 1}") # First argument is automatic self file-path
        print("slack-export-to-md [-h | --help] for help")
        sys.exit(1)

    # Parse export directory argument
    export_dir = Path(sys.argv[1])
    if not export_dir.is_absolute():
        export_dir = Path.cwd() / export_dir

    if not export_dir.exists():
        raise FileNotFoundError(f"Cannot find export directory {export_dir}")

    # Parse glob search string argument
    channel_glob = sys.argv[2]

    # Read user information
    user_file = export_dir / "users.json"
    users = User.create_map(user_file)

    # Setup output directory
    outdir = export_dir / "../md"
    outdir.mkdir(exist_ok=True)

    # Process channel export data and write to markdown format
    for channel_dir in export_dir.glob(channel_glob):
        channel = Channel.create(channel_dir)
        print(f"Channel {channel_dir.name}: Found {len(channel.messages)} total messages with {len(channel.threads)} discrete threads")
        channel.to_markdown(outdir / f"{channel_dir.name}.md")
