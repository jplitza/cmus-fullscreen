#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""
Fullscreen music title display

This app provides a fullscreen interface to cmus, including library navigation.
"""

import pygame, sys, os, time, operator
import cmus, shapes
try:
  import dbus
except ImportError:
  pass
try:
  import thread, Queue
except ImportError:
  # TODO: implement library reading without threads
  pass
from math import pi

DEBUG = 0
SCRIPT_START = time.time()

def LibThread(q):
  """
  LibThread(q) -- Get representation of cmus' cache

  On success, puts a dict representing cmus' cache in the Queue object q.

  This function is intended to be called as a separate thread! Thus, it
  does few error handling and modifies nice value.
  """
  os.nice(1)
  time.sleep(0)
  library = cmus.Library()
  cache = cmus.Cache()
  liblist = {}
  # BUG: newly added tracks don't appear in the listing as they aren't recorded
  #      neither in the cache nor in the library.pl
  # TODO: speed up loading
  # TODO: report progress values, maybe even return partial results?
  for track in cache.itervalues():
    # allow other thread to jump in
    time.sleep(0)

    # file in cache but not in library?
    if not track['file'] in library:
      continue

    # use dummy values if no value given
    if track.has_key('albumartist') and track['albumartist'] != '':
      artist = track['albumartist']
    elif track.has_key('artist') and track['artist'] != '':
      artist = track['artist']
    else:
      artist = '[unknown]'

    if track.has_key('album') and track['album'] != '':
      album = track['album']
    else:
      album = '[unknown]'

    if track.has_key('title') and track['title'] != '':
      title = track['title']
    else:
      # use filename without extension
      title = os.path.basename(track['file']).rsplit('.', 1)[0]

    if not liblist.has_key(artist):
      liblist[artist] = {}
    if not liblist[artist].has_key(album):
      liblist[artist][album] = {}
    liblist[artist][album][title] = track

  def sorter(x):
    ref = liblist[artist][album][x]
    if ref.has_key('tracknumber') and ref['tracknumber'] != '':
      return ref['tracknumber']
    elif ref.has_key('title') and ref['title'] != '':
      return ref['title']
    else:
      return 0

  for artist in liblist.keys():
    for album in liblist[artist].keys():
      # sort by tracknumber if existant, title else
      liblist[artist][album]['__keys__'] = \
        sorted(liblist[artist][album].keys(), key=sorter)
    liblist[artist]['__keys__'] = sorted(liblist[artist].keys(), key=str.lower)
  liblist['__keys__'] = sorted(liblist.keys(), key=str.lower)
  q.put(liblist)

class Surface(pygame.Surface):
  """
  Wrapper class for pygame.Surface() keeping track of the blitted Rects.
  They are available in Surface.updates.
  """
  updates = []

  def update(self, rect, blank = True):
    if blank:
      self.fill((0,0,0,0), rect)
    # keep track of surface updates so we know which parts of the screen
    # need to be updated
    self.updates.append(pygame.Rect(rect))

  def blit(self, source, dest, area = None, blank = True):
    self.update((dest, area[2:4]) if area else (dest, source.get_size()), blank)
    pygame.Surface.blit(self, source, dest, area)


def load_font(fontname, fontsize):
  """
  load_font(fontname, fontsize) -> the appropriate pygame.Font()

  Searches for the font given by fontname and fontsize at the following
  places (in order):
   - the pygame system fonts
   - the standard MS fonts at /usr/share/fonts/truetype/msttcorefonts
   - /usr/share/fonts (recursive)
   - working dir
  If the font isn't found, the default pygame font is returned.
  """
  # system fonts
  if pygame.font.get_fonts().count(fontname) == 1:
    return pygame.font.SysFont(fontname, fontsize)
  # standard MS fonts
  if os.path.exists('/usr/share/fonts/truetype/msttcorefonts/'+fontname+'.ttf'):
    return pygame.font.Font('/usr/share/fonts/truetype/msttcorefonts/'+fontname+'.ttf', fontsize)
  # search /usr/share/fonts/
  for root, dirs, files in os.walk('/usr/share/fonts'):
    if fontname+'.ttf' in files:
      return pygame.font.Font(os.path.join(root, fontname+'.ttf'), fontsize)
  # search in working dir
  if os.exists('./'+fontname+'.ttf'):
    return pygame.font.Font(fontname+'.ttf', fontsize)
  # last resort: return default font
  return pygame.font.Font(None, fontsize)


def checkpoint(name, first = False):
  """
  checkpoint(name, [first]) -- print elapsed time since last checkpoint

  Prints the elapsed time since the last call to checkpoint(), but only
  if the global variable DEBUG is nonzero.
  """
  global DEBUG
  if DEBUG:
    if name != 'first':
      print 'checkpoint %15s: %f' % ((time.time() - SCRIPT_START) if not first else name, (time.time() - checkpoint.start))
    checkpoint.start = time.time()

def load_svg(filename, size):
  """
  load_svg(filename, size) -> pygame.Surface()

  Loads the SVG graphic pointed at by filename rendered at the given size
  into a pygame surface
  """
  try:
    import rsvg, cairo, array, cStringIO
    os.stat(filename)
  except (ImportError, OSError):
    return pygame.Surface((0,0))
  width, height = size
  csurface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
  context = cairo.Context(csurface)
  svg = rsvg.Handle(file=filename)
  ssize = svg.get_dimension_data()
  context.set_matrix(cairo.Matrix(width/ssize[2], 0, 0, height/ssize[3], 0, 0))
  svg.render_cairo(context)
  f = cStringIO.StringIO()
  csurface.write_to_png(f)
  f.seek(0)
  return pygame.image.load(f, 'temp.png').convert_alpha()

class Screen:
  """
  main interface class
  """
  fonts = []
  shapes = {}
  colors = [
    (255, 255, 255), # track title
    (200, 200, 200), # track artist/album
    (150, 150, 150), # volume/status
    (0, 0, 0),       # background
    (50, 50, 50)     # light gradient end
  ]
  mode = 'status'
  fullscreen = True

  def __init__(self, fullscreen = True, size = None):
    """
    Screen.__init__([fullscreen [,size]]) -- initialize screen

    Starts up the display screen, optionally in window and mode with
    specified size.
    """
    checkpoint('first')
    pygame.font.init()
    pygame.display.init()
    pygame.event.set_allowed(None)
    pygame.event.set_allowed((pygame.QUIT, pygame.KEYDOWN))
    pygame.event.set_grab(False)
    pygame.mouse.set_visible(False)
    self.fullscreen = fullscreen
    if size:
      self.rsize = size
    else:
      self.rsize = pygame.display.list_modes()[0] if fullscreen else (800, 600)

    # TODO: generalize detection of dualhead configs
    if self.rsize == (2704, 1050):
      self.size = (1680, 1050)
    else:
      self.size = self.rsize

    checkpoint('pygame init')

    self.fonts = [
      {'name': 'arialbd', 'size': self.size[0]/24},
      {'name': 'arial', 'size': self.size[0]/33},
      {'name': 'arial', 'size': self.size[0]/47},
    ]
    self.load_fonts()
    self.load_shapes()
    self.deactivate_screensaver()
    pygame.display.set_caption('cmus fullscreen interface')
    # TODO: set window icon?
    self.screen = pygame.display.set_mode(self.rsize, \
      pygame.FULLSCREEN if fullscreen else 0)
    checkpoint('window')
    self.back = self.draw_background()
    # TODO: only make browsurf as big as needed
    self.browsurf = Surface(self.size, pygame.SRCALPHA)
    self.surf = Surface(self.size, pygame.SRCALPHA)
    self.st = cmus.Status()
    self.start_thread()

  def start_thread(self):
    if not hasattr(self, 'thread'):
      try:
        self.queue = Queue.Queue()
        self.thread = thread.start_new_thread(LibThread, (self.queue, ))
      except NameError:
        self.thread = True
        self.queue = 0

  def quit(self):
    """
    Screen.quit() -- close all components
    """
    pygame.display.quit()
    os.unlink(os.path.expanduser(os.path.join('~', '.cmus', 'inhibit-osd')))
    self.activate_screensaver()
    # TODO: kill thread silently/cleanly

  def load_fonts(self):
    """
    Screen.load_fonts() -- load all required fonts

    Loads all fonts defined in Screen.fonts by name and size as
    pygame.Font object.
    """
    for key, font in enumerate(self.fonts):
      self.fonts[key]['font'] = load_font(font['name'], font['size'])
    checkpoint('fonts')

  def deactivate_screensaver(self):
    """
    Screen.deactivate_screensaver() -- deactivate a running screensaver
    """
    # TODO: support xscreensaver and maybe others (kscreensaver?)
    try:
      self.session_bus = dbus.SessionBus()
      self.scrsvr = self.session_bus.get_object(
        'org.gnome.ScreenSaver',
        '/org/gnome/ScreenSaver'
      )
      self.scrsvr_cookie = self.scrsvr.Inhibit(
        'cmus-status',
        'Showing played track info'
      )
    except NameError:
      pass
    # TODO: doesn't belong here
    f = file(os.path.expanduser(os.path.join('~', '.cmus', 'inhibit-osd')), 'w')
    f.close()
    checkpoint('screensaver')

  def activate_screensaver(self):
    """
    Screen.activate_screensaver() -- activate screensaver

    Re-activates a previously deactivated screensaver.
    """
    # TODO: support xscreensaver and maybe others (kscreensaver?)
    try:
      self.scrsvr.UnInhibit(self.scrsvr_cookie)
    except (NameError, AttributeError):
      pass

  def draw_background(self):
    """
    Screen.draw_background() -> pygame.Surface

    Paint the background layer onto a pygame surface and return it.
    """
    back = pygame.Surface(self.size)
    width, height = self.size
    self.shapes['gradient'] = shapes.gen_gradient(
      (width, height / 2),
      self.colors[3],
      self.colors[4]
    )
    back.blit(self.shapes['gradient'], (0, height - self.sh('gradient')))

    # TODO: Don't use static path/icon
    image = '/usr/share/icons/Tango/scalable/mimetypes/audio-x-generic.svg'
    self.shapes['musicimg'] = load_svg(image, [height/2]*2)
    back.blit(
      self.shapes['musicimg'],
      (width / 10, (height - self.sh('musicimg')) / 2)
    )
    return back

  def load_shapes(self):
    import shapes
    width, height = self.size
    self.shapes['bar'] = shapes.gen_bar((width/3, 16), self.colors[1])
    self.shapes['dot'] = shapes.gen_dot(16/2, self.colors[1])
    self.shapes['pause'] = shapes.gen_pause([height/10]*2, self.colors[0])
    self.shapes['stop'] = shapes.gen_stop([height/10]*2, self.colors[0])

  def sw(self, name):
    return self.shapes[name].get_width()
  def sh(self, name):
    return self.shapes[name].get_height()

  def render_center(self, lines):
    size = width, height = self.size
    i = 0
    blockheight = reduce(
      operator.add,
      [a['font']['font'].get_linesize()+5 for a in lines]
    )
    fromtop = 0
    for line in lines:
      if line['text'] != '' or line.has_key('blank'):
        self.surf.update((
          width / 10 + self.sw('musicimg') + 10,
          (height - blockheight) / 2 + fromtop,
          width * 9 / 10 - self.sw('musicimg') - 10,
          line['font']['font'].get_linesize()
        ))
      if line['text'] != '':
        i = 0
        sw = width+1
        while sw + width/10+self.sw('musicimg')+1 > width:
          s = line['font']['font'].render(
            line['text'].decode('utf-8')[0:-i]+'...' if i > 0 else
            line['text'].decode('utf-8'),
            True, line['color']
          )
          sw, sh = s.get_size()
          i += 1
        self.surf.blit(s, (
          width / 10 + self.sw('musicimg') + 10,
          (height - blockheight) / 2 + fromtop
        ))
      fromtop += line['font']['font'].get_linesize()+5
      i += 1

  def update(self, first = False):
    if len(self.surf.updates) == 0 and not first \
      and (self.mode != 'browser' or len(self.browsurf.updates) == 0):
        return False
    width, height = self.size
    w, h = self.screen.get_size()
    if self.screen != self.surf:
      self.screen.blit(self.back, (w-width, h-height))
      checkpoint('blit back')
      self.screen.blit(self.surf, (w-width, h-height))
      checkpoint('blit')
    if self.mode == 'browser':
      self.screen.blit(self.browsurf, (w-width, h-height))
      checkpoint('browser blit')

    if first:
      pygame.display.update()
    else:
      updates = self.surf.updates
      if self.mode == 'browser':
        updates += self.browsurf.updates
      updates = [u.move(w-width, h-height) for u in updates]
      self.surf.updates = []
      self.browsurf.updates = []
      pygame.display.update(updates)
    checkpoint('update')

  def loop(self, first = False):
    for event in pygame.event.get():
      if event.type == pygame.KEYDOWN and event.key == pygame.K_f:
        self.__init__(not self.fullscreen)
        first = True
      elif event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE \
        and self.mode != 'browser':
          self.mode = 'browser'
          first = True
      elif event.type == pygame.KEYDOWN and event.key == pygame.K_s \
        and self.mode != 'status':
          self.mode = 'status'
          self.surf.fill((0, 0, 0, 0))
          first = True
      elif event.type == pygame.KEYDOWN \
        and (event.key == pygame.K_ESCAPE or event.key == pygame.K_q) \
        or event.type == pygame.QUIT:
          self.quit()
          return False
      else:
        pygame.event.post(event)

    checkpoint('events')
    self.loop_status(first)
    if self.mode == 'browser':
      if not self.loop_browser(first):
        pygame.event.clear()
        # close browser by simulating s keypress
        # TODO: do this nicer
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, dict(key=pygame.K_s)))
      else:
        pygame.event.clear()

    # update screen
    self.update(first)
    return True

  def loop_status(self, first):
    width, height = size = self.size
    old = self.st.copy()
    self.st.update()
    st = self.st

    if not st['tag'].has_key('artist'):
      st['tag']['artist'] = 'Unknown Artist'
    if not st['tag'].has_key('title'):
      st['tag']['title'] = 'Unknown Track'

    checkpoint('status update')

    if st['status'] != old['status'] or first:
      if st['status'] == 'paused':
        self.surf.blit(self.shapes['pause'], 
          ((width - self.sw('pause')) / 2, height / 6 - self.sh('pause') / 2)
        )
      elif st['status'] == 'stopped':
        self.surf.blit(self.shapes['stop'], 
          ((width - self.sw('stop')) / 2, height / 6 - self.sh('stop') / 2)
        )
      else:
        self.surf.update((
          (width - self.sw('pause')) / 2,
          height / 6 - self.sh('pause') / 2,
          self.sw('pause'),
          self.sh('pause')
        ))

    if st['tag'] != old['tag'] or first:
      lines = []
      lines.append({
        'text': '%s' % st['tag']['title'],
        'font': self.fonts[0],
        'color': self.colors[0]
      })
      lines.append({
        'text': '%s' % st['tag']['artist'],
        'font': self.fonts[0],
        'color': self.colors[1]
      })

      if st['tag'].has_key('album'):
        lines.append({
          'text': '%s' % st['tag']['album'],
          'font': self.fonts[1],
          'color': self.colors[1]
        })
      else:
        lines.append({'text': '', 'font': self.fonts[1], 'blank': True})

      checkpoint('track change')
      self.render_center(lines)
      checkpoint('trackinfo')

    if old['set']['vol'] != st['set']['vol'] or first:
      sh = self.fonts[2]['font'].metrics('%')[0][3]
      sw = sh*4
      vol = pygame.Surface((sw+3, sh+3))

      i = st['set']['vol'] / 100.0 * sw
      pygame.draw.polygon(vol, self.colors[0], (
          (1, sh),
          (1+i, sh-round((i/float(sw))*(sh-1))),
          (1+i, sh+1),
          (1, sh+1)
        ), 0)
      pygame.draw.aalines(vol, self.colors[0], True, (
          (1, sh),
          (sw+1, 1),
          (sw+1, sh+1),
          (1, sh+1)
        ), 1)
      vol.set_alpha(150)
      vol.set_colorkey((0, 0, 0))

      vols = self.fonts[2]['font'].render(
        '%02d%%' % st['set']['vol'], True, self.colors[2])
      self.surf.blit(vols, (
        width - vols.get_width() - 10,
        height - vols.get_height() - 10
      ))
      self.surf.blit(vol, (
        width - vol.get_width() - 15 - vols.get_width(),
        height - vol.get_height() / 2 - vols.get_height() / 2 - 10
      ))
      self.shapes['vol'] = vol
      self.shapes['vols'] = vols
      checkpoint('volume')

    if old['position'] != st['position'] or first:
      pos = [(width - self.sw('bar')) / 2, height * 3 / 4]
      self.surf.blit(self.shapes['bar'], pos)
      self.surf.blit(self.shapes['dot'], (
          pos[0] + float(st['position']) / st['duration'] * (self.sw('bar') - self.sw('dot')), pos[1]
        ), None, False)
      del pos

      checkpoint('position')

    if st['set'] != old['set'] or first:
      sstring = []
      sstring.append('Playing: %s' %
        (st['set']['aaa_mode'] if st['set']['play_library'] == 'true'
          else 'playlist').title()
      )

      if st['set']['continue'] != 'true':
        sstring.append('Stop after track')
      else:
        if st['set']['repeat_current'] == 'true':
          sstring.append('Repeat current track')
        else:
          if st['set']['repeat'] != 'true':
            sstring.append('Stop after playlist')
      if st['set']['shuffle'] == 'true':
        sstring.append('Shuffle')
      sstring.reverse()

      s = self.fonts[2]['font'].render(
        ' – '.decode('utf-8').join(sstring),
        True,
        self.colors[2]
      )
      sw, sh = s.get_size()
      self.surf.update((
        0,
        height - sh - 10,
        width - 10 - self.sw('vol') - self.sw('vols'),
        height - 10
      ))
      self.surf.blit(s, (
        width - sw - 10 - self.sw('vol') - self.sw('vols') - 25,
        height - sh - 10
      ))

      checkpoint('settings')

    if int(time.time()-0.25) / 60 != int(time.time()) / 60 or first:
      s = self.fonts[1]['font'].render(
        time.strftime('%H:%M'),
        True,
        self.colors[2]
      )
      sw, sh = s.get_size()
      self.surf.blit(s, (width - sw - 10, 10))

      checkpoint('clock')

  def loop_browser(self, first):
    width, height = self.size
    if hasattr(self, 'thread') and self.thread != False:
      if isinstance(self.queue, int):
        if first:
          s = self.fonts[1]['font'].render(
            'Browser unavailable.',
            True,
            self.colors[1]
          )
          self.browsurf.blit(s, (50, 50))
          return True
        elif self.queue < 10:
          self.queue += 1
          return True
        else:
          self.queue = 0
          return False
      try:
        self.liblist = self.queue.get_nowait()
      except Queue.Empty:
        if first:
          s = self.fonts[1]['font'].render(
            'Loading browser...',
            True,
            self.colors[1]
          )
          self.browsurf.blit(s, (50, 50))
        return True
      else:
        self.thread = False
        del self.queue
        first = True

    if not hasattr(self, 'control'):
      self.control = cmus.Control()
      self.selected = {'artist': 0, 'album': -1, 'track': -1}
      self.current = 'artist'
      checkpoint('init control')

    selected = self.selected[self.current]
    pp = (height - 100) / self.fonts[1]['font'].get_linesize()
    artistlist = self.liblist['__keys__']
    albumlist = self.liblist[artistlist[self.selected['artist']]]['__keys__'] if self.current != 'artist' else False
    tracklist = self.liblist[artistlist[self.selected['artist']]][albumlist[self.selected['album']]]['__keys__'] if self.current == 'track' else False
    curlist = tracklist if self.current == 'track' else albumlist if self.current == 'album' else artistlist

    for event in pygame.event.get():
      if event.type == pygame.KEYDOWN:
        if event.key == pygame.K_DOWN:
          if selected < len(curlist)-1:
            self.selected[self.current] += 1
            first = True
        elif event.key == pygame.K_UP:
          if selected > 0:
            self.selected[self.current] -= 1
            first = True
        elif event.key == pygame.K_PAGEDOWN:
          if selected < len(curlist)-pp:
            self.selected[self.current] += pp
          else:
            self.selected[self.current] = len(curlist)-1
          first = True
        elif event.key == pygame.K_PAGEUP:
          if selected >= pp:
            self.selected[self.current] -= pp
          else:
            self.selected[self.current] = 0
          first = True
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_RIGHT):
          if self.current == 'artist':
            self.current = 'album'
          elif self.current == 'album':
            self.current = 'track'
          elif self.current == 'track':
            artist = self.liblist['__keys__'][self.selected['artist']]
            album = self.liblist[artist]['__keys__'][self.selected['album']]
            track = self.liblist[artist][album]['__keys__'][self.selected['track']]
            self.control.play_lib(self.liblist[artist][album][track])
            return False
          self.selected[self.current] = 0
          first = True
        elif event.key == pygame.K_BACKSPACE or event.key == pygame.K_LEFT:
          if self.current == 'track':
            self.current = 'album'
          elif self.current == 'album':
            self.current = 'artist'
          elif self.current == 'artist':
            return False
          first = True

    if first:
      selected = self.selected[self.current]
      artistlist = self.liblist['__keys__']
      albumlist = self.liblist[artistlist[self.selected['artist']]]['__keys__'] if self.current != 'artist' else False
      tracklist = self.liblist[artistlist[self.selected['artist']]][albumlist[self.selected['album']]]['__keys__'] if self.current == 'track' else False
      curlist = tracklist if self.current == 'track' else albumlist if self.current == 'album' else artistlist
      fromtop = 50
      self.browsurf.update((30, 30, width/3+40, height-60))
      self.browsurf.fill(
        (0, 0, 0, 150),
        (30, 30, width/3+40, height-60)
      )
      start = 0
      if selected >= len(curlist) - pp / 2:
        start = len(curlist) - pp
      elif selected > pp / 2 and len(curlist) > pp:
        start = selected - pp / 2
      if start < 0:
        start = 0
      stop = start + pp if start < len(curlist) - pp else len(curlist)
      for a in xrange(start, stop):
        value = curlist[a]
        sw = width+1
        i = 0
        while sw > width/3:
          string = value.decode('utf-8')[0:-i]+'...' if i > 0 \
              else value.decode('utf-8')
          sw, sh = self.fonts[1]['font'].size(string)
          i += 1
        if a != selected:
          s = self.fonts[1]['font'].render(string, True, self.colors[1])
        else:
          self.browsurf.fill(self.colors[0], (30, fromtop, width/3+40, sh))
          s = self.fonts[1]['font'].render(string, True,
            [255-self.colors[0][i] for i in xrange(len(self.colors[0]))]
          )
        sw, sh = s.get_size()
        self.browsurf.blit(s, (50, fromtop), None, False)
        fromtop += self.fonts[1]['font'].get_linesize()
    # TODO: indicate if list is scrollable
    return True

def start():
  m = Screen()
  first = True
  checkpoint('startup', True)
  while 1:
    step = 0.1 if m.mode == 'browser' else 0.25
    loop_start = time.time()
    checkpoint('first')
    if not m.loop(first):
      break
    if first:
      first = False
    timediff = time.time()-loop_start
    if DEBUG:
      print 'checkpoint            loop: %f' % timediff
      print '------------------------'
    time.sleep(step-(timediff%step))

if __name__ == '__main__':
  # Import Psyco if available
  try:
    import psyco
    psyco.full()
  except ImportError:
    pass
  start()

# vim: set sw=2 et
