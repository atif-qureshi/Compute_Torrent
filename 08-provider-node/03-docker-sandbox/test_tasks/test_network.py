# Security Test 2: Try network access
import socket
try:
    s = socket.socket()
    s.connect(('8.8.8.8', 53))
    print('SECURITY BREACH: Network access')
except:
    print('OK: Network blocked')
