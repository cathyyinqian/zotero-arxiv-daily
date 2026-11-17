"""Tests for zotero_arxiv_daily.utils: glob_match, send_email, tex extraction."""

import smtplib
import tarfile
import io

import pytest

from zotero_arxiv_daily.utils import glob_match, send_email, extract_tex_code_from_tar, _bm25_pick
from tests.canned_responses import make_stub_smtp


# ---------------------------------------------------------------------------
# glob_match — migrated from test_glob_match.py
# ---------------------------------------------------------------------------


class TestGlobMatch:
    """Test cases for the glob_match function."""

    def test_exact_match(self):
        assert glob_match("hello.txt", "hello.txt")
        assert not glob_match("hello.txt", "world.txt")
        assert glob_match("", "")

    def test_wildcard_asterisk(self):
        assert glob_match("hello.txt", "*.txt")
        assert not glob_match("hello.py", "*.txt")
        assert glob_match("file", "*")

        assert glob_match("hello.world.txt", "*.*.txt")
        assert not glob_match("hello.txt", "*.*.txt")
        assert glob_match("a.b.c.d", "*.*.*.*")

        assert glob_match("hello_world.txt", "hello*world.txt")
        assert glob_match("hello123world.txt", "hello*world.txt")
        assert glob_match("helloworld.txt", "hello*world.txt")
        assert not glob_match("hello_universe.txt", "hello*world.txt")

    def test_wildcard_question_mark(self):
        assert glob_match("hello.txt", "hell?.txt")
        assert not glob_match("hell.txt", "hell?.txt")
        assert glob_match("hello.txt", "he??o.txt")
        assert glob_match("heXXo.txt", "he??o.txt")
        assert not glob_match("heo.txt", "he??o.txt")

    def test_character_classes(self):
        assert glob_match("file1.txt", "file[123].txt")
        assert glob_match("file2.txt", "file[123].txt")
        assert not glob_match("file4.txt", "file[123].txt")

        assert glob_match("file1.txt", "file[1-3].txt")
        assert glob_match("file2.txt", "file[1-3].txt")
        assert not glob_match("file4.txt", "file[1-3].txt")

        assert glob_match("fileA.txt", "file[!123].txt")
        assert not glob_match("file1.txt", "file[!123].txt")

    def test_path_separators(self):
        assert glob_match("dir/file.txt", "dir/file.txt")
        assert glob_match("dir/file.txt", "*/file.txt")
        assert glob_match("dir/subdir/file.txt", "*/subdir/file.txt")
        assert glob_match("dir/subdir/file.txt", "dir/*/file.txt")
        assert glob_match("dir/subdir/file.txt", "*/*/file.txt")

    def test_complex_patterns(self):
        assert glob_match("test1_file.txt", "test[1-3]*file.txt")
        assert glob_match("test2_long_file.txt", "test[1-3]*file.txt")
        assert not glob_match("test4_file.txt", "test[1-3]*file.txt")

        assert glob_match("prefix_middle_suffix.log", "prefix*middle*.log")
        assert not glob_match("prefix_other_suffix.log", "prefix*middle*.log")

    def test_edge_cases(self):
        assert glob_match("", "**")
        assert not glob_match("", "?")
        assert not glob_match("file", "")

        assert glob_match("file-name.txt", "file-name.txt")
        assert glob_match("file_name.txt", "file_name.txt")
        assert glob_match("file.name.txt", "file.name.txt")

        assert not glob_match("File.txt", "file.txt")
        assert not glob_match("FILE.TXT", "file.txt")
        assert glob_match("file.txt", "file.txt")

    def test_partial_matches(self):
        assert glob_match("hello.txt", "hello.txt")
        assert not glob_match("prefix_hello.txt", "hello.txt")
        assert glob_match("hello.txt", "*.txt")

    def test_special_glob_characters(self):
        assert not glob_match("file[1].txt", "file[1].txt")
        assert glob_match("file1.txt", "file[1].txt")

    def test_numeric_patterns(self):
        assert glob_match("file001.txt", "file???.txt")
        assert not glob_match("file01.txt", "file???.txt")
        assert glob_match("version1.2.3.txt", "version*.txt")
        assert glob_match("version1.2.3.txt", "version?.?.?.txt")

    def test_extension_patterns(self):
        assert glob_match("document.pdf", "*.pdf")
        assert glob_match("image.jpg", "*.jpg")
        assert glob_match("script.py", "*.py")
        assert not glob_match("data.csv", "*.txt")

        assert glob_match("file.txt", "*.[tc][xs][tv]")
        assert glob_match("file.csv", "*.[tc][xs][tv]")
        assert not glob_match("file.pdf", "*.[tc][xs][tv]")

    def test_recursive_wildcard(self):
        assert glob_match("file.txt", "**/*.txt")
        assert glob_match("dir/file.txt", "**/*.txt")
        assert glob_match("dir/subdir/file.txt", "**/*.txt")
        assert glob_match("dir/subdir/subsubdir/file.txt", "**/*.txt")


