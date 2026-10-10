"""Archive public disclosures and resolve figures from their original text/cells.

AI chooses references; this module reads the referenced numbers. Source text is
untrusted data. No company mappings, generated code, or model API calls live here.
"""

import copy
import hashlib
import io
import ipaddress
import logging
import math
import re
import socket
import zipfile
from datetime import datetime, timezone
from html.parser import HTMLParser
from http.client import HTTPSConnection
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener

from openpyxl import load_workbook
from pypdf import PdfReader


MAX_BYTES = 25 * 1024 * 1024
MAX_UNITS = 3000
MAX_TEXT = 3_000_000
MAX_READ = 100_000
FORMATS = {"dot_decimal", "comma_decimal"}


def parse_number(value, number_format="dot_decimal"):
    """Parse a complete numeric cell; missing cells are never silently zero."""
    if number_format not in FORMATS:
        raise ValueError("Choose dot_decimal or comma_decimal explicitly.")
    if isinstance(value, bool) or value is None:
        raise ValueError("Missing or invalid financial number.")
    if isinstance(value, (int, float)):
        result = float(value)
    elif isinstance(value, str):
        text = value.strip().replace("\u00a0", " ").replace("\u202f", " ").replace("\u2212", "-")
        if text in {"-", "\u2013", "\u2014"}:
            return 0.0
        percent = text.endswith("%")
        if percent:
            text = text[:-1].strip()
        negative = text.startswith("(") and text.endswith(")")
        if negative:
            text = text[1:-1].strip()
            if text.startswith(("+", "-")):
                raise ValueError("A parenthesized number cannot carry another sign.")
        decimal, thousands = (".", ",") if number_format == "dot_decimal" else (",", ".")
        integer = rf"(?:\d+|\d{{1,3}}(?:{re.escape(thousands)}\d{{3}})+|\d{{1,3}}(?: \d{{3}})+)"
        if not re.fullmatch(rf"[+-]?{integer}(?:{re.escape(decimal)}\d+)?", text):
            raise ValueError(f"Unrecognized financial number: {value!r}")
        text = text.replace(thousands, "").replace(" ", "").replace(decimal, ".")
        result = float(text) * (-1 if negative else 1) / (100 if percent else 1)
    else:
        raise ValueError("Invalid financial number type.")
    if not math.isfinite(result):
        raise ValueError("Financial numbers must be finite.")
    return result


# Thousands separated by one space occur inside a PDF table cell; multiple spaces
# delimit table columns. Both decimal conventions remain explicit at resolution.
_NUMBER = re.compile(
    r"(?<![\w.,])(?:\([+\-\u2212]?\d(?:[\d.,]*\d)?(?:[ \u00a0\u202f]\d{3})*(?:[.,]\d+)?\)"
    r"|[+\-\u2212]?\d(?:[\d.,]*\d)?(?:[ \u00a0\u202f]\d{3})*(?:[.,]\d+)?)(?:\s*%)?(?![\w.,])"
)


def _tokens(text):
    tokens = []
    for match in _NUMBER.finditer(text):
        raw = match.group()
        try:
            parse_number(raw)
        except ValueError:
            try:
                parse_number(raw, "comma_decimal")
            except ValueError:
                continue
        tokens.append({"index": len(tokens), "raw": raw, "start": match.start(), "end": match.end()})
    # A dash is nil only in a delimited table cell, never a prose dash or list mark.
    for match in re.finditer(r"(?<=\s)[\-\u2013\u2014](?=\s|$)", text):
        before, after = text[:match.start()], text[match.end():]
        if ((before.endswith("\t") or before.endswith("  "))
                and (after.startswith("\t") or after.startswith("  ") or not after or after.startswith("\n"))):
            tokens.append({"raw": match.group(), "start": match.start(), "end": match.end()})
    tokens.sort(key=lambda token: token["start"])
    for index, token in enumerate(tokens):
        token["index"] = index
    return tokens


def _public_url(url):
    """Reject local destinations before each connection, including redirects."""
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.port not in (None, 443)):
        raise ValueError("Sources must use public HTTPS URLs without credentials or custom ports.")
    _public_addresses(parsed.hostname)
    return url


def _public_addresses(hostname):
    try:
        addresses = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError("Source host could not be resolved.") from exc
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError("A source URL resolved to a nonpublic address.")
    return [item[4][0] for item in addresses]


class _PublicHTTPSConnection(HTTPSConnection):
    def connect(self):
        # Connect to the validated IP itself; a second DNS lookup must not turn a
        # public hostname into an internal destination between validation and use.
        address = _public_addresses(self.host)[0]
        self.sock = socket.create_connection((address, self.port), self.timeout, self.source_address)
        self.sock = self._context.wrap_socket(self.sock, server_hostname=self.host)


