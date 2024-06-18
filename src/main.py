# TODO
# fix dot display (50.7mm)
# fix V glyph, it looks like Y

import connect_wifi
from neopixel import NeoPixel
from machine import Pin, Timer, SPI
from utime import sleep
from pt6315 import PT6315
import time, asyncio, ntptime, random

import util
from primitives import Queue
import wttrin
import uping

SPICLK=1000000
TZOFS_HOURS=4				# +4
TIME_SYNC_INTERVAL=3600*8
RECONNECT_INTERVAL=2
VFD_NCHARS=6
SCROLL_PACE = 0.1
PERIOD_WEATHER=60	# display weather once a minute +-
PERIOD_WEATHER_REQUEST=20 	# request fresh weather every 20 mins
PERIOD_PING=60*5	# ping hosts every 5 min

LOCATION='batumi' # 'stephenville'

time_is_set = False
status_led = NeoPixel(Pin(10), 1) # pin 10, 1x ws2812

def set_status(rgb):
    status_led[0] = (rgb[1], rgb[0], rgb[2])
    status_led.write()

wifi = connect_wifi.connect_wifi()

class Flasher:
    _flash = 0
    callback = None
    
    def __init__(self):
        self._timer = Timer(0)
        self._timer.init(period = 250, mode=Timer.PERIODIC, callback=self.flash_cb)
        
    def flash_cb(self, tmr):
        self._flash ^= 1
        if self.callback != None:
            self.callback(self._flash)

flasher = Flasher()


hspi = SPI(1, baudrate=SPICLK, firstbit=SPI.LSB, sck=Pin(6), mosi=Pin(7), miso=Pin(8))
vfd_cs = Pin(9, mode=Pin.OUT, value=1)
vfd = PT6315(hspi, pin_cs=vfd_cs)

sleep(0.25)

vfd.begin()
vfd.setDisplay(True)
vfd.setBrightness(1)

vfd.vfd_cls()

vfd_status = [0, 0, 0]

VFD_STATUS_WIFI = 16	# red "wifi" transparant
VFD_STATUS_3D = 8		# red "3D" transparant
VFD_STATUS_CLOCK = 4	# red clock transparant
VFD_STATUS_REC = 2		# red REC transparant

VFD_WTF_PLAY = 0xb5 	# > triangle 128+1+4+16+32
VFD_WTF_EJECT = 0x1e0 	# 
VFD_WTF_EJECT2 = 0x1e	# inverted black triangle?
VFD_WTF_PLAY2 = 0x90    # small right triangle
VFD_WTF_STOP = 0x1fe	# just box
VFD_WTF_PERSP = 0x103	# kind of runway in perspective

def vfd_wifi_status(on):
    if on:
        vfd_status[1] |= VFD_STATUS_WIFI
    else:
        vfd_status[1] &= ~VFD_STATUS_WIFI
    vfd.vfd_direct(6, vfd_status)

def vfd_weather_status(on):
    if on:
        vfd_status[1] |= VFD_STATUS_3D
    else:
        vfd_status[1] &= ~VFD_STATUS_3D
    vfd.vfd_direct(6, vfd_status)

def vfd_access_indicator(on):
    if on:
        vfd_status[1] |= VFD_STATUS_CLOCK
    else:
        vfd_status[1] &= ~VFD_STATUS_CLOCK
    vfd.vfd_direct(6, vfd_status)
    
def vfd_wtf(glyph):
    vfd_status[0] = glyph & 255
    vfd_status[1] = (vfd_status[1] & 0xfe) | ((glyph >> 8) & 1)
    vfd.vfd_direct(6, vfd_status)

class VFDStatus:
    _statusbit = 0
    def __init__(self, statusbit):
        self._statusbit = statusbit
        
    def __enter__(self):
        vfd_status[1] |= self._statusbit
        vfd.vfd_direct(6, vfd_status)
        return self
        
    def __exit__(self, *args):
        vfd_status[1] &= ~self._statusbit
        vfd.vfd_direct(6, vfd_status)
        return False


