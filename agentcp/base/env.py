# -*- coding: utf-8 -*-
# Copyright 2025 AgentUnion Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
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