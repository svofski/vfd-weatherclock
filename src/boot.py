# This file is executed on every boot (including wake-boot from deepsleep)
#import esp
#esp.osdebug(None)


def reload(mod):
  import sys
  nam = mod.__name__
  z = __import__(nam)
  del z
  del sys.modules[nam]
    
