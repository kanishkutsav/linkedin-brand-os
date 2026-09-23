from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "LinkedIn Personal Brand OS"
    environment: str = "development"
    app_env: str = "development"
    database_url: str = "sqlite+aiosqlite:///./brand_os.db"
    emergency_stop: bool = False
    approval_ttl_minutes: int = 60
    cors_origins: str = "http://localhost:3000"
    secret_key: str = "dev-secret-change-me"
    render_external_url: str | None = None
    supabase_url: str | None = None
    supabase_anon_key: str | None = None
    supabase_service_role_key: str | None = None
    jwt_secret: str | None = None
    frontend_url: str | None = None
    linkedin_client_id: str | None = None
    linkedin_client_secret: str | None = None
    linkedin_api_base_url: str | None = None
    api_base_url: str | None = None
    linkedin_redirect_uri: str | None = None

    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.8-flash"

    agent_enabled: bool = True
    agent_timezone: str = "Asia/Kolkata"
    agent_daily_discovery_enabled: bool = True
    agent_daily_discovery_hour: int = 9
    agent_daily_discovery_minute: int = 0
    agent_calendar_enabled: bool = True
    agent_calendar_hour: int = 9
    agent_calendar_minute: int = 15

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        origins = [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]
        if self.render_external_url and self.render_external_url not in origins:
            origins.append(self.render_external_url)
        return origins

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production" or self.app_env.lower() == "production"


settings = Settings()
