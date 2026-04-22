from __future__ import annotations

from toconline_mcp.tools.bank import _derive_bank_identifiers


def test_pt_account_with_nib():
    acc = {"iban": "PT50000700000055422870723", "nib": "000700000055422870723", "swift": "BESCPTPL"}
    _derive_bank_identifiers(acc)
    assert acc["pais_conta"] == "PT"
    assert acc["id_banco"] == "0007"  # first 4 digits of NIB


def test_pt_account_with_different_bank():
    acc = {"iban": "PT50003500000000000000000", "nib": "003500000000000000000", "swift": ""}
    _derive_bank_identifiers(acc)
    assert acc["id_banco"] == "0035"  # CGD
    assert acc["pais_conta"] == "PT"


def test_gb_iban_uses_swift_when_present():
    acc = {"iban": "GB22TRWI23140412345678", "nib": None, "swift": "TRWIGB22"}
    _derive_bank_identifiers(acc)
    assert acc["pais_conta"] == "GB"
    assert acc["id_banco"] == "TRWIGB22"


def test_gb_iban_without_swift_falls_back_to_iban_slice():
    acc = {"iban": "GB22TRWI23140412345678", "nib": None, "swift": None}
    _derive_bank_identifiers(acc)
    assert acc["pais_conta"] == "GB"
    assert acc["id_banco"] == "TRWI"


def test_empty_account_yields_none():
    acc = {"iban": "", "nib": "", "swift": ""}
    _derive_bank_identifiers(acc)
    assert acc["pais_conta"] is None
    assert acc["id_banco"] is None


def test_only_nib_but_iban_empty_does_not_assume_pt():
    # If IBAN is missing, we can't prove country from IBAN — pais_conta is None.
    acc = {"iban": "", "nib": "000700000055422870723", "swift": ""}
    _derive_bank_identifiers(acc)
    assert acc["pais_conta"] is None
    # Without PT confirmation from IBAN, we don't apply the PT-specific nib[:4] rule.
    assert acc["id_banco"] is None


def test_whitespace_stripped():
    acc = {"iban": "  PT50000700000055422870723  ", "nib": " 000700000055422870723 ", "swift": ""}
    _derive_bank_identifiers(acc)
    assert acc["pais_conta"] == "PT"
    assert acc["id_banco"] == "0007"


def test_short_iban_rejected():
    # IBAN too short to extract country (e.g. malformed). Must not raise.
    acc = {"iban": "P", "nib": "", "swift": ""}
    _derive_bank_identifiers(acc)
    assert acc["pais_conta"] is None
    assert acc["id_banco"] is None


def test_non_dict_is_noop():
    # Should not raise on unexpected shapes.
    _derive_bank_identifiers(None)  # type: ignore[arg-type]
    _derive_bank_identifiers("string")  # type: ignore[arg-type]
