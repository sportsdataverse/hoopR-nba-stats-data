"""Release-format derivation for the D26d cutover: staged parquet -> ``.rds`` + ``.csv.gz``.

``v3_staging/`` is parquet-only, but a release asset set that is parquet-only
ships data ``hoopR::load_nba_*()`` cannot read -- those loaders read the
``.rds``. So every published artifact is materialized in three formats and the
``.rds`` is the one the R consumer actually opens.

- **rds** via :func:`sportsdataverse._rds.write_rds` -- a byte-parity RDS
  writer, no R install and no ``Rscript`` shell-out. It is stamped with the
  league's own S3 class chain (``hoopR_data`` first, ``data.frame`` last),
  because hoopR registers S3 methods on that class; an rds without it prints
  differently for every user.
- **csv, gzipped** (``.csv.gz``, :data:`CSV_SUFFIX`) -- matching the convention
  ``ncaa-wbb-hoops-data`` adopted in ``9f52612``. A season of pbp writes a
  multi-GB plain csv, which runs into GitHub's 2 GiB per-asset hard limit;
  gzip removes the cliff. ``GzipFile`` is given ``mtime=0`` so re-deriving the
  same frame produces byte-identical output instead of a file that differs only
  by an embedded timestamp.

**The rds is verified, not assumed.** :func:`verify_rds` re-reads the written
file with :func:`read_rds_structure` -- a minimal structural RDS-v2 reader --
and compares shape, column names, and per-column R vector type against the
source parquet. A silently truncated or mistyped rds is worse than a missing
one: it publishes as though complete and fails only in the consumer's session.
"""

from __future__ import annotations

import gzip
import struct
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Any, Optional

import polars as pl

#: Extension for the release csv. Gzipped -- see the module docstring. Every
#: caller derives the name from this constant so the writer and the uploader
#: cannot drift into staging one name and uploading another.
CSV_SUFFIX = ".csv.gz"

#: Formats published for every artifact, in upload order.
FORMATS = ("parquet", "rds", CSV_SUFFIX.lstrip("."))

#: hoopR's S3 chain (``hoopR:::make_hoopR_data``). Load-bearing, not cosmetic.
RDS_CLASS = ("hoopR_data", "tbl_df", "tbl", "data.table", "data.frame")

#: Attribute names the R producer stamps on every released frame.
RDS_TYPE_ATTR = "hoopR_type"
RDS_TIMESTAMP_ATTR = "hoopR_timestamp"

# R serialize.c SEXP type codes we can encounter in a written data.frame.
_LGLSXP, _INTSXP, _REALSXP, _STRSXP, _VECSXP = 10, 13, 14, 16, 19
_SYMSXP, _LISTSXP, _CHARSXP, _NILVALUE, _REFSXP = 1, 2, 9, 254, 255

_TYPE_NAMES = {
    _LGLSXP: "logical",
    _INTSXP: "integer",
    _REALSXP: "double",
    _STRSXP: "character",
}

#: polars dtype -> the R vector types :mod:`sportsdataverse._rds` may emit for it.
#: ``Int64`` is two-valued on purpose: the writer downgrades ids outside int32
#: range to doubles, because R has no 64-bit integer.
_ALLOWED: dict[str, tuple[str, ...]] = {
    "Boolean": ("logical",),
    "Int8": ("integer",),
    "Int16": ("integer",),
    "Int32": ("integer",),
    "UInt8": ("integer",),
    "UInt16": ("integer",),
    "Int64": ("integer", "double"),
    "UInt32": ("integer", "double"),
    "UInt64": ("integer", "double"),
    "Float32": ("double",),
    "Float64": ("double",),
    "String": ("character",),
    "Categorical": ("character",),
    "Enum": ("character",),
    "Date": ("double",),
    "Null": ("logical",),
}


def _dtype_key(dtype: Any) -> str:
    """Base-class name of a polars dtype (``Datetime(us, UTC)`` -> ``Datetime``)."""
    return type(dtype).__name__ if not isinstance(dtype, type) else dtype.__name__


def allowed_r_types(dtype: Any) -> tuple[str, ...]:
    key = _dtype_key(dtype)
    if key == "Datetime":
        return ("double",)
    return _ALLOWED.get(key, ())


# --------------------------------------------------------------------------- reader


