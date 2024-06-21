# Author: Igor Ferreira
# License: MIT
# Version: 2.1.0
# Description: WiFi Manager for ESP8266 and ESP32 using MicroPython.

import machine
import network
import socket
import re
import time
import _thread
import gc
from microDNSSrv import MicroDNSSrv

class WifiManager:
    message = None
    mdns = None
    city = 'Zzyzx'
    timezone = 0
    _is_serving = False
    
    def __init__(self, ssid = 'WifiManager', password = 'wifimanager', reboot = True, debug = False):
        self.wlan_sta = network.WLAN(network.STA_IF)
        self.wlan_sta.active(True)
        self.wlan_ap = network.WLAN(network.AP_IF)
        
        # Avoids simple mistakes with wifi ssid and password lengths, but doesn't check for forbidden or unsupported characters.
        if len(ssid) > 32:
            raise Exception('The SSID cannot be longer than 32 characters.')
        else:
            self.ap_ssid = ssid
        if len(password) < 8:
            raise Exception('The password cannot be less than 8 characters long.')
        else:
            self.ap_password = password
            
        # Set the access point authentication mode to WPA2-PSK.
        self.ap_authmode = 3
        
        # The file were the credentials will be stored.
        # There is no encryption, it's just a plain text archive. Be aware of this security problem!
        self.wifi_credentials = 'wifi.dat'
        self.location_and_timezone = 'location_tz.dat'
        
        # Prevents the device from automatically trying to connect to the last saved network without first going through the steps defined in the code.
        self.wlan_sta.disconnect()
        
        # Change to True if you want the device to reboot after configuration.
        # Useful if you're having problems with web server applications after WiFi configuration.
        self.reboot = reboot
        
        self.debug = debug
        self.read_location()


    def connect(self):
        if self.wlan_sta.isconnected():
            return
        profiles = self.read_credentials()
        for ssid, *_ in self.wlan_sta.scan():
            ssid = ssid.decode("utf-8")
            if ssid in profiles:
                password = profiles[ssid]
                if self.wifi_connect(ssid, password):
                    _thread.stack_size(0)
                    return
        print('Could not connect to any WiFi network. Starting the configuration portal...')
        self.web_server()
        
    
    def disconnect(self):
        if self.wlan_sta.isconnected():
            self.wlan_sta.disconnect()


    def is_connected(self):
        return self.wlan_sta.isconnected()

    def isconnected(self):
        return self.wlan_sta.isconnected()
    
    def is_serving(self):
        return self._is_serving

    def get_address(self):
        return self.wlan_sta.ifconfig()


    def write_credentials(self, profiles):
        lines = []
        for ssid, password in profiles.items():
            lines.append('{0};{1}\n'.format(ssid, password))
        with open(self.wifi_credentials, 'w') as file:
            file.write(''.join(lines))


    def read_credentials(self):
        lines = []
        try:
            with open(self.wifi_credentials) as file:
                lines = file.readlines()
        except Exception as error:
            if self.debug:
                print('read_credentials: error=', error)
            pass
        profiles = {}
        for line in lines:
            ssid, password = line.strip().split(';')
            profiles[ssid] = password
        return profiles

    def write_location(self, city, timezone):
        with open(self.location_and_timezone, 'w') as file:
            file.write(f'{city},{timezone}\n')
            
    def read_location(self):
        try:
            with open(self.location_and_timezone) as file:
                lines = file.readlines()
            for line in lines:
                self.city, tzstr = line.strip().split(',')
                try:
                    self.timezone = int(tzstr)
                except:
                    pass
                break                
        except Exception as error:
            if self.debug:
                print('read_location: error=', error)
            pass
        return self.city, self.timezone

    def wifi_connect(self, ssid, password):
        print('Trying to connect to:', ssid)
        self.message = f'Connecting to {ssid}'
        self.wlan_sta.connect(ssid, password)
        for _ in range(100):
            if self.wlan_sta.isconnected():
                print('\nConnected! Network information:', self.wlan_sta.ifconfig())
                message = ''
                return True
            else:
                print('.', end='')
                time.sleep_ms(100)
        print('\nConnection failed!')
        self.wlan_sta.disconnect()
        message = ''
        return False

    
    def web_server(self):
        self.wlan_ap.active(True)
        self.wlan_ap.config(essid = self.ap_ssid, password = self.ap_password, authmode = self.ap_authmode)
        server_socket = socket.socket()
        server_socket.close()
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind(('0.0.0.0', 80))
        server_socket.listen()#(1)
        
        myipstr = f"{self.wlan_ap.ifconfig()[0]}"
        self.mdns = MicroDNSSrv.Create({"connectivitycheck.gstatic.com" : myipstr,
                                        "detectportal.firefox.com" : myipstr,
                                        "clients3.google.com" : myipstr,
                                        "www.msftconnecttest.com" : myipstr,
                                        "www.msftncsi.com" : myipstr,
                                        "nmcheck.gnome.org" : myipstr,
                                        "captive.apple.com" : myipstr,
                                        "www.apple.com" : myipstr})
        #self.mdns = MicroDNSSrv.Create({"*" : myipstr})
        
        self._is_serving = True
        
        self.message = f'Connect to ##{self.ap_ssid}## pass ##{self.ap_password}## and open http://{self.wlan_ap.ifconfig()[0]}~'
        print(self.message)
        while True:
            if self.wlan_sta.isconnected():
                self.message = None
                self.wlan_ap.active(False)
                self.mdns.Stop()
                self.mdns = None
                gc.collect()
                if self.reboot:
                    print('The device will reboot in 5 seconds.')
                    time.sleep(5)
                    machine.reset()
            self.client, addr = server_socket.accept()
            try:
                print(f'wifi_manager: 0: {self.client} {addr}')
                self.client.settimeout(5.0)
                self.request = b''
                try:
                    while True:
                        if '\r\n\r\n' in self.request:
                            # Fix for Safari browser
                            self.request += self.client.recv(512)
                            break
                        self.request += self.client.recv(128)
                except Exception as error:
                    # It's normal to receive timeout errors in this stage, we can safely ignore them.
                    if self.debug:
                        print('wifi_manager: 1 error=', error)
                    pass
                if self.request:
                    if self.debug:
                        print('wifi_manager: 2 url=', self.url_decode(self.request))
                    url = re.search('(?:GET|POST) /(.*?)(?:\\?.*?)? HTTP', self.request).group(1).decode('utf-8').rstrip('/')
                    if url == '':
                        self.handle_root()
                    elif url == 'configure':
                        self.handle_configure()
                    else:
                        self.handle_not_found()
            except Exception as error:
                if self.debug:
                    print('wifi_manager: 3 error=', error)
                #return
            finally:
                self.client.close()


    def send_header(self, status_code = 200):
        self.client.send("""HTTP/1.1 {0} OK\r\n""".format(status_code))
        self.client.send("""Content-Type: text/html\r\n""")
        self.client.send("""Connection: close\r\n""")


    def send_response(self, payload, status_code = 200):
        self.send_header(status_code)
        self.client.sendall("""
            <!DOCTYPE html>
            <html lang="en">
                <head>
                    <title>WiFi Manager</title>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1">
                    <link rel="icon" href="data:,">
                </head>
                <body>
                    {0}
                </body>
            </html>
        """.format(payload))
        self.client.close()
        
    def send_redirect(self, url):
        self.client.send("""HTTP/1.1 302 Found\r\n""")
        self.client.send("""Location: {0}\r\n""".format(url))
        self.client.send("""Content-Type: text/html\r\n""")
        self.client.sendall("""
            <body>Redirect to captive portal</body>
            """)


    def handle_root(self):
        self.send_header()
        self.client.sendall("""
            <!DOCTYPE html>
            <html lang="en">
                <head>
                    <title>WiFi Manager</title>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1">
                    <link rel="icon" href="data:,">
                </head>
                <body>
                    <h1>WiFi Manager</h1>
                    <form action="/configure" method="post" accept-charset="utf-8">
        """.format(self.ap_ssid))
        for ssid, *_ in self.wlan_sta.scan():
            ssid = ssid.decode("utf-8")
            self.client.sendall("""
                        <p><input type="radio" name="ssid" value="{0}" id="{0}"><label for="{0}">&nbsp;{0}</label></p>
            """.format(ssid))
        self.client.sendall("""
                        <p><label for="password">Password:&nbsp;</label><input type="password" id="password" name="password"></p>
                        <p><label for="city">City:&nbsp;</label><input type="text" id="city" name="city"></p>
                        <p><label for="timezone">Timezone:&nbsp;</label><input type="number" id="timezone" name="timezone" value="0"></p>
                        <p><input type="submit" value="Connect"></p>
                    </form>
                </body>
            </html>
        """)
        self.client.close()


    def handle_configure(self):
        decoded_url = self.url_decode(self.request)
        match = re.search('ssid=([^&]*)&password=(.*)&city=(.*)&timezone=(.*)', decoded_url)
        if match:
            ssid = match.group(1).decode('utf-8')
            password = match.group(2).decode('utf-8')
            city = match.group(3).decode('utf-8')
            timezone = match.group(4).decode('utf-8')
            print(f'ssid={ssid} pass={password} city={city} timezone={timezone}')
            if len(ssid) == 0:
                self.send_response("""
                    <p>SSID must be provided!</p>
                    <p>Go back and try again!</p>
                """, 400)
            elif len(city) == 0:# or timezone < -12 or timezone > 12:
                self.send_response("""
                    <p>City name and timezone in range [-12..+12] must be provided!</p>
                    <p>Go back and try again!</p>
                """, 400)                
            elif self.wifi_connect(ssid, password):
                self.send_response("""
                    <p>Successfully connected to</p>
                    <h1>{0}</h1>
                    <p>IP address: {1}</p>
                """.format(ssid, self.wlan_sta.ifconfig()[0]))
                profiles = self.read_credentials()
                profiles[ssid] = password
                self.write_credentials(profiles)
                self.write_location(city, timezone)
                time.sleep(5)
            else:
                self.send_response("""
                    <p>Could not connect to</p>
                    <h1>{0}</h1>
                    <p>Go back and try again!</p>
                """.format(ssid))
                time.sleep(5)
        else:
            self.send_response("""
                <p>Parameters not found!</p>
            """, 400)
            time.sleep(5)
            
    def handle_not_found(self):
        #self.send_response("""
        #    <p>Page not found!</p>
        #""", 404)
        #return self.handle_root()
        print("handle_not_found --> send_redirect")
        self.send_redirect("http://192.168.4.1/")


    def url_decode(self, url_string):

        # Source: https://forum.micropython.org/viewtopic.php?t=3076
        # unquote('abc%20def') -> b'abc def'
        # Note: strings are encoded as UTF-8. This is only an issue if it contains
        # unescaped non-ASCII characters, which URIs should not.

        if not url_string:
            return b''

        if isinstance(url_string, str):
            url_string = url_string.encode('utf-8')

        bits = url_string.split(b'%')

        if len(bits) == 1:
            return url_string

        res = [bits[0]]
        appnd = res.append
        hextobyte_cache = {}

        for item in bits[1:]:
            try:
                code = item[:2]
                char = hextobyte_cache.get(code)
                if char is None:
                    char = hextobyte_cache[code] = bytes([int(code, 16)])
                appnd(char)
                appnd(item[2:])
            except Exception as error:
                if self.debug:
                    print('url_decode error=', error)
                appnd(b'%')
                appnd(item)

        return b''.join(res)

    def connect_threaded(self):
        _thread.stack_size(8000)
        _thread.start_new_thread(self.connect, ())
