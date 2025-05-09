import enum
import os

class Environ(enum.Enum):
    """
    Environment for the agent.
    """
    # Define the environments
    ENTRY_SERVER = "ENTRY_SERVER"
    LOG_LEVEL = "LOG_LEVEL"
    CA_SERVER = "CA_SERVER"
    
    def __str__(self):
        return self.value

    def get(self, default=None):
        """
        Get the environment variable value.
        """
        return os.environ.get(self.value, default)