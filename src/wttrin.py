import requests
import _thread

WTTR = 'https://wttr.in'
NAMES = ['temperature', 'feelslike', 'condition', 'humidity', 'wind', 'precipitation', 'pressure', 'uv', 'moon']
FORMAT = '%t:%f:%C:%h:%w:%p:%P:%u:%m'
MOON_PHASES = ("🌑", "🌒", "🌓", "🌔", "🌕", "🌖", "🌗", "🌘")
MOON_PHASES_TEXT = (
     'NEW',
     'WAXING CRESCENT',
     'FIRST QUARTER',
     'WAXING GIBBOUS',
     'FULL',
     'WANING GIBBOUS',
     'LAST QUARTER',
     'WANING CRESCENT')
    
WIND_DIRECTION = ("↓", "↙", "←", "↖", "↑", "↗", "→", "↘")

class Weatherman:
    _location = 'Earth' # Earth, Texas
    _lock = None
    _weather = {}
    _running = False
    
    def __init__(self, location):
        self._location = location
        self._lock = _thread.allocate_lock()
        
    def request_threadproc(self):
        res = None
        try:
            url = f'{WTTR}/{self._location}?format={FORMAT}'
            res = requests.get(url)
            parts = res.text.split(':')
            with self._lock:
                self._weather = {n:parts[i] for i,n in enumerate(NAMES)}
        except Exception as e:
            print('Error in Weatherman.request:', repr(e))
        
        with self._lock:
            self._running = False            
            
    
    def request(self):
        with self._lock:
            if not self._running:
                self._running = True
                _thread.start_new_thread(self.request_threadproc, ())
                return True
        return False
    
    def get(self, key):
        with self._lock:
            try:
                return self._weather[key]
            except:
                return None
            
    def get_moon_phase_text(self):
        try:
            unicode = self.get('moon')
            i = MOON_PHASES.index(unicode)
            return MOON_PHASES_TEXT[i]
        except:
            return None        
    
    def isrunning(self):
        with self._lock:
            return self._running
        
#w = Weatherman('Batumi')
#w.request()

#print(w._weather)
#print(w.get('feelslike'))