class _PublicHTTPSHandler(HTTPSHandler):
    def https_open(self, request):
        return self.do_open(_PublicHTTPSConnection, request, context=self._context)


class _SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        _public_url(newurl)
        return super().redirect_request(request, fp, code, message, headers, newurl)


def download(url):
    """Fetch a bounded disclosure; never follow a redirect to a private service."""
    _public_url(url)
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 ResearchPlatform/0.1"})
    # Proxies can redirect connections to local services, so source retrieval uses
    # direct validated HTTPS connections, retaining normal TLS certificate checks.
    with build_opener(ProxyHandler({}), _SafeRedirect(), _PublicHTTPSHandler()).open(request, timeout=30) as response:
        final_url = _public_url(response.url)
        payload = response.read(MAX_BYTES + 1)
        if len(payload) > MAX_BYTES:
            raise ValueError("Source exceeds the 25 MB download limit.")
        return payload, final_url, response.headers.get_content_type()


class _HTMLText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self.hidden += 1
        if not self.hidden and tag in {"p", "div", "br", "tr", "h1", "h2", "h3", "li", "table"}:
            self.parts.append("\n")
        if not self.hidden and tag in {"td", "th"}:
            self.parts.append("\t")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"} and self.hidden:
            self.hidden -= 1
        if not self.hidden and tag in {"p", "div", "tr", "h1", "h2", "h3", "li", "table"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def _units(payload, file_format):
    if file_format == "pdf":
        pdf = PdfReader(io.BytesIO(payload))
        if len(pdf.pages) > 500:
            raise ValueError("PDF exceeds the 500-page source limit.")
        for index, page in enumerate(pdf.pages, 1):
            messages = []
            capture = logging.Handler()
            capture.emit = lambda record: messages.append(record.getMessage())
            logger = logging.getLogger("pypdf")
            logger.addHandler(capture)
            try:
                text = page.extract_text(extraction_mode="layout") or ""
            finally:
                logger.removeHandler(capture)
            yield {"unit_id": f"page:{index}", "text": text, "numbers": _tokens(text), "warnings": messages}
            if messages:
                # Rotated headings can be omitted by layout extraction. Give the
                # reviewer the complementary plain extraction instead of hiding it.
                plain = page.extract_text(extraction_mode="plain") or ""
                yield {"unit_id": f"page:{index}:plain", "text": plain, "numbers": _tokens(plain),
                       "warnings": ["Alternative text order; verify column meanings against the original page."]}
    elif file_format == "xlsx":
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            if len(archive.infolist()) > 5000 or sum(item.file_size for item in archive.infolist()) > 100 * 1024 * 1024:
                raise ValueError("Spreadsheet exceeds the uncompressed archive limit.")
        workbook = load_workbook(io.BytesIO(payload), data_only=True, read_only=True)
        try:
            for sheet in workbook:
                if sheet.max_row is None or sheet.max_column is None:
                    raise ValueError("Spreadsheet omits worksheet dimensions; bounded extraction cannot verify its extent.")
                if sheet.max_row > 10000 or sheet.max_column > 300:
                    raise ValueError("Spreadsheet dimensions exceed the bounded extraction limit.")
                for row in sheet.iter_rows():
                    populated = [cell for cell in row if cell.value is not None]
                    if not populated:
                        continue
                    text = " | ".join(f"{cell.coordinate}: {cell.value}" for cell in populated)
                    numbers = []
                    for cell in populated:
                        value = cell.value
                        for number_format in ("dot_decimal", "comma_decimal"):
                            try:
                                parse_number(value, number_format)
                            except ValueError:
                                continue
                            numbers.append({"index": len(numbers), "raw": value, "locator": cell.coordinate,
                                            "display_format": cell.number_format})
                            break
                    yield {"unit_id": f"{sheet.title}!R{populated[0].row}", "text": text, "numbers": numbers}
        finally:
            workbook.close()
    else:
        parser = _HTMLText()
        # Financial websites normally use UTF-8; unsupported encodings must not
        # silently corrupt symbols and digits into a supposedly verified source.
        parser.feed(payload.decode("utf-8-sig"))
        lines = [line.strip(" \r") for line in "".join(parser.parts).splitlines() if line.strip()]
        chunk, length, index = [], 0, 1
        for line in lines:
            if len(line) > MAX_READ:
                raise ValueError("An HTML disclosure line exceeds the evidence read limit.")
            if chunk and length + len(line) > 5000:
                text = "\n".join(chunk)
                yield {"unit_id": f"chunk:{index}", "text": text, "numbers": _tokens(text)}
                chunk, length, index = [], 0, index + 1
            chunk.append(line)
            length += len(line) + 1
        if chunk:
            text = "\n".join(chunk)
            yield {"unit_id": f"chunk:{index}", "text": text, "numbers": _tokens(text)}


class SourceStore:
    """Immutable original files plus bounded, stable units available to the AI."""

    def __init__(self, directory: Path, fetcher=None):
        self.directory = Path(directory)
        self.fetcher = fetcher or download
        self.sources = []
        self._units = {}

    @staticmethod
    def _validate_spec(spec: dict):
        if not isinstance(spec, dict) or not all(key in spec for key in ("id", "url", "title", "published_at", "reason", "kind")):
            raise ValueError("Source metadata must include identity, URL, title, publication time, selection reason and kind.")
        if any(not isinstance(spec[key], str) or not spec[key].strip() for key in ("url", "title", "reason", "kind")):
            raise ValueError("Source URL, title, selection reason and kind must be nonempty text.")
        if spec["published_at"] is not None and not isinstance(spec["published_at"], str):
            raise ValueError("Publication time must be source-supplied text or null.")
        source_id = spec["id"]
        if not isinstance(source_id, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,60}", source_id):
            raise ValueError("Invalid source ID.")

    @staticmethod
    def _index(payload: bytes, file_format: str, source_id: str):
        """Use the same bounded parser for new and restored originals."""
        units, text_length = {}, 0
        for unit in _units(payload, file_format):
            text_length += len(unit["text"])
            if len(units) >= MAX_UNITS or text_length > MAX_TEXT:
                raise ValueError("Source exceeds 3000 units or 3 million extracted characters.")
            unit["source_id"] = source_id
            units[unit["unit_id"]] = unit
        if not units or not text_length:
            raise ValueError("No readable source text; scanned reports require an OCR-capable adapter.")
        metadata = {"unit_count": len(units),
                    "empty_units": [key for key, unit in units.items() if not unit["text"].strip()],
                    "extraction_warnings": [{"unit_id": key, "messages": unit["warnings"]}
                                            for key, unit in units.items() if unit.get("warnings")]}
        return units, metadata

    def add(self, spec: dict) -> dict:
        self._validate_spec(spec)
        source_id = spec["id"]
        for existing in self.sources:
            if existing["id"] == source_id:
                if existing["url"] != spec["url"]:
                    raise ValueError("A source ID cannot refer to two URLs.")
                if existing["status"] != "ready":
                    raise ValueError("Previously archived source could not be read.")
                return existing
        if len(self.sources) >= 12:
            raise ValueError("The run reached its 12-source limit.")
        payload, final_url, content_type = self.fetcher(spec["url"])
        if not isinstance(payload, bytes) or not payload or len(payload) > MAX_BYTES:
            raise ValueError("Source is empty, invalid or exceeds 25 MB.")
        if payload.startswith(b"%PDF"):
            file_format = "pdf"
        elif payload.startswith(b"PK\x03\x04"):
            file_format = "xlsx"
        elif "html" in content_type or payload.lstrip().lower().startswith((b"<!doctype html", b"<html")):
            file_format = "html"
        else:
            raise ValueError("Unsupported disclosure format; PDF, XLSX or UTF-8 HTML is required.")
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{source_id}.{file_format}"
        with path.open("xb") as output:
            output.write(payload)
        descriptor = {key: spec.get(key) for key in ("id", "url", "title", "published_at", "reason", "kind")}
        descriptor.update({"fetched_url": final_url, "fetched_at": datetime.now(timezone.utc).isoformat(),
                           "sha256": hashlib.sha256(payload).hexdigest(), "path": str(path),
                           "format": file_format, "status": "unreadable"})
        self.sources.append(descriptor)
        try:
            units, metadata = self._index(payload, file_format, source_id)
        except Exception as exc:
            descriptor["error"] = str(exc)
            raise
        self._units[source_id] = units
        descriptor.update(status="ready", **metadata)
        return descriptor

    def restore(self, descriptor: dict, *, archive_root: Path) -> dict:
        """Reopen a verified original without fetching it or rewriting its history.

        The descriptor continues to point at its original run. Only ready sources
        regain evidence units; an earlier parsing failure cannot become approval
        merely because a run is resumed.
        """
        self._validate_spec(descriptor)
        required = ("fetched_url", "fetched_at", "sha256", "path", "format", "status")
        if any(not isinstance(descriptor.get(key), str) or not descriptor[key].strip() for key in required):
            raise ValueError("Archived source metadata is incomplete.")
        source_id, file_format = descriptor["id"], descriptor["format"]
        if file_format not in {"pdf", "xlsx", "html"} or descriptor["status"] not in {"ready", "unreadable"}:
            raise ValueError("Archived source format or status is invalid.")
        if not re.fullmatch(r"[0-9a-f]{64}", descriptor["sha256"]):
            raise ValueError("Archived source hash is invalid.")
        for existing in self.sources:
            if existing["id"] == source_id:
                if existing != descriptor:
                    raise ValueError("A restored source ID cannot refer to different archived metadata.")
                return existing
        if len(self.sources) >= 12:
            raise ValueError("The run reached its 12-source limit.")

        try:
            archive_root = Path(archive_root).resolve(strict=True)
            path = Path(descriptor["path"]).resolve(strict=True)
            path.relative_to(archive_root)
        except (OSError, ValueError) as exc:
            raise ValueError("Archived source is missing or outside the allowed output directory.") from exc
        if not path.is_file() or path.name != f"{source_id}.{file_format}":
            raise ValueError("Archived source path does not match its ID and format.")
        if not 0 < path.stat().st_size <= MAX_BYTES:
            raise ValueError("Archived source is empty or exceeds 25 MB.")
        with path.open("rb") as original:
            payload = original.read(MAX_BYTES + 1)
        if not payload or len(payload) > MAX_BYTES or hashlib.sha256(payload).hexdigest() != descriptor["sha256"]:
            raise ValueError("Archived source content does not match its saved hash or size limits.")
        signature = "pdf" if payload.startswith(b"%PDF") else "xlsx" if payload.startswith(b"PK\x03\x04") else "html"
        if signature != file_format:
            raise ValueError("Archived source content does not match its saved format.")

        units = None
        if descriptor["status"] == "ready":
            if isinstance(descriptor.get("unit_count"), bool) or not isinstance(descriptor.get("unit_count"), int):
                raise ValueError("Archived source unit count is invalid.")
            units, metadata = self._index(payload, file_format, source_id)
            if any(descriptor.get(key) != value for key, value in metadata.items()):
                raise ValueError("Archived source extraction metadata changed; saved evidence cannot be replayed.")
        elif not isinstance(descriptor.get("error"), str) or not descriptor["error"]:
            raise ValueError("An unreadable archived source must retain its parsing error.")
        restored = copy.deepcopy(descriptor)
        self.sources.append(restored)
        if units is not None:
            self._units[source_id] = units
        return restored

    def catalog(self, max_units=None) -> list:
        """List stable unit IDs, explicitly marking any requested preview limit."""
        if max_units is not None and (isinstance(max_units, bool) or not isinstance(max_units, int) or max_units < 1):
            raise ValueError("Catalog limit must be a positive integer or None.")
        result = []
        for source in self.sources:
            units = list(self._units.get(source["id"], {}).values())
            selected = units if max_units is None else units[:max_units]
            result.append(dict(source, unit_count=len(units), catalog_truncated=len(selected) < len(units),
                               units=[{"id": unit["unit_id"], "preview": " ".join(unit["text"].split())[:100],
                                       "number_count": len(unit["numbers"])} for unit in selected]))
        return result

    def search(self, query: str, limit=30) -> dict:
        """Find literal text anywhere in archived units without enlarging catalogs."""
        if not isinstance(query, str) or not query.strip() or len(query) > 200:
            raise ValueError("Evidence search requires nonempty text of at most 200 characters.")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 30:
            raise ValueError("Evidence search limit must be between 1 and 30.")
        query, matches = query.strip(), []
        needle = query.casefold()
        for source_id, units in self._units.items():
            for unit_id, unit in units.items():
                text = unit["text"]
                folded = text.casefold()
                position = folded.find(needle)
                if position < 0:
                    continue
                if len(matches) == limit:
                    return {"query": query, "matches": matches, "truncated": True}
                if len(folded) != len(text):
                    # Unicode case folding can expand a character (e.g. sharp s).
                    # Recover the original offset so the preview still surrounds it.
                    offset = 0
                    for index, character in enumerate(text):
                        offset += len(character.casefold())
                        if offset > position:
                            position = index
                            break
                preview = " ".join(text[max(0, position - 60):position + 180].split())[:180]
                matches.append({"source_id": source_id, "unit_id": unit_id, "preview": preview})
        return {"query": query, "matches": matches, "truncated": False}

    def read(self, requests: list) -> list:
        result, length = [], 0
        for reference in requests:
            try:
                unit = self._units[reference["source_id"]][reference["unit_id"]]
            except KeyError as exc:
                raise ValueError("Unknown source evidence unit.") from exc
            length += len(unit["text"]) + sum(len(str(token["raw"])) + 60 for token in unit["numbers"])
            if length > MAX_READ:
                raise ValueError("Evidence read exceeds 100000 characters; request fewer units.")
            result.append(copy.deepcopy(unit))
        return result

    def resolve(self, reference: dict) -> float:
        try:
            unit = self._units[reference["source_id"]][reference["unit_id"]]
            index = reference["number_index"]
            if isinstance(index, bool) or not isinstance(index, int) or index < 0:
                raise ValueError("Invalid numeric token index.")
            token = unit["numbers"][index]
        except (KeyError, IndexError) as exc:
            raise ValueError("Numeric reference does not exist in the archived source.") from exc
        return parse_number(token["raw"], reference["number_format"])
