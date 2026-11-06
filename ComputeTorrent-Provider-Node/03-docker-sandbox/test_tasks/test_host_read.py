# Security Test 1: Try to read host filesystem
import os
try:
    with open('/etc/passwd', 'r') as f:
        print('SECURITY BREACH: Read host file')
except:
    print('OK: Cannot read host files')
