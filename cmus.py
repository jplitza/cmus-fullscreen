# -*- coding: utf-8 -*-
'''cmus module

This module is capable of controlling cmus and getting the status returned by
the cmus-remote -Q command in a nicer form.

NOT THREAD-SAFE!'''

import os, socket, struct, mmap

_sock = False

def Socket():
    global _sock
    # TODO: read socket path from config and use IP if desired
    # TODO: reopen if connection was closed
    if not _sock:
        try:
            _sock = socket.socket(socket.AF_UNIX)
            _sock.connect(os.path.expanduser(os.path.join('~', '.cmus', 'socket')))
        except:
            del _sock
            raise
    return _sock

class Status(dict):
    '''
    returns a dict containing all information returned by the status command in
    cmus. The dict contains two sub-dicts 'tag' and 'set' containing the file
    metadata and the cmus settings.
    '''
    def __init__(self):
        self._sock = Socket()
        self.update()

    def _receive(self, retry = True):
        try:
            self._sock.sendall("status\n")
            return self._sock.recv(4096)
        except socket.error:
            if retry:
                self._sock = Socket()
                return self._receive(False)
            else:
                return ""

    def update(self):
        dict.__init__(self)
        self['status'] = 'stopped'
        self['tag'] = {}
        self['set'] = {}
        p = self._receive().split("\n")
        for line in p:
            if not line == '':
                splitted = line.split(" ", 1)
                try:
                    if splitted[0] in ('tag', 'set'):
                        splitted[1:] = splitted[1].split(" ", 1)
                        if splitted[2].strip() != '':
                            self[splitted[0]][splitted[1]] = splitted[2].strip()
                    else:
                        self[splitted[0]] = splitted[1].strip()
                except IndexError:
                    print line
        if 'duration' in self.keys():
            self['duration'] = int(self['duration'])
        if 'position' in self.keys():
            self['position'] = int(self['position'])
        if 'tracknumber' in self['tag'].keys():
            self['tag']['tracknumber'] = int(self['tag']['tracknumber'])
        if 'vol_left' in self['set'].keys():
            self['set']['vol_left'] = int(self['set']['vol_left'])
        if 'vol_right' in self['set'].keys():
            self['set']['vol_right'] = int(self['set']['vol_right'])
        if 'vol_left' in self['set'].keys() and 'vol_right' in self['set'].keys():
            self['set']['vol'] = (self['set']['vol_left']+self['set']['vol_right'])/2

class Control:
    def __init__(self):
        self._sock = Socket()

    def _send(self, text, retry = True):
        try:
            self._sock.sendall("%s\n" % text)
            self._sock.recv(1)
            return True
        except socket.error:
            if retry:
                self._sock = Socket()
                return self._send(text, False)
            else:
                return False

    def pause(self):
        return self._send('player-pause')

    def play(self):
        return self._send('player-play')

    def stop(self):
        return self._send('player-stop')

    def next(self):
        return self._send('player-next')

    def prev(self):
        return self._send('player-prev')

    def set(self, setting, value):
        return self._send('set %s=%s' % (setting, value))

    def toggle(self, setting):
        return self._send('toggle %s' % setting)

    def play_file(self, file):
        if self._send('add -Q %s' % file):
            return self.next()
        return false

    def play_lib(self, metadata):
        for key in ('artist', 'album', 'title'):
            if key not in metadata.keys():
                return False
        self._send('view sorted')
        self._send('/%s %s %s' % (metadata['artist'], metadata['album'], metadata['title']))
        self._send('win-activate')

    def raw(self, text):
        return self._send(text)

class Cache:
    _cache = False
    _cache_index = {}
    def __init__(self):
        self.structsize = struct.calcsize('3l')
        self._open()

    def __iter__(self):
        return self

    def _getfield(self, fd):
        buf = fd.read(1)
        while buf[-1] != '\0':
            buf += fd.read(1)
        return buf[:-1]

    def keys(self):
        return self._cache_index.keys()

    def _open(self):
        if not self._cache:
            try:
                self._cache = open(os.path.expanduser(os.path.join('~', '.cmus', 'cache')))
            except IOError:
                def next():
                    raise StopIteration
                self.next = next
                return False
        self._cache.seek(0, 2)
        self.endloc = self._cache.tell()
        self._cache.seek(0)
        if self._cache.read(4) != 'CTC\x01':
            raise Exception('unexpected cache magic string: %s' % buf)
        flags = struct.unpack('<l', self._cache.read(4))[0]
        if flags & 0x01:
            self._64bit = True
            self._bytelength = 7
        else:
            self._64bit = False
            self._bytelength = 3
        if flags & 0x02:
            self._big_endian = True
        else:
            self._big_endian = False
        self._cache.seek(8)

    def next(self):
        offset = self._cache.tell()
        if offset >= self.endloc:
            raise StopIteration

        s = struct.unpack('3l', self._cache.read(self.structsize))
        entry = {
                'size': s[0],
                'duration': s[1],
                'mtime': s[2],
                'file': self._getfield(self._cache)
        }
        fields = self._cache.read(entry['size']-self.structsize-len(entry['file'])-1).split('\0')
        for i in xrange(0, len(fields)-1, 2):
            if fields[i] == 'tracknumber':
                try:
                    fields[i+1] = int(fields[i+1])
                except ValueError:
                    fields[i+1] = 0
            entry[fields[i]] = fields[i+1]
        seeker = ((entry['size'] + self._bytelength) & ~self._bytelength) - entry['size']
        if seeker > 0:
            try:
                self._cache.seek(seeker, 1)
            except ValueError:
                self._cache.seek(self.endloc)
        del seeker
        return entry

    def gen_index(self):
        self._cache_index = {}
        for track in self:
            self._cache_index[track['file']] = track


    def __getitem__(self, file):
        if not self._cache_index:
            self.gen_index()
        if file in self._cache_index.keys():
            return self._cache_index[file]
        else:
            return False

    def __setitem__(self, key, value):
        raise NotImplementedError

def library():
    fd = open(os.path.expanduser(os.path.join('~', '.cmus', 'lib.pl')))
    return [line[0:-1] for line in fd]

Library = library

# vim: set sw=4 et