@dataclass(frozen=True)
class RdsStructure:
    """What a written ``.rds`` actually contains, read back off disk."""

    nrows: int
    names: list[str]
    types: list[str]
    cls: list[str]

    @property
    def ncols(self) -> int:
        return len(self.names)


def _i32(fh: IO[bytes]) -> int:
    raw = fh.read(4)
    if len(raw) != 4:
        raise ValueError("truncated rds: stream ended mid-integer")
    return int(struct.unpack(">i", raw)[0])


def _charsxp(fh: IO[bytes]) -> Optional[str]:
    _i32(fh)  # flags (encoding bits; irrelevant to structure)
    n = _i32(fh)
    if n < 0:
        return None  # NA_STRING
    return fh.read(n).decode("utf-8")


def _skip(fh: IO[bytes], n: int) -> None:
    """Seek past *n* bytes without materializing them (works on a gzip stream)."""
    remaining = n
    while remaining > 0:
        chunk = fh.read(min(remaining, 1 << 20))
        if not chunk:
            raise ValueError("truncated rds: stream ended mid-vector")
        remaining -= len(chunk)


class _Reader:
    """Structural walk of an RDS-v2 XDR stream. Values are skipped, not decoded."""

    def __init__(self, fh: IO[bytes]) -> None:
        self.fh = fh
        self.symbols: list[str] = []

    def header(self) -> None:
        magic = self.fh.read(2)
        if magic != b"X\n":
            raise ValueError(f"not an XDR rds stream (magic {magic!r})")
        version = _i32(self.fh)
        if version != 2:
            raise ValueError(f"unsupported rds serialization version {version}")
        _i32(self.fh)  # writer R version
        _i32(self.fh)  # minimum reader R version

    def _symbol(self) -> str:
        """A pairlist tag: a fresh SYMSXP, or a packed back-reference to one."""
        flags = _i32(self.fh)
        if flags & 0xFF == _REFSXP:
            idx = flags >> 8 or _i32(self.fh)
            return self.symbols[idx - 1]
        if flags & 0xFF != _SYMSXP:
            raise ValueError(f"expected a symbol tag, got sexp type {flags & 0xFF}")
        name = _charsxp(self.fh) or ""
        self.symbols.append(name)
        return name

    def pairlist(self) -> dict[str, Any]:
        """Attribute chain of ``(tag, value)`` pairs, terminated by NILVALUE."""
        out: dict[str, Any] = {}
        while True:
            flags = _i32(self.fh)
            if flags == _NILVALUE:
                return out
            if flags & 0xFF != _LISTSXP:
                raise ValueError(f"expected a pairlist cell, got sexp type {flags & 0xFF}")
            # Bind the tag first: in `out[tag()] = value()` Python evaluates the
            # right-hand side BEFORE the subscript, which would read the value
            # off the stream ahead of the symbol it belongs to.
            tag = self._symbol()
            out[tag] = self.sexp()

    def sexp(self) -> Any:
        """One object. Returns strings/ints for the small vectors, a marker otherwise."""
        flags = _i32(self.fh)
        stype = flags & 0xFF
        if flags == _NILVALUE:
            return None
        has_attr = bool(flags & (1 << 9))
        value: Any

        if stype == _STRSXP:
            n = _i32(self.fh)
            value = [_charsxp(self.fh) for _ in range(n)]
        elif stype in (_INTSXP, _LGLSXP):
            n = _i32(self.fh)
            # row.names is the only short int vector we need the values of.
            if n <= 8:
                raw = self.fh.read(4 * n)
                value = list(struct.unpack(f">{n}i", raw))
            else:
                _skip(self.fh, 4 * n)
                value = _TYPE_NAMES[stype]
        elif stype == _REALSXP:
            n = _i32(self.fh)
            _skip(self.fh, 8 * n)
            value = _TYPE_NAMES[stype]
        elif stype == _VECSXP:
            n = _i32(self.fh)
            value = [self.sexp() for _ in range(n)]
        elif stype == _CHARSXP:
            raise ValueError("bare CHARSXP outside a STRSXP")
        else:
            raise ValueError(f"unsupported sexp type {stype} in a data.frame rds")

        attrs = self.pairlist() if has_attr else {}
        return {"type": _TYPE_NAMES.get(stype, str(stype)), "value": value, "attrs": attrs}


