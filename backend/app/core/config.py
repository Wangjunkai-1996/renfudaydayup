from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    app_name: str = Field(default='Renfu Next API', alias='APP_NAME')
    environment: str = Field(default='development', alias='ENVIRONMENT')
    app_host: str = Field(default='0.0.0.0', alias='APP_HOST')
    app_port: int = Field(default=9000, alias='APP_PORT')
    frontend_origin: str = Field(default='http://localhost:5173', alias='FRONTEND_ORIGIN')
    database_url: str = Field(default='sqlite+pysqlite:///./backend-dev.db', alias='DATABASE_URL')
    redis_url: str = Field(default='redis://localhost:6379/0', alias='REDIS_URL')
    secret_key: str = Field(default='change-me', alias='SECRET_KEY')
    access_token_expire_minutes: int = Field(default=30, alias='ACCESS_TOKEN_EXPIRE_MINUTES')
    refresh_token_expire_days: int = Field(default=14, alias='REFRESH_TOKEN_EXPIRE_DAYS')
    access_cookie_name: str = Field(default='renfu_access_token', alias='ACCESS_COOKIE_NAME')
    refresh_cookie_name: str = Field(default='renfu_refresh_token', alias='REFRESH_COOKIE_NAME')
    bootstrap_admin_username: str = Field(default='legacy_admin', alias='BOOTSTRAP_ADMIN_USERNAME')
    bootstrap_admin_password: str = Field(default='ChangeMe123!', alias='BOOTSTRAP_ADMIN_PASSWORD')
    auto_create_schema: bool = Field(default=False, alias='AUTO_CREATE_SCHEMA')
    mount_legacy_app: bool = Field(default=True, alias='MOUNT_LEGACY_APP')

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == 'production'


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
