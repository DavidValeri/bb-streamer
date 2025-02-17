# Copyright 2025 David Valeri
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

# Use go2rtc base image. Comes with Python 3.
FROM alexxit/go2rtc 

# Set the working directory inside the container
WORKDIR /app

# Copy requirements file
COPY ../../requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY ../../start-and-refresh-stream.py .
COPY ../../pybirdbuddy ./pybirdbuddy