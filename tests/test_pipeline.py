from fec_mt import pipeline


def test_api_key_is_loaded_from_dotenv(tmp_path, monkeypatch):
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("FEC_API_KEY=from-dotenv\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("FEC_API_KEY", raising=False)

    assert pipeline._load_api_key() == "from-dotenv"


def test_existing_environment_api_key_takes_precedence(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("FEC_API_KEY=from-dotenv\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FEC_API_KEY", "from-environment")

    assert pipeline._load_api_key() == "from-environment"
