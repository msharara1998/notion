import sys

def is_mac() -> bool:
    """Check if the current operating system is macOS.
    
    Returns:
        True if running on macOS, False otherwise.
    """
    return sys.platform == "darwin"
