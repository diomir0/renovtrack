from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "RenovTrack"
    secret_key: str = "change-me"
    database_url: str = "sqlite+aiosqlite:///./renovtrack.db"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "mistral"
    upload_dir: str = "./uploads"

    class Config:
        env_file = ".env"


settings = Settings()
