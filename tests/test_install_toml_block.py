"""The marker-delimited TOML block: ownership is a whole line, bytes are UTF-8, writes never truncate."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from agentseam import install as I  # noqa: E402


def test_an_owner_that_prefixes_another_owner_does_not_own_its_block(isolated_home):
    """`chock` is a prefix of `chock-java-security`, and both are consumers of this library.

    block_bounds() used a bare substring find, so the shorter owner's begin AND end markers
    matched inside the longer owner's: installed(owner="chock") said yes to a block it never
    wrote, install(owner="chock") replaced the other owner's block with its own -- closed by
    the other owner's end marker -- and uninstall(owner="chock") deleted it."""
    cfg = isolated_home / ".kimi-code" / "config.toml"
    I.install("kimi_code", ["pre_tool"], "guard-java", owner="chock-java-security")
    assert not I.installed("kimi_code", owner="chock"), "a prefix of the owner is not the owner"

    I.install("kimi_code", ["pre_tool"], "guard-chock", owner="chock")
    text = cfg.read_text(encoding="utf-8")
    assert "guard-java" in text and "guard-chock" in text, text
    assert text.count(I.BEGIN) == 2 and text.count(I.END) == 2, text
    for owner, command in (("chock-java-security", "guard-java"), ("chock", "guard-chock")):
        assert I.installed("kimi_code", owner=owner, events=["pre_tool"], command=command), owner

    assert I.uninstall("kimi_code", owner="chock") is True
    after = cfg.read_text(encoding="utf-8")
    assert "guard-java" in after and "guard-chock" not in after, after
    assert I.installed("kimi_code", owner="chock-java-security")
    assert not I.installed("kimi_code", owner="chock")


def test_a_marker_quoted_inside_a_comment_is_not_a_block(isolated_home):
    """The same substring find matched our markers anywhere on a line, a comment included."""
    cfg = isolated_home / ".kimi-code" / "config.toml"
    cfg.parent.mkdir()
    comment = "# agentseam wraps its hooks in '%s agentseam' ... '%s agentseam'\n" % (I.BEGIN, I.END)
    own = comment + '[model]\nname = "kimi"\n'
    cfg.write_text(own, encoding="utf-8")

    assert not I.installed("kimi_code")
    assert I.uninstall("kimi_code") is False
    assert cfg.read_text(encoding="utf-8") == own, "a query rewrote the file"

    I.install("kimi_code", ["pre_tool"], "guard.py")
    text = cfg.read_text(encoding="utf-8")
    assert text.startswith(own), "the user's own text was cut at the quoted marker"
    assert I.installed("kimi_code", events=["pre_tool"], command="guard.py")
    assert I.uninstall("kimi_code") is True
    assert cfg.read_text(encoding="utf-8") == own


def test_toml_install_reads_and_writes_utf8_whatever_the_platform_locale(isolated_home, tmp_path):
    """write_block()/remove_block() opened config.toml with no encoding -- the platform locale.

    Under a Windows code page (or any non-UTF-8 locale) a user's config holding one non-ASCII
    byte failed to decode, and a command holding one character the code page lacks failed to
    ENCODE -- after "w" had already truncated the file to zero bytes. Run in a subprocess with
    the UTF-8 mode and locale coercion off, which is the only way to get a non-UTF-8 locale
    on a modern CPython."""
    cfg = isolated_home / ".kimi-code" / "config.toml"
    cfg.parent.mkdir()
    original = '[model]\nname = "kimi-\u0101"\n\n[[hooks]]\nevent = "Stop"\ncommand = "echo caf\u00e9"\n'.encode(
        "utf-8"
    )
    cfg.write_bytes(original)
    script = tmp_path / "wire.py"
    script.write_text(
        "import sys\n"
        "sys.path.insert(0, %r)\n"
        "from agentseam import install\n"
        "install.install('kimi_code', ['pre_tool'], 'python3 guard.py --tag \\u2713')\n"
        "assert install.installed('kimi_code', events=['pre_tool'], command='python3 guard.py --tag \\u2713')\n"
        "assert install.uninstall('kimi_code', owner='nobody') is False\n" % str(SRC),
        encoding="utf-8",
    )
    env = dict(os.environ, PYTHONUTF8="0", PYTHONCOERCECLOCALE="0", LC_ALL="C", LANG="C")
    proc = subprocess.run([sys.executable, str(script)], capture_output=True, env=env, timeout=120, check=False)
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    after = cfg.read_bytes()
    assert after.startswith(original), "the user's own bytes were not preserved: %r" % after
    assert "\u2713".encode("utf-8") in after and I.installed("kimi_code")

    script.write_text(
        "import sys\nsys.path.insert(0, %r)\nfrom agentseam import install\n"
        "assert install.uninstall('kimi_code') is True\n" % str(SRC),
        encoding="utf-8",
    )
    proc = subprocess.run([sys.executable, str(script)], capture_output=True, env=env, timeout=120, check=False)
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    assert cfg.read_bytes() == original


def test_a_command_that_cannot_be_encoded_leaves_the_config_untouched(isolated_home):
    """A lone surrogate is what an undecodable byte in a path becomes on POSIX argv, and it
    has no UTF-8 form. The failure has to come before the file is opened for writing."""
    cfg = isolated_home / ".kimi-code" / "config.toml"
    cfg.parent.mkdir()
    original = b'[model]\nname = "kimi"\n'
    cfg.write_bytes(original)
    with pytest.raises(UnicodeEncodeError):
        I.install("kimi_code", ["pre_tool"], "guard-\udcff")
    assert cfg.read_bytes() == original, "the config was truncated before the write failed"


def test_install_never_destroys_a_toml_config_it_cannot_decode(isolated_home):
    """The TOML twin of the JSON data-loss guard: a file that is not UTF-8 is refused, whole."""
    cfg = isolated_home / ".kimi-code" / "config.toml"
    cfg.parent.mkdir()
    cfg.write_bytes('[model]\nname = "kimi"\n'.encode("utf-16"))
    with pytest.raises(I.ConfigUnreadableError):
        I.install("kimi_code", ["pre_tool"], "guard.py")
    with pytest.raises(I.ConfigUnreadableError):
        I.uninstall("kimi_code")
    assert cfg.read_bytes()[:2] == b"\xff\xfe", "a UTF-16 config was overwritten"


def test_a_crlf_config_keeps_its_bytes_outside_our_block(isolated_home):
    """Text mode rewrote every line ending in the file to the platform's; a Windows-authored
    config lost its CRLFs on Linux and a git-checked-out one gained them on Windows."""
    cfg = isolated_home / ".kimi-code" / "config.toml"
    cfg.parent.mkdir()
    original = b'[model]\r\nname = "kimi"\r\n'
    cfg.write_bytes(original)
    I.install("kimi_code", ["pre_tool"], "guard.py")
    after = cfg.read_bytes()
    assert after.startswith(original), after
    assert b"\r\n[[hooks]]\r\n" in after and b"\n\n" not in after, "our block took the file's line endings"
    assert I.installed("kimi_code", events=["pre_tool"], command="guard.py")
    I.install("kimi_code", ["pre_tool"], "guard2.py")
    assert cfg.read_bytes().count(I.BEGIN.encode()) == 1, "a re-install duplicated the block"
    assert I.uninstall("kimi_code") is True
    assert cfg.read_bytes() == original
