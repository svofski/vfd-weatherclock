def connect_wifi():
    import network
    
    sta_if = network.WLAN(network.STA_IF)
    if not sta_if.isconnected():
        ssid,passwd=None,None
        try:
            with open('network.txt', 'r') as f:
                ssid,passwd = f.read().split()
        except:
            print('ssid and password could not be read from network.txt')
            return sta_if
        
        print('connecting to ', ssid, ' network...')
        sta_if.active(True)
        sta_if.connect(ssid, passwd)

    return sta_if #sta_if.ifconfig()