def read_rds_structure(path: Path) -> RdsStructure:
    """Read back a written ``.rds`` and report its real shape / names / column types.

    Deliberately structural: bulk column payloads are seeked past rather than
    decoded, so this costs one linear pass and bounded memory even on a
    season-sized play-by-play frame. It still fails on a truncated file --
    every length prefix is consumed, so a short stream raises.
    """
    with gzip.open(path, "rb") as fh:
        reader = _Reader(fh)  # type: ignore[arg-type]
        reader.header()
        frame = reader.sexp()
    if not isinstance(frame, dict) or not isinstance(frame["value"], list):
        raise ValueError("rds root object is not a list (expected a data.frame VECSXP)")

    attrs = frame["attrs"]
    names = attrs.get("names", {}).get("value", [])
    row_names = attrs.get("row.names", {}).get("value", [])
    cls = attrs.get("class", {}).get("value", [])
    # data.frame row.names compact form is c(NA_integer_, -nrow)
    nrows = -int(row_names[1]) if len(row_names) == 2 else len(row_names)
    types = [col["type"] for col in frame["value"]]
    return RdsStructure(nrows=nrows, names=list(names), types=types, cls=list(cls))


def verify_rds(rds_path: Path, df: pl.DataFrame) -> RdsStructure:
    """Re-read *rds_path* and assert it matches *df*. Raises ``ValueError`` on drift.

    Checks shape, column names in order, the S3 class chain, and that each
    column's R vector type is one the writer is allowed to emit for that polars
    dtype -- a Utf8 id that came back as ``double`` would be a silent
    ``"123.0"``-class corruption in every downstream R join.
    """
    got = read_rds_structure(rds_path)
    if got.nrows != df.height or got.ncols != df.width:
        raise ValueError(
            f"{rds_path.name}: rds is {got.nrows}x{got.ncols}, parquet is {df.height}x{df.width}"
        )
    if got.names != list(df.columns):
        missing = [c for c in df.columns if c not in got.names]
        raise ValueError(f"{rds_path.name}: column names differ (missing from rds: {missing[:5]})")
    if got.cls and got.cls[-1] != "data.frame":
        raise ValueError(f"{rds_path.name}: class chain does not end in data.frame: {got.cls}")
    for name, r_type in zip(df.columns, got.types):
        allowed = allowed_r_types(df.schema[name])
        if allowed and r_type not in allowed:
            raise ValueError(
                f"{rds_path.name}: column {name!r} is {df.schema[name]} in parquet but "
                f"{r_type} in the rds (allowed: {', '.join(allowed)})"
            )
    return got


# --------------------------------------------------------------------------- writer


def write_csv_gz(df: pl.DataFrame, path: Path) -> Path:
    """Write *df* as a gzipped csv. Deterministic: no embedded mtime."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
            df.write_csv(gz)  # type: ignore[arg-type]
    return path


def derive_formats(
    parquet: Path,
    out_dir: Path,
    *,
    dataset: str = "",
    force: bool = False,
    verify: bool = True,
) -> dict[str, Path]:
    """Materialize the ``.rds`` + ``.csv.gz`` siblings of a staged parquet.

    Returns ``{format: path}`` for all three formats (the parquet is returned
    as-is, not copied). Existing derived files newer than the parquet are reused
    unless *force* -- re-deriving 120 season frames on every dry run would make
    the manifest step cost hours.

    The rds is verified against the parquet before it is considered done
    (:func:`verify_rds`); a failed verification deletes the file rather than
    leaving a bad artifact that a later run would happily reuse.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = parquet.stem
    rds = out_dir / f"{stem}.rds"
    csv = out_dir / f"{stem}{CSV_SUFFIX}"
    fresh = parquet.stat().st_mtime

    need_rds = force or not rds.exists() or rds.stat().st_mtime < fresh
    need_csv = force or not csv.exists() or csv.stat().st_mtime < fresh
    if need_rds or need_csv:
        from sportsdataverse._rds import write_rds

        df = pl.read_parquet(parquet)
        if need_csv:
            write_csv_gz(df, csv)
        if need_rds:
            write_rds(
                df,
                rds,
                cls=list(RDS_CLASS),
                attributes={
                    RDS_TYPE_ATTR: dataset or stem,
                    RDS_TIMESTAMP_ATTR: datetime.now(timezone.utc),
                },
            )
            if verify:
                try:
                    verify_rds(rds, df)
                except Exception:
                    rds.unlink(missing_ok=True)
                    raise

    return {"parquet": parquet, "rds": rds, CSV_SUFFIX.lstrip("."): csv}
