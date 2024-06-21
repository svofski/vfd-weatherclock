from neopixel import NeoPixel
from machine import Pin, Timer, SPI
import machine
from utime import sleep
import _thread
import pt6315
import time, asyncio, ntptime, random
import futaba_8md06inkm
import futaba_8md06inkm_term
import boratcast_vfd
from asy_ntp_time import asy_ntp_time, settime

import util
from primitives import Queue
import wttrin
import uping

SPICLK=1000000
TIME_SYNC_INTERVAL=3600*8
RECONNECT_INTERVAL=2
VFD_NCHARS=6
SCROLL_PACE = 0.1
PERIOD_WEATHER=60	# display weather once a minute +-
PERIOD_WEATHER_REQUEST=20 	# request fresh weather every 20 mins
PERIOD_PING=60*5	# ping hosts every 5 min

BRIGHTNESS_DAY=2
BRIGHTNESS_NIGHT=1

time_is_set = False
status_led = NeoPixel(Pin(10), 1) # pin 10, 1x ws2812

from wifi_manager import WifiManager
wifi = WifiManager(ssid="vfdclock", password="vfdclock", debug=True)

def set_status(rgb):
    status_led[0] = (rgb[1], rgb[0], rgb[2])
    status_led.write()

hspi = SPI(1, baudrate=SPICLK, firstbit=SPI.LSB, sck=Pin(6), mosi=Pin(7), miso=Pin(8))
vfd1_cs = Pin(9, mode=Pin.OUT, value=1)
vfd1_drv = pt6315.PT6315(hspi, pin_cs=vfd1_cs)
term1 = pt6315.Term(vfd1_drv)

vfd2_cs = Pin(4, mode=Pin.OUT, value=1)
vfd2_res = Pin(5, mode=Pin.OUT, value=1)
vfd2_drv = futaba_8md06inkm.VFD(hspi, vfd2_res, vfd2_cs, None, digits=8, dimming=255)
term2 = futaba_8md06inkm_term.Term(vfd2_drv)

vfd = boratcast_vfd.Boratcast([term1, term2])

sleep(0.25)

vfd.begin()
vfd.setDisplay(True)
vfd.setBrightness(1)

vfd.cls(flush=True)

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

def vfd_rec_status(on):
    if on:
        vfd_status[1] |= VFD_STATUS_REC
    else:
        vfd_status[1] &= ~VFD_STATUS_REC
    vfd.direct(6, vfd_status)

def vfd_wifi_status(on):
    if on:
        vfd_status[1] |= VFD_STATUS_WIFI
    else:
        vfd_status[1] &= ~VFD_STATUS_WIFI
    vfd.direct(6, vfd_status)

def vfd_weather_status(on):
    if on:
        vfd_status[1] |= VFD_STATUS_3D
    else:
        vfd_status[1] &= ~VFD_STATUS_3D
    vfd.direct(6, vfd_status)

def vfd_access_indicator(on):
    if on:
        vfd_status[1] |= VFD_STATUS_CLOCK
    else:
        vfd_status[1] &= ~VFD_STATUS_CLOCK
    vfd.direct(6, vfd_status)
    
def vfd_wtf(glyph):
    vfd_status[0] = glyph & 255
    vfd_status[1] = (vfd_status[1] & 0xfe) | ((glyph >> 8) & 1)
    vfd.direct(6, vfd_status)

class VFDStatus:
    _statusbit = 0
    def __init__(self, statusbit):
        self._statusbit = statusbit
        
    def __enter__(self):
        vfd_status[1] |= self._statusbit
        vfd.direct(6, vfd_status)
        return self
        
    def __exit__(self, *args):
        vfd_status[1] &= ~self._statusbit
        vfd.direct(6, vfd_status)
        return False


wifi.connect_threaded()

report_queue = Queue()		# messages

weatherman = wttrin.Weatherman()

async def at_timesync():
    while True:
        if wifi.isconnected():
            util.TZ_OFFSET=wifi.timezone * 3600
            
            print('ntptime...', end='')
            ntp_time = await asy_ntp_time()
            settime(ntp_time)
            print('(async) ntp_time is ', ntp_time)
            global time_is_set
            time_is_set = True
            print("synced time: ", util.localtime(time.time()))
            await asyncio.sleep(TIME_SYNC_INTERVAL)
        else:
            await asyncio.sleep(RECONNECT_INTERVAL)
        
