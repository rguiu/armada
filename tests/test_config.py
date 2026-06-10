"""Tests for armada_ai.config."""
from armada_ai import config


class TestParseValue:
    def test_true(self):
        assert config._parse_value("true") is True

    def test_false(self):
        assert config._parse_value("false") is False

    def test_null(self):
        assert config._parse_value("null") is None

    def test_tilde_null(self):
        assert config._parse_value("~") is None

    def test_integer(self):
        assert config._parse_value("42") == 42
        assert config._parse_value("-7") == -7

    def test_float(self):
        assert config._parse_value("3.14") == 3.14

    def test_string(self):
        assert config._parse_value("hello") == "hello"


class TestParseYaml:
    def test_empty(self):
        assert config._parse_yaml("") == {}

    def test_comments(self):
        assert config._parse_yaml("# comment\nfoo: bar") == {"foo": "bar"}

    def test_simple_scalars(self):
        result = config._parse_yaml("port: 9100\nhost: 127.0.0.1\ndebug: true")
        assert result == {"port": 9100, "host": "127.0.0.1", "debug": True}

    def test_nested_dict(self):
        result = config._parse_yaml("server:\n  port: 8080\n  host: 0.0.0.0")
        assert result == {"server": {"port": 8080, "host": "0.0.0.0"}}

    def test_deep_nested(self):
        result = config._parse_yaml("a:\n  b:\n    c: 1\n    d: 2")
        assert result == {"a": {"b": {"c": 1, "d": 2}}}

    def test_list_scalar_items(self):
        result = config._parse_yaml("projects:\n  - alpha\n  - beta")
        assert "projects" in result

    def test_bare_dash_dict(self):
        result = config._parse_yaml("items:\n  -\n    key: value")
        assert "items" in result

    def test_key_with_brackets(self):
        result = config._parse_yaml("projects: []")
        assert "projects" in result

    def test_sibling_keys_outdent(self):
        result = config._parse_yaml("a:\n  b: 1\nc: 2")
        assert result == {"a": {"b": 1}, "c": 2}

    def test_blank_lines(self):
        result = config._parse_yaml("key: value\n\nother: thing")
        assert result == {"key": "value", "other": "thing"}


class TestYamlValue:
    def test_bool(self):
        assert config._yaml_value(True) == "true"
        assert config._yaml_value(False) == "false"

    def test_int_float(self):
        assert config._yaml_value(42) == "42"
        assert config._yaml_value(3.14) == "3.14"

    def test_null(self):
        assert config._yaml_value(None) == "null"

    def test_string_special_char(self):
        assert '"' in config._yaml_value("hello: world")


class TestYamlLines:
    def test_scalar(self):
        assert config._yaml_lines("key", "val", 0) == ['key: val']

    def test_int(self):
        assert config._yaml_lines("port", 9100, 0) == ['port: 9100']

    def test_bool_true(self):
        assert config._yaml_lines("enabled", True, 0) == ['enabled: true']

    def test_bool_false(self):
        assert config._yaml_lines("enabled", False, 0) == ['enabled: false']

    def test_null_value(self):
        assert config._yaml_lines("nothing", None, 0) == ['nothing: null']

    def test_empty_list(self):
        assert config._yaml_lines("items", [], 0) == ['items: []']

    def test_list_scalars(self):
        lines = config._yaml_lines("items", ["a", "b"], 0)
        assert lines[0] == "items:"
        assert "  - a" in lines
        assert "  - b" in lines

    def test_list_of_dicts(self):
        lines = config._yaml_lines("items", [{"k": "v"}], 0)
        assert lines[0] == "items:"
        assert "  -" in lines
        assert "    k: v" in lines

    def test_nested_dict(self):
        lines = config._yaml_lines("server", {"port": 9100}, 0)
        assert lines[0] == "server:"
        assert "  port: 9100" in lines

    def test_special_string_quoted(self):
        lines = config._yaml_lines("txt", "a: b", 0)
        assert lines == ['txt: "a: b"']


class TestGetAndLoad:
    def test_get_default(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "CONFIG_PATH", str(tmp_path / "nonexistent.yaml"))
        config._cache = None
        assert config.get("port") == 9100

    def test_get_all_defaults(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "CONFIG_PATH", str(tmp_path / "nonexistent.yaml"))
        config._cache = None
        cfg = config.get_all()
        assert cfg["port"] == 9100

    def test_load_from_file(self, tmp_path, monkeypatch):
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text("port: 1234\nhost: 0.0.0.0")
        monkeypatch.setattr(config, "CONFIG_PATH", str(cfg_path))
        config._cache = None
        cfg = config._load_config()
        assert cfg["port"] == 1234
        assert cfg["host"] == "0.0.0.0"

    def test_load_cache_hit(self, tmp_path, monkeypatch):
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text("port: 5555")
        monkeypatch.setattr(config, "CONFIG_PATH", str(cfg_path))
        config._cache = None
        cfg1 = config._load_config()
        cfg2 = config._load_config()
        assert cfg1 is cfg2

    def test_load_cache_force_reload(self, tmp_path, monkeypatch):
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text("port: 1111")
        monkeypatch.setattr(config, "CONFIG_PATH", str(cfg_path))
        config._cache = None
        config._load_config()
        cfg_path.write_text("port: 2222")
        cfg = config._load_config(force=True)
        assert cfg["port"] == 2222

    def test_load_corrupt_file(self, tmp_path, monkeypatch):
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text("{invalid yaml!!")
        monkeypatch.setattr(config, "CONFIG_PATH", str(cfg_path))
        config._cache = None
        cfg = config._load_config()
        assert cfg == config.DEFAULTS


class TestWriteConfig:
    def test_write_and_readback(self, tmp_path, monkeypatch):
        cfg_path = tmp_path / "config.yaml"
        monkeypatch.setattr(config, "CONFIG_PATH", str(cfg_path))
        config._cache = None
        config.write_config({"port": 7777, "host": "0.0.0.0"})
        assert cfg_path.exists()
        content = cfg_path.read_text()
        assert "port: 7777" in content
        cfg = config._load_config()
        assert cfg["port"] == 7777


class TestInitConfig:
    def test_creates_default_config(self, tmp_path, monkeypatch):
        cfg_path = tmp_path / "config.yaml"
        monkeypatch.setattr(config, "CONFIG_PATH", str(cfg_path))
        config._cache = None
        config.init_config()
        assert cfg_path.exists()
        content = cfg_path.read_text()
        assert "port: 9100" in content
