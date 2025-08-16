from __future__ import annotations

import csv
from dataclasses import dataclass
from io import TextIOWrapper
from typing import Iterable, List, Tuple, Dict, Any

from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction

from .models import (
    Taxon,
    PlantMaterial,
    PropagationBatch,
    Plant,
    MaterialType,
    PropagationMethod,
    PlantStatus,
)
from .serializers import (
    TaxonSerializer,
    PlantMaterialSerializer,
    PlantSerializer,
)


@dataclass
class ImportResult:
    rows_ok: int
    rows_failed: int
    errors: List[Dict[str, Any]]
    created_ids: List[int]


def _ensure_size(upload: UploadedFile) -> None:
    max_bytes = int(getattr(settings, "MAX_IMPORT_BYTES", 5_000_000))
    size = upload.size if upload.size is not None else 0
    if size and size > max_bytes:
        raise ValueError(f"File too large (>{max_bytes} bytes).")
    # If size is 0 or unknown, we still guard by reading only through TextIOWrapper below.


def _open_csv(upload: UploadedFile) -> Iterable[Dict[str, str]]:
    """
    Wrap the uploaded file in a text wrapper for csv.DictReader.
    Caller must *not* reuse the file after this call.
    """
    _ensure_size(upload)
    # decode as UTF-8 with BOM handling
    text = TextIOWrapper(upload.file, encoding="utf-8-sig", newline="")
    reader = csv.DictReader(text)
    if not reader.fieldnames:
        raise ValueError("Missing header row.")
    for row in reader:
        yield row


def _normalize_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    return str(v).strip()


def _normalize_choice(choice_cls, value: Any) -> str:
    """
    Accept either the canonical value (exact) or case-insensitive label.
    Returns canonical value or raises ValueError.
    """
    s = _normalize_str(value)
    if not s:
        raise ValueError("Empty choice value.")
    # direct match to value
    for val, _label in choice_cls.choices:
        if s == val:
            return val
    # case-insensitive label match
    label_map = {label.lower(): val for val, label in choice_cls.choices}
    if s.lower() in label_map:
        return label_map[s.lower()]
    # also allow common relaxed variants (e.g., snake/hyphen -> space)
    relaxed = s.lower().replace("_", " ").replace("-", " ")
    if relaxed in label_map:
        return label_map[relaxed]
    raise ValueError(f"Invalid choice '{value}'. Allowed: {', '.join(v for v, _ in choice_cls.choices)}")


# ------------------------------ Import runners ------------------------------

def import_taxa(user, rows: Iterable[Dict[str, str]], dry_run: bool = False) -> ImportResult:
    ok, failed = 0, 0
    errors: List[Dict[str, Any]] = []
    created_ids: List[int] = []

    with transaction.atomic():
        for idx, row in enumerate(rows, start=2):  # header is line 1
            payload = {
                "scientific_name": _normalize_str(row.get("scientific_name")),
                "cultivar": _normalize_str(row.get("cultivar")),
                "clone_code": _normalize_str(row.get("clone_code")),
            }
            ser = TaxonSerializer(data=payload)
            if not ser.is_valid():
                failed += 1
                errors.append({"row": idx, "error": ser.errors})
                continue
            if dry_run:
                ok += 1
                continue
            obj = ser.save(user=user)
            created_ids.append(obj.id)
            ok += 1
        if dry_run:
            transaction.set_rollback(True)
    return ImportResult(ok, failed, errors, created_ids)


def import_materials(user, rows: Iterable[Dict[str, str]], dry_run: bool = False) -> ImportResult:
    ok, failed = 0, 0
    errors: List[Dict[str, Any]] = []
    created_ids: List[int] = []

    with transaction.atomic():
        for idx, row in enumerate(rows, start=2):
            # FK: taxon must belong to user
            try:
                taxon_id = int(_normalize_str(row.get("taxon_id")))
                taxon = Taxon.objects.for_user(user).get(pk=taxon_id)
            except (ValueError, Taxon.DoesNotExist):
                failed += 1
                errors.append({"row": idx, "field": "taxon_id", "error": "Not found or invalid."})
                continue

            # Choices
            try:
                material_type = _normalize_choice(MaterialType, row.get("material_type"))
            except ValueError as e:
                failed += 1
                errors.append({"row": idx, "field": "material_type", "error": str(e)})
                continue

            payload = {
                "taxon": taxon.id,
                "material_type": material_type,
                "lot_code": _normalize_str(row.get("lot_code")),
                "notes": _normalize_str(row.get("notes")),
            }
            ser = PlantMaterialSerializer(data=payload)
            if not ser.is_valid():
                failed += 1
                errors.append({"row": idx, "error": ser.errors})
                continue
            if dry_run:
                ok += 1
                continue
            obj = ser.save(user=user)
            created_ids.append(obj.id)
            ok += 1
        if dry_run:
            transaction.set_rollback(True)
    return ImportResult(ok, failed, errors, created_ids)


def import_plants(user, rows: Iterable[Dict[str, str]], dry_run: bool = False) -> ImportResult:
    ok, failed = 0, 0
    errors: List[Dict[str, Any]] = []
    created_ids: List[int] = []

    with transaction.atomic():
        for idx, row in enumerate(rows, start=2):
            # FKs and ownership
            try:
                taxon_id = int(_normalize_str(row.get("taxon_id")))
                taxon = Taxon.objects.for_user(user).get(pk=taxon_id)
            except (ValueError, Taxon.DoesNotExist):
                failed += 1
                errors.append({"row": idx, "field": "taxon_id", "error": "Not found or invalid."})
                continue

            batch_id_raw = _normalize_str(row.get("batch_id"))
            batch_id = int(batch_id_raw) if batch_id_raw else None
            batch = None
            if batch_id is not None:
                try:
                    batch = PropagationBatch.objects.for_user(user).get(pk=batch_id)
                except PropagationBatch.DoesNotExist:
                    failed += 1
                    errors.append({"row": idx, "field": "batch_id", "error": "Not found or invalid."})
                    continue

            # Choices
            status_val = row.get("status") or PlantStatus.ACTIVE
            try:
                status = _normalize_choice(PlantStatus, status_val)
            except ValueError as e:
                failed += 1
                errors.append({"row": idx, "field": "status", "error": str(e)})
                continue

            qty_raw = _normalize_str(row.get("quantity") or "1")
            try:
                qty = int(qty_raw)
                if qty < 1:
                    raise ValueError
            except ValueError:
                failed += 1
                errors.append({"row": idx, "field": "quantity", "error": "Must be integer >= 1."})
                continue

            payload = {
                "taxon": taxon.id,
                "batch": batch.id if batch else None,
                "status": status,
                "quantity": qty,
                "acquired_on": _normalize_str(row.get("acquired_on")),
                "notes": _normalize_str(row.get("notes")),
            }
            # Serializer will validate date format etc.
            ser = PlantSerializer(data=payload)
            if not ser.is_valid():
                failed += 1
                errors.append({"row": idx, "error": ser.errors})
                continue

            if dry_run:
                ok += 1
                continue
            obj = ser.save(user=user)
            created_ids.append(obj.id)
            ok += 1

        if dry_run:
            transaction.set_rollback(True)

    return ImportResult(ok, failed, errors, created_ids)