async def at_blinker():
    n = 0
    while True:
        if wifi.is_serving():
            vfd_rec_status(n)
            vfd_wifi_status(1)
            set_status((0,n,n))
        elif wifi.isconnected():
            vfd_wifi_status(1)
            set_status((0,1,0))
        else:
            vfd_wifi_status(n)
            set_status((n,0,0))
        n ^= 1
        vfd_weather_status(weatherman.isrunning())
        await asyncio.sleep(0.25)
        
async def at_printtask():
    lastsep = '-'
    state = 0
    while True:
        if report_queue.empty():
            dtime = util.localtime(time.time()) # year, month, mday, hour, minute, second, weekday, yearday
            sep = ':' if (time.time_ns() % 1000000000) // 100000000 < 5 else ' '
            if sep != lastsep:
                if time_is_set:
                    timestr = '\014%02d%c%02d' % (dtime[3],sep,dtime[4])
                else:
                    timestr = f'\014--{sep}--'
                vfd.puts(timestr)
                
                vfd.setBrightness(BRIGHTNESS_NIGHT if dtime[3] < 9 else BRIGHTNESS_DAY)
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
                        vfd.flush()
                        await asyncio.sleep(1)
                    elif c == '#':
                        vfd.flush()
                        await asyncio.sleep(0.1)
                    elif c == '\001':
                        pace = SCROLL_PACE if pace == 0 else 0
                    elif c == '\002':
                        state = 1
                    else:
                        vfd.putchar(c)
                        if pace > 0 or ord(c) < 32:
                            vfd.flush()
                        if pace > 0:
                            await asyncio.sleep(pace)
            vfd.flush()
        
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
            await report_queue.put(blink(f"{wifi.city:{VFD_NCHARS}}", 4))
            await report_queue.put(f"\r{wifi.city:{VFD_NCHARS}}~")
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
                res = weatherman.request(wifi.city)
            print('done')    
            if res:
                await asyncio.sleep(60*PERIOD_WEATHER_REQUEST)	# all good, wait 30 min
            else:
                await asyncio.sleep(60)		# some error, retry in 1 min
        else:
            await asyncio.sleep(1)
            
async def at_wifi_reporter():
    while True:
        if not wifi.isconnected():
            if wifi.message != None and wifi.message != '':                
                await report_queue.put(f"\001{wifi.message}...\001")
                await asyncio.sleep(len(wifi.message)*0.2 + 2)
            else:
                await asyncio.sleep(0.2)
        else:
            await asyncio.sleep(5)
   
boot_btn_pressed = False   
   
async def at_button_check():
    bootbtn = vfd1_cs#Pin(9, Pin.IN, Pin.PULL_UP)
    while True:
        bootbtn.init(mode=Pin.IN, pull=Pin.PULL_UP)
        if bootbtn.value() == 0:
            print("BOOT btn pressed")            
            while bootbtn.value() == 0:
                await asyncio.sleep(0.25)
            bootbtn.init(mode=Pin.OUT, pull=None, value=1)   # restore pin 9 = CS
            print("BOOT btn released")
            global boot_btn_pressed
            boot_btn_pressed = True
            #raise Exception("BOOT btn pressed")
            break
        bootbtn.init(mode=Pin.OUT, pull=None, value=1)    # restore pin 9 = CS
        await asyncio.sleep(1)
        
            
async def at_main(duration):
    asyncio.create_task(at_blinker())
    asyncio.create_task(at_printtask())
    asyncio.create_task(at_wifi_reporter())
    asyncio.create_task(at_timesync())
    asyncio.create_task(at_weather_reporter())
    asyncio.create_task(at_weather_requester())
    buttcheck = asyncio.create_task(at_button_check())
    
    if duration < 0:
        #asyncio.get_event_loop().run_forever()
        asyncio.get_event_loop().run_until_complete(buttcheck)
        #while not terminate_main:
        #    asyncio.sleep(1)
        #print("at_main terminated")
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

if boot_btn_pressed:
    # button pressed, reconfig
    for n in range(5):
        vfd.puts("\014RECONFIG")
        sleep(0.5)
        vfd.puts("\014")
        sleep(0.5)
    vfd.puts("\014RECONFIG")
    import os
    try:
        os.remove('wifi.dat')
    except:
        pass
    try:
        os.remove('location.dat')
    except:
        pass
    print("machine will reset")
    vfd.puts("\014REBOOT")
    sleep(3)
    machine.reset()