def status_led_cb(s):
    if not wifi.isconnected():
        set_status((s,0,0))
        vfd_wifi_status(s)
    else:
        set_status((0,1,0))

flasher.callback = status_led_cb

report_queue = Queue()		# messages

weatherman = wttrin.Weatherman(LOCATION)

async def at_timesync():
    util.TZ_OFFSET=TZOFS_HOURS*3600
    while True:
        if wifi.isconnected():
            print('ntptime...', end='')
            try:
                with VFDStatus(VFD_STATUS_CLOCK):
                    ntptime.settime()
                global time_is_set
                time_is_set = True
                print("synced time: ", util.localtime(time.time()))
            except:
                print('error')
            await asyncio.sleep(TIME_SYNC_INTERVAL)
        else:
            await asyncio.sleep(RECONNECT_INTERVAL)
        
async def at_printtask():
    lastsep = '-'
    state = 0
    while True:
        if wifi.isconnected():
            vfd_wifi_status(1)
        vfd_weather_status(weatherman.isrunning())
        if report_queue.empty():
            dtime = util.localtime(time.time()) # year, month, mday, hour, minute, second, weekday, yearday
            sep = ':' if (time.time_ns() % 1000000000) // 100000000 < 5 else ' '
            if sep != lastsep:
                if time_is_set:
                    timestr = '\014%02d%c%02d' % (dtime[3],sep,dtime[4])
                else:
                    timestr = f'\014--{sep}--'
                vfd.vfd_puts(timestr)
                
                vfd.setBrightness(1 if dtime[3] < 9 else 2)
            await asyncio.sleep(0.05)
        else:
            report = await report_queue.get()
            pace = 0
            for c in report:
                if state == 1:
                    if c == 'A':
                        vfd_wtf(VFD_WTF_PLAY)
                    elif c == 'B':
                        vfd_wtf(VFD_WTF_EJECT)
                    elif c == 'C':
                        vfd_wtf(VFD_WTF_STOP)
                    else:
                        vfd_wtf(0)
                    state = 0
                else:
                    if c == '~':
                        vfd.vfd_flush()
                        await asyncio.sleep(1)
                    elif c == '#':
                        vfd.vfd_flush()
                        await asyncio.sleep(0.1)
                    elif c == '\001':
                        pace = SCROLL_PACE if pace == 0 else 0
                    elif c == '\002':
                        state = 1
                    else:
                        vfd.vfd_putchar(c)
                        if pace > 0 or ord(c) < 32:
                            vfd.vfd_flush()
                        if pace > 0:
                            await asyncio.sleep(pace)
            vfd.vfd_flush()
        
def blink(s, n):
    ret = ''
    for i in range(n):
        ret += '\014#' + s + '###'
    return ret

def nblink(n, width, times):
    ret = ''
    for i in range(times):
        ret += f'{n:{width}}##' + ('\010' * width) + (' ' * width) + '#' + ('\010' * width)
    ret += f'{n:{width}}'
    return ret

