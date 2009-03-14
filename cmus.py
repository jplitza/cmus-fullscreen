# -*- coding: utf-8 -*-
'''cmus module

This module is capable of controlling cmus and getting the status returned by
the cmus-remote -Q command in a nicer form.

NOT THREAD-SAFE!'''

import os, socket, struct
from operator import add
import mmap

_sock = False

CACHE_FULL = 1
CACHE_POS = 2

def Socket():
    global _sock
    # TODO: read socket path from config and use IP if desired
    # TODO: reopen if connection was closed
    if not _sock:
        _sock = socket.socket(socket.AF_UNIX)
        _sock.connect(os.path.expanduser(os.path.join('~', '.cmus', 'socket')))
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

# TODO: combine CacheIter and Cache
class CacheIter:
    _cache = False
    _cache_index = False
    def __init__(self):
        self._open()

    def _strtoint(self, str):
        ret = 0
        for i in xrange(len(str)):
            ret += ord(str[i]) << (i*8)
        return ret

    def _getfield(self, fd, size = False):
        start = i = fd.tell()
        while fd[i] != '\0':
            i += 1
        buf = fd[start:i]
        fd.seek(i+1)
        return buf

    def __iter__(self):
        return self

    def _open(self):
        if not self._cache:
            self._cache = open(os.path.expanduser(os.path.join('~', '.cmus', 'cache')))
        self._cache.seek(0, 2)
        self.endloc = self._cache.tell()
        self._cache.seek(0)
        self.m = mmap.mmap(self._cache.fileno(), 0, access=mmap.ACCESS_READ)
        if self.m[0:4] != 'CTC\x01':
            raise Exception('unexpected cache magic string: %s' % buf)
        flags = self._strtoint(self.m[4:8])
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
        self.m.seek(8)

    def next(self):
        if self.m.tell() >= self.endloc:
            raise StopIteration

        offset = self.m.tell()
        s = struct.unpack('3l', self.m.read(struct.calcsize('3l')))
        entry = {
                'size': s[0],
                'duration': s[1],
                'mtime': s[2],
                'file': self._getfield(self.m)
        }
        while self.m.tell() < offset+entry['size']:
            key = self._getfield(self.m)
            value = self._getfield(self.m)
            if key in 'tracknumber':
                try:
                    value = int(value)
                except ValueError:
                    value = 0
            entry[key] = value
        try:
            self.m.seek(offset + (entry['size'] + self._bytelength) & ~self._bytelength)
        except ValueError:
            self.m.seek(self.endloc)
        return entry

class Cache:
    _cache = False
    _cache_index = False
    _big_endian = False
    _64bit = False
    def __init__(self):
        self.gen_index()
        self.__iter__ = self._cache_index.__iter__
        self.keys = self._cache_index.keys
        self.itervalues = self._cache_index.itervalues
    def _strtoint(self, str):
        ret = 0
        for i in xrange(len(str)):
            ret += ord(str[i]) << (i*8)
        return ret
    def _getfield(self, fd, size = False):
        start = i = fd.tell()
        while fd[i] != '\0':
            i += 1
        buf = fd[start:i]
        fd.seek(i+1)
        return buf
    def gen_index(self):
        if not self._cache:
            self._cache = open(os.path.expanduser(os.path.join('~', '.cmus', 'cache')))
        self._cache.seek(0, 2)
        endloc = self._cache.tell()
        self._cache.seek(0)
        m = mmap.mmap(self._cache.fileno(), endloc, access=mmap.ACCESS_READ)
        self._cache_index = {}
        if m[0:4] != 'CTC\x01':
            raise Exception('unexpected cache magic string: %s' % buf)
        flags = self._strtoint(m[4:8])
        if flags & 0x01:
            self._64bit = True
        if flags & 0x02:
            self._big_endian = True
        m.seek(8)
        while m.tell() < endloc:
            offset = m.tell()
            s = struct.unpack('3l', m.read(struct.calcsize('3l')))
            entry = {
                    'size': s[0],
                    'duration': s[1],
                    'mtime': s[2],
                    'file': self._getfield(m)
            }
            while m.tell() < offset+entry['size']:
                key = self._getfield(m)
                value = self._getfield(m)
                if key == 'tracknumber':
                    try:
                        value = int(value)
                    except ValueError:
                        value = 0
                entry[key] = value
            self._cache_index[entry['file']] = entry
            try:
              m.seek(offset+(entry['size'] + (3 if not self._64bit else 7)) & ~(3 if not self._64bit else 7))
            except ValueError:
              return False

    def __getitem__(self, file):
        if not self._cache_index:
            self.gen_index()
        if file in self._cache_index.keys():
            return self._cache_index[file]
            m = mmap.mmap(self._cache.fileno(), os.path.getsize(self._cache.name), access=mmap.ACCESS_READ)
            offset = self._cache_index[file]
            m.seek(offset)
        else:
            return False
        s = struct.unpack('3l', m.read(struct.calcsize('3l')))
        entry = {
                'size': s[0],
                'duration': s[1],
                'mtime': s[2],
                'file': self._getfield(m)
        }
        if entry['file'] == file:
            while m.tell() < offset + entry['size']:
                key = self._getfield(m)
                value = self._getfield(m)
                if value != '':
                    entry[key] = self._getfield(m)
            return entry
        else:
            return False

    def __setitem__(self, key, value):
        raise NotImplementedError

class Library(list):
    def __init__(self):
        list.__init__(self)
        fd = open(os.path.expanduser(os.path.join('~', '.cmus', 'lib.pl')))
        for line in fd:
            self.append(line[0:-1])

# vim: set sw=4 et