# ---------------------------------------------------------------------------
# send_email
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("port", [465, 587, 1025])
def test_send_email_uses_encrypted_transport(config, monkeypatch, port):
    import ssl

    config.email.smtp_port = port
    sent = []
    calls = []
    StubSMTP = make_stub_smtp(sent)

    class RecordingSMTP(StubSMTP):
        def __init__(self, host, actual_port, **kwargs):
            calls.append(("connect", host, actual_port, kwargs))

        def starttls(self, **kwargs):
            calls.append(("starttls", kwargs))

        def login(self, user, password):
            calls.append(("login", user, password))

        def quit(self):
            calls.append(("quit",))

        def close(self):
            calls.append(("close",))

    def unexpected_transport(*args, **kwargs):
        pytest.fail("The port selected the wrong SMTP transport")

    monkeypatch.setattr(smtplib, "SMTP_SSL", RecordingSMTP if port == 465 else unexpected_transport)
    monkeypatch.setattr(smtplib, "SMTP", unexpected_transport if port == 465 else RecordingSMTP)
    send_email(config, "<html>hello</html>")

    connection = calls[0]
    assert connection[1:3] == ("localhost", port)
    assert connection[3]["timeout"] == 30
    if port == 465:
        context = connection[3]["context"]
        assert not any(call[0] == "starttls" for call in calls)
    else:
        assert calls[1][0] == "starttls"
        context = calls[1][1]["context"]
    assert context.check_hostname
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert calls[-2:] == [("quit",), ("close",)]
    assert len(sent) == 1
    sender, recipients, body = sent[0]
    assert sender == "test@example.com"
    assert recipients == ["test@example.com"]
    assert "text/html" in body


@pytest.mark.parametrize("port, failure", [
    (587, "starttls"),
    (587, "login"),
    (465, "login"),
    (587, "sendmail"),
    (465, "sendmail"),
    (587, "quit"),
])
def test_send_email_closes_on_error_without_fallback(config, monkeypatch, port, failure):
    config.email.smtp_port = port
    calls = []

    def record(operation):
        calls.append(operation)
        if operation == failure:
            raise OSError(f"{operation} failed")

    class FailingSMTP:
        def __init__(self, *args, **kwargs):
            record("connect")

        def starttls(self, **kwargs):
            record("starttls")

        def login(self, *args):
            record("login")

        def sendmail(self, *args):
            record("sendmail")

        def quit(self):
            record("quit")

        def close(self):
            record("close")

    def unexpected_transport(*args, **kwargs):
        pytest.fail("An SMTP error must not trigger a transport fallback")

    monkeypatch.setattr(smtplib, "SMTP_SSL", FailingSMTP if port == 465 else unexpected_transport)
    monkeypatch.setattr(smtplib, "SMTP", unexpected_transport if port == 465 else FailingSMTP)
    with pytest.raises(OSError, match=f"{failure} failed"):
        send_email(config, "<html>hello</html>")

    assert calls.count("connect") == 1
    assert calls[-1] == "close"
    if failure == "starttls":
        assert "login" not in calls
        assert "sendmail" not in calls


