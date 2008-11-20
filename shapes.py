import pygame

def gen_gradient(size, color1, color2):
  width, height = size
  surface = pygame.Surface(size)
  step = [float(color2[i] - color1[i]) / height for i in xrange(len(color1))]
  for i in xrange(height):
    pygame.draw.line(surface,
      [color1[j] + step[j] * i for j in xrange(len(step))],
      (0, i),
      (width, i)
    )
  return surface

def gen_dot(radius, color):
  width, height = size = [radius*2]*2
  surface = pygame.Surface(size)
  surface.set_colorkey((0, 0, 0))
  pygame.draw.ellipse(surface, color, (0, 0, radius*2-1, radius*2), 0)
  return surface

def gen_bar(size, color):
  width, height = size
  tmpsurf = pygame.Surface((height, height))
  tmpsurf.set_colorkey((0, 0, 0))
  pygame.draw.circle(tmpsurf, color, [height/2]*2, height/2, 1)
  surface = pygame.Surface(size)
  surface.set_colorkey((0, 0, 0))
  surface.blit(tmpsurf, (0, 0), (0, 0, height/2, height))
  surface.blit(tmpsurf, (width-height/2, 0), (height/2+1, 0, height/2, height))
  pygame.draw.line(surface, color, (height/2, 0), (width-height/2, 0), 1)
  pygame.draw.line(surface, color, (height/2, height-1), (width-height/2, height-1), 1)
  return surface

def gen_status_back(size, color):
  width, height = size
  surface = pygame.Surface(size, pygame.SRCALPHA)
  surface.fill((0, 0, 0, 0))
  pygame.draw.circle(surface, color+(50,), (width/9, width/9), width/9, 0)
  pygame.draw.circle(surface, color+(50,), (width-width/9, width/9), width/9, 0)
  pygame.draw.circle(surface, color+(50,), (width/9, height-width/9), width/9, 0)
  pygame.draw.circle(surface, color+(50,), (width-width/9, height-width/9), width/9, 0)
  pygame.draw.rect(surface, color+(50,), (width/9, 0, width-width*2/9, height))
  pygame.draw.rect(surface, color+(50,), (0, width/9, width, height-width*2/9))
  return surface

def gen_pause(size, color):
  width, height = size
  surface = gen_status_back(size, color)
  pygame.draw.rect(surface, color, (width*2/9, width*2/9, width*2/9, height-width*4/9))
  pygame.draw.rect(surface, color, (width-width*4/9, width*2/9, width*2/9, height-width*4/9))
  return surface

def gen_stop(size, color):
  width, height = size
  surface = gen_status_back(size, color)
  pygame.draw.rect(surface, color, (width*2/9, width*2/9, width-width*4/9, height-width*4/9))
  return surface

# vim: set sw=2 et
