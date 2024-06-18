import time
TZ_OFFSET = 0

def localtime(secs=None):
  """Convert the time secs expressed in seconds since the Epoch into an 8-tuple which contains: (year, month, mday, hour, minute, second, weekday, yearday) If secs is not provided or None, then the current time from the RTC is used."""
  return time.localtime((secs if secs else time.time()) + TZ_OFFSET)