def test_send_email_ssl_connection_error_does_not_fall_back(config, monkeypatch):
    config.email.smtp_port = 465

    def failed_ssl(*args, **kwargs):
        raise OSError("SSL connection failed")

    def unexpected_smtp(*args, **kwargs):
        pytest.fail("An SSL connection error must not fall back to plaintext SMTP")

    monkeypatch.setattr(smtplib, "SMTP_SSL", failed_ssl)
    monkeypatch.setattr(smtplib, "SMTP", unexpected_smtp)
    with pytest.raises(OSError, match="SSL connection failed"):
        send_email(config, "<html>hello</html>")


# ---------------------------------------------------------------------------
# extract_tex_code_from_tar
# ---------------------------------------------------------------------------


@pytest.fixture()
def make_tar(tmp_path):
    """Create a tar file with given files, auto-cleaned by tmp_path."""

    def _make(files: dict[str, str]) -> str:
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            for name, content in files.items():
                data = content.encode()
                info = tarfile.TarInfo(name=name)
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
        path = tmp_path / "test.tar"
        path.write_bytes(buf.getvalue())
        return str(path)

    return _make


def test_extract_tex_single_file(make_tar):
    path = make_tar({"main.tex": "\\begin{document}\nHello\n\\end{document}"})
    result = extract_tex_code_from_tar(path, "test-paper")
    assert result is not None
    assert "Hello" in result["all"]


def test_extract_tex_with_input_resolution(make_tar):
    path = make_tar({
        "main.tex": "\\begin{document}\n\\input{intro}\n\\end{document}",
        "main.bbl": "",
        "intro.tex": "This is the introduction.",
    })
    result = extract_tex_code_from_tar(path, "test-paper")
    assert "This is the introduction." in result["all"]


def test_extract_tex_no_tex_files(make_tar):
    path = make_tar({"readme.md": "# Hello"})
    result = extract_tex_code_from_tar(path, "test-paper")
    assert result is None


def test_extract_tex_not_a_tar(tmp_path):
    path = tmp_path / "bad.tar"
    path.write_bytes(b"this is not a tar file")
    result = extract_tex_code_from_tar(str(path), "test-paper")
    assert result is None


def test_extract_tex_multiple_tex_no_bbl(make_tar):
    path = make_tar({
        "a.tex": "\\section{A}",
        "b.tex": "\\begin{document}\nMain content\n\\end{document}",
    })
    result = extract_tex_code_from_tar(path, "test-paper")
    assert result is not None
    assert "Main content" in result["all"]


def test_extract_tex_multiple_document_blocks_bm25(make_tar):
    """When multiple tex files contain \\begin{document}, BM25 picks the one matching paper_title."""
    path = make_tar({
        "appendix.tex": "\\begin{document}\n\\title{Supplementary Material}\nAppendix stuff\n\\end{document}",
        "main.tex": "\\begin{document}\n\\title{Quantum Entanglement in Neural Networks}\nReal content here\n\\end{document}",
    })
    result = extract_tex_code_from_tar(path, "test-paper", paper_title="Quantum Entanglement in Neural Networks")
    assert result is not None
    assert "Real content here" in result["all"]


def test_extract_tex_multiple_document_blocks_no_title(make_tar):
    """Without paper_title, falls back to the first candidate."""
    path = make_tar({
        "a.tex": "\\begin{document}\nFirst doc\n\\end{document}",
        "b.tex": "\\begin{document}\nSecond doc\n\\end{document}",
    })
    result = extract_tex_code_from_tar(path, "test-paper")
    assert result is not None
    assert result["all"] is not None


class TestBm25Pick:
    def test_picks_best_match(self):
        candidates = {
            "a.tex": "This paper discusses cats and dogs in the wild",
            "b.tex": "Quantum entanglement in neural network architectures",
        }
        assert _bm25_pick("Quantum entanglement neural networks", candidates) == "b.tex"

    def test_single_candidate(self):
        candidates = {"only.tex": "Some content here"}
        assert _bm25_pick("anything", candidates) == "only.tex"

    def test_empty_query_returns_first(self):
        candidates = {"a.tex": "hello", "b.tex": "world"}
        result = _bm25_pick("", candidates)
        assert result in candidates
