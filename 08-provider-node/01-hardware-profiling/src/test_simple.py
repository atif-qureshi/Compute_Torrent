"""
Simple Hardware Detection Test
Tests basic CPU and RAM detection
"""
import psutil

def test_detection():
    print("=== Hardware Detection Test ===")
    
    # RAM detection
    ram_bytes = psutil.virtual_memory().total
    ram_gb = ram_bytes // (1024 ** 3)
    print(f"RAM: {ram_gb} GB")
    
    # CPU detection
    cores_physical = psutil.cpu_count(logical=False)
    cores_logical = psutil.cpu_count(logical=True)
    print(f"CPU: {cores_physical} physical cores, {cores_logical} logical cores")
    
    print("\nTest passed!")

if __name__ == "__main__":
    test_detection()
