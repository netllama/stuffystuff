#!/bin/python2.7
"""Sonos player.

Keyboard controls:
    p: pause currently playing track
    s: stop playing current track
    u: increase volume
    d: decrease volume
    q: quit
"""

import warnings
warnings.simplefilter(action='ignore', category=FutureWarning)
import argparse
from random import shuffle
import os
import sys
import time
import readchar
from urllib import quote
from threading import Thread
from SimpleHTTPServer import SimpleHTTPRequestHandler
from SocketServer import TCPServer
from soco.discovery import by_name, discover


_FINISH = False

class HttpServer(Thread):
    """A simple HTTP Server in its own thread."""

    def __init__(self, docroot, port):
        patch_broken_pipe_error()
        os.chdir(docroot)
        super(HttpServer, self).__init__()
        self.daemon = True
        handler = SimpleHTTPRequestHandler
        sys.stderr = open('/dev/null', 'w', 1)
        self.httpd = TCPServer(("", port), handler)

    def run(self):
        """Start the server."""
        self.httpd.serve_forever()

    def stop(self):
        """Stop the server."""
        self.httpd.socket.close()


def patch_broken_pipe_error():
    """Monkey Patch BaseServer.handle_error to not write
    a stacktrace to stderr on broken pipe.
    https://stackoverflow.com/a/7913160"""
    import sys
    from SocketServer import BaseServer

    handle_error = BaseServer.handle_error

    def my_handle_error(self, request, client_address):
        type, err, tb = sys.exc_info()
        # there might be better ways to detect the specific erro
        if repr(err) == "error(32, 'Broken pipe')":
            # you may ignore it...
            pass
        else:
            handle_error(self, request, client_address)

    BaseServer.handle_error = my_handle_error


def controller(zone):
    """Control currently playing track."""
    keep_polling = True
    while keep_polling:
        if _FINISH:
            # catch the abort signal to avoid deadlock
            break
        device_state = zone.get_current_transport_info()['current_transport_state']
        control_input = readchar.readchar()
        if control_input.lower() == 's':
            # stop track
            zone.stop()
            print '\tSTOPPED'
            keep_polling = False
            continue
        elif control_input.lower() == 'p' and device_state == 'PAUSED_PLAYBACK':
            # unpause
            print '\t{}'.format(device_state)
            zone.play()
            print '\tRESUME'
        elif control_input.lower() == 'p' and device_state in ['PLAYING', 'RESUME']:
            # pause
            print '\t{}'.format(device_state)
            zone.pause()
            print '\tPAUSED'
        elif control_input.lower() == 'u':
            # volume up
            zone.volume += 1
            print '\tVOLUME ({}) +'.format(zone.volume)
        elif control_input.lower() == 'd':
            # volume down
            zone.volume -= 1
            print '\tVOLUME ({}) -'.format(zone.volume)
        elif control_input.lower() == 'q':
            zone.stop()
            print 'SSSTOP'
            sys.exit()
            print '\nEXIT'
        time.sleep(0.1)
    return None


def play_tracks(port, args, here, zone, docroot):
    """Play audio tracks."""
    global _FINISH
    # shuffle playlist
    playlist = args.files
    if args.random:
        shuffle(playlist)

    base_url = 'http://10.0.0.1:{p}'.format(p=port)
    url_path = here.replace(docroot, '')
    url = base_url + url_path
    total_tracks = len(playlist)
    track_counter = 0
    for mp3 in playlist:
        _FINISH = False
        control_thread = Thread(target=controller, args=(zone,))
        control_thread.start()
        track_counter += 1
        mp3_url = '{u}/{m}'.format(u=url, m=quote(mp3))
        print '\nAdding to queue:\t{}'.format(mp3)
        print 'Playing track:\t{} of {}'.format(track_counter, total_tracks)
        try:
            zone.play_uri(uri=mp3_url, title='test00101')
        except Exception as err:
            print 'Failed to play {} due to error:\t{}'.format(mp3, err)
            continue
        duration = zone.get_current_track_info()['duration']
        while zone.get_current_transport_info()['current_transport_state'] != 'STOPPED':
            # wait for track to finish playing
            time.sleep(1)
            position = zone.get_current_track_info()['position']
            # print current progress /duration
            sys.stdout.write('\r{p} / {d}'.format(p=position, d=duration))
            sys.stdout.flush()
        _FINISH = True
        control_thread.join(timeout=1)


def main():
    # Settings
    global _FINISH
    port = 61823
    args = parse_args()
    docroot = args.docroot
    here = os.getcwd()

    # Get the zone
    zone = by_name(args.zone)

    # Check if a zone by the given name was found
    if zone is None:
        zone_names = [zone_.player_name for zone_ in discover()]
        print("No Sonos player named '{}'. Player names are {}".format(args.zone,
                                                                       zone_names))
        sys.exit(1)

    # remove other members from the group
    for member in zone.group.members.copy():
        if member.get_speaker_info()['zone_name'] != args.zone:
            # remove group member that isn't the zone we want
            zone.group.members.discard(member)

    # Check whether the zone is a coordinator (stand alone zone or
    # master of a group)
    if not zone.is_coordinator:
        msg = "The zone '{}' is not a group master, and therefore cannot "
        msg += "play music. Please use '{}' instead".format(args.zone,
                                                            zone.group.coordinator.player_name)
        print msg
        sys.exit(2)
    if args.party:
        zone.partymode()

    # Setup and start the http server
    server = HttpServer(docroot, port)
    server.start()

    zone.clear_queue()
    try:
        play_tracks(port, args, here, zone, docroot)
    except KeyboardInterrupt:
        server.stop()
    zone.clear_queue()
    print '\n'


def parse_args():
    """Parse the command line arguments"""
    description = 'Play local files with Sonos by running a local web server'
    description += '\n\nKeyboard controls:\n\tp: pause currently playing track'
    description += '\n\ts: stop playing current track'
    description += '\n\tu: increase volume'
    description += '\n\td: decrease volume'
    description += '\n\tq: quit'
    parser = argparse.ArgumentParser(description=description,
                                     formatter_class=argparse.RawTextHelpFormatter)

    parser.add_argument('--zone', '-z', help='The name of the zone to play from',
                        required=True)
    parser.add_argument('--files', '-f', required=True,
    	    	    	help='Space separated list of files to play',
                        nargs='+')
    parser.add_argument('--party', '-p', default=False, action='store_true',
                        help='play on all zones')
    parser.add_argument('--random', '-r', action='store_true', default=False,
                        help='randomize the order of tracks')
    parser.add_argument('--docroot', '-d', action='store',
    	    	    	default='/media0/music',
                        help='Embedded web server doc root. All mp3 files must be' +
                        ' under this directory hierarchy')
    return parser.parse_args()


if __name__ == '__main__':
    main()
