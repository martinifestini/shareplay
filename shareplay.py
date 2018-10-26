import logging
import os
import time
import re

from slackclient import SlackClient
import spotipy
import spotipy.util as util

log = logging.getLogger()
log.setLevel(logging.DEBUG)

slack_token = os.getenv('SHAREPLAY_SLACK_TOKEN')
username = os.getenv('SPOTIFY_USERNAME')
scope = 'user-library-read streaming playlist-modify-private user-read-currently-playing user-modify-playback-state'
sc = SlackClient(slack_token)

spotify_token = util.prompt_for_user_token(username, scope)
# spotify_token = os.getenv('SHAREPLAY_SPOTIFY_TOKEN')
sp = spotipy.Spotify(auth=spotify_token)

"""Bynder  Rotterdam Playlist"""
playlist_id = "4EHsYFOT5DZ5FDA05PwVaE"
user = sp.current_user()

MENTION_REGEX = "^<@(|[WU].+?)>(.*)"


class Event:
    def __init__(self, args):
        self.args = args
        self.context = {}

    def __str__(self):
        return '<{0.__class__} args="{0.args}">'.format(self)

    def with_context(self, context):
        self.context = context

class AddEvent(Event):
    pass


class VolumeEvent(Event):
    pass


class NextEvent(Event):
    pass


class HelpEvent(Event):
    pass


class ChatListener:
    event_registry = {
        'add': AddEvent,
        'volume': VolumeEvent,
        'next': NextEvent,
        'help': HelpEvent,
    }

    def __init__(self):
        self.user_id = sc.api_call("auth.test")["user_id"]

    def _parse_rtm(self, rtm):
        for event in rtm:
            if event['type'] == 'message':
                try:
                    yield self._parse_message_event(event)
                except Exception as e:
                    log.error(e, exc_info=True)
                    yield "Whoops"


    def _parse_message_event(self, message_event):
        user_id, message = self._parse_direct_mention(message_event['text'])
        if user_id == self.user_id:
            event = self._parse_command(message)
            context = {
                'channel': message_event['channel'],
                'user': message_event['user'],
            }
            event.with_context(context)
            return event

    def _parse_command(self, command):
        log.info(" > Got command %s", command)
        try:
            command, args = command.split(" ", maxsplit=1)
        except ValueError:
            log.info("Got no args")
            args = None
        
        return self.receive(command, args)

    def _parse_direct_mention(self, message_text):
        matches = re.search(MENTION_REGEX, message_text)
        if matches:
            return (matches.group(1), matches.group(2).strip())
        else:
            (None, None)

    def listen(self, event_bus):
        if sc.rtm_connect(with_team_state=False):
            while True:
                for event in self._parse_rtm(sc.rtm_read()):
                    if not isinstance(event, Event):
                        continue
                    response = event_bus.accept(event)
                    self.send(response, context=event.context)
                time.sleep(1)
        else:
            print("Connection Failed")

    def receive(self, chat_command, args=None, context=None):
        """ incoming slack message """
        log.info("Received command %s", chat_command)
        return self.event_registry[chat_command](args)

    def send(self, message, context):
        sc.api_call(
            "chat.postMessage",
            channel=context['channel'],
            text='<@{}> {}'.format(context['user'], message)
        )


class MusicController:
    def add(self, event):
        return "Added to playlist"


class SpotifyMusicController(MusicController):
    def add(self, event):
        tracks = sp.search(event.args, limit=1, type='track')
        try:
            track = tracks['tracks']['items'][0]
        except KeyError as e:
            log.info(e)
            return "Didnt find anything dude"
        sp.user_playlist_add_tracks(
            user['id'], playlist_id, [track['id']]
        )
        log.info(track)
        return "Added {} to playlist".format(track['name'])

    def next(self, event):
        sp.next_track()
        return "Skipped track, also deleted it"

    def volume(self, event):
        sp.volume(int(event.args))
        return "Fine, set to {}%".format(event.args)

    def help(self, event):
        return str(ChatListener.event_registry)


class EventBus:
    def __init__(self, controller):
        self.event_registry = {
            AddEvent: controller.add,
            HelpEvent: controller.help,
            VolumeEvent: controller.volume,
            NextEvent: controller.next,
        }

    def accept(self, event):
        try:
            return self.event_registry[event.__class__](event)
        except Exception as e:
            log.error(e, exc_info=True)
            return "Whoops, something went wrong"

    def start(self, listener):
        listener.listen(self)


def run_app():
    chat_listener = ChatListener()
    controller = SpotifyMusicController()
    event_bus = EventBus(controller)
    event_bus.start(chat_listener)

    event_bus.accept(
        chat_listener.receive('add')
    )



if __name__ == '__main__':
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    log.addHandler(ch)
    log.info("asd")
    run_app()
