# Security Test 3: Try to write outside mount
import os
try:
    with open('/tmp/breach.txt', 'w') as f:
        f.write('breach')
    print('SECURITY BREACH: Wrote outside mount')
except:
    print('OK: Cannot write outside mount')