async def at_weather_reporter():
    await asyncio.sleep(random.randint(5,15))
    while True:
        if weatherman.get('condition') != None:
            await report_queue.put(blink(f"{LOCATION:{VFD_NCHARS}}", 4))
            await report_queue.put(f"\r{LOCATION:{VFD_NCHARS}}~")
            await report_queue.put("\002A") # icon "PLAY" on
            await report_queue.put(f"\001  {weatherman.get('condition'):{VFD_NCHARS}}\001~~")
            temp = weatherman.get('feelslike') # .replace('\xb0','"')
            await report_queue.put(f"\001  {temp:{VFD_NCHARS}}\001~~~~")
            await report_queue.put(f"\001  {'WIND':{VFD_NCHARS}}\001####\001{weatherman.get('wind')}\001~~")
            
            rain = weatherman.get('precipitation')            
            if rain != '0.0mm':
                await report_queue.put(f"\001  {'RAIN':{VFD_NCHARS}}\001####\001{rain:{VFD_NCHARS}}\001~~")
            await report_queue.put(f"\001  HUM{weatherman.get('humidity'):{VFD_NCHARS-3}}\001~~")
            
            uv = weatherman.get('uv')            
            if int(uv) > 1:
                if int(uv) < 6:
                    await report_queue.put(f"\001  UVI{uv:>3}\001~")
                else:
                    await report_queue.put(f"\001  UVI{uv:>3}\001")
                    await report_queue.put(f"\rUVI {nblink(uv, 2, 4)}~")
            await report_queue.put("\002a") # icon "PLAY" off
            await report_queue.put("\014####")
            moon = weatherman.get_moon_phase_text()
            if moon != None:
                await report_queue.put(f"\002C\001{moon}~~\001\002c\014####") # icon STOP
                    
        await asyncio.sleep(PERIOD_WEATHER + random.randint(-10,10))
        
async def at_weather_requester():
    while True:
        if wifi.isconnected():
            print('wttr...', end='')
            with VFDStatus(VFD_STATUS_CLOCK):
                res = weatherman.request()
            print('done')    
            if res:
                await asyncio.sleep(60*PERIOD_WEATHER_REQUEST)	# all good, wait 30 min
            else:
                await asyncio.sleep(60)		# some error, retry in 1 min
        else:
            await asyncio.sleep(1)
            
ping_hosts=[('caglrc.cc', 'krtek'), ('sensi.org', 'sensi'), ('hackaday.io', 'had.io')]
ping_times=[0] * len(ping_hosts)

async def at_ping_pinger():
    rr = 0
    await asyncio.sleep(random.randint(5,15))    
    while True:
        if wifi.isconnected():
            print('ping ', ping_hosts[rr][0], end='...')
            with VFDStatus(VFD_STATUS_CLOCK):
                try:
                    _,_,times = uping.ping(ping_hosts[rr][0], count=1, quiet=True)
                    ping_times[rr] = times[0]
                except:
                    ping_times[rr] = -1
                finally:
                    print('done')
            rr = (rr + 1) % len(ping_hosts)
            if rr == 0:
                await asyncio.sleep(PERIOD_PING + random.randint(-30,30))
            else:
                await asyncio.sleep(1)
        else:
            await asyncio.sleep(1)
            
async def at_ping_reporter():
    await asyncio.sleep(random.randint(5,15))
    rr = 0
    nreported = 0
    while True:
        time = ping_times[rr]
        if time != 0:
            nreported += 1
            await report_queue.put("\002B") # icon "PLAY" on
            await report_queue.put(f'\001{" ":{VFD_NCHARS}}{ping_hosts[rr][1]:{VFD_NCHARS}}\001####')
            if time < 0:
                await report_queue.put(f'\001  {"ERROR":{VFD_NCHARS}}\001{blink("ERROR",3)}~')
            else:
                await report_queue.put(f'\001{int(time):4}ms\001~')
        rr = (rr + 1) % len(ping_hosts)        
        if rr == 0:
            if nreported > 0:
                await report_queue.put("\014####")
                await report_queue.put("\002x") # icon "PLAY" off
            nreported = 0
            await asyncio.sleep(PERIOD_PING + random.randint(-30,30))

async def at_main(duration):
    asyncio.create_task(at_printtask())
    asyncio.create_task(at_timesync())
    asyncio.create_task(at_weather_reporter())
    asyncio.create_task(at_weather_requester())
    #asyncio.create_task(at_ping_pinger())
    #asyncio.create_task(at_ping_reporter())
    if duration < 0:
        asyncio.get_event_loop().run_forever()
    else:
        await asyncio.sleep(duration)
        
def async_run(duration=120):
    try:
        asyncio.run(at_main(duration))
    except KeyboardInterrupt:
        print("Interrupted")
    finally:
        asyncio.new_event_loop()
        print("async_run done")

async_run(-1)