# Copyright 2026 MSPbots.ai
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
"""Process settings. Holds no credentials: those arrive per request as headers."""

from pydantic_settings import BaseSettings, SettingsConfigDict

# Auvik API clusters. The API host for a region is auvikapi.<region>.my.auvik.com.
REGIONS: tuple[str, ...] = (
    "us1",
    "us2",
    "us3",
    "us4",
    "us5",
    "us6",
    "lnx",
    "eu1",
    "eu2",
    "au1",
    "ca1",
)
DEFAULT_REGION = "us1"


def api_base_url(region: str) -> str:
    return f"https://auvikapi.{region}.my.auvik.com"


class Settings(BaseSettings):
    # extra="ignore": the runtime injects variables this project does not declare.
    model_config = SettingsConfigDict(extra="ignore")

    mcp_http_port: int = 8080
    mcp_http_host: str = "0.0.0.0"
    log_level: str = "INFO"


def get_settings() -> Settings:
    return Settings()
