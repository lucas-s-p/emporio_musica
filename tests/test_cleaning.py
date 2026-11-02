from emporio.data.cleaning import blank_to_none, detect_brand, normalize_text


def test_normalize_text_removes_accents_and_case() -> None:
    assert normalize_text("  Violão   AÇO ") == "violao aco"


def test_detect_brand_in_the_middle_of_the_name() -> None:
    assert detect_brand("Bateria Acústica Yamaha Kit 1 Studio") == "Yamaha"
    assert detect_brand("Music Man Bass 1X Electric Bass") == "Music Man"
    assert detect_brand("Instrumento Qualquer") is None


def test_blank_to_none() -> None:
    assert blank_to_none("  ") is None
    assert blank_to_none(None) is None
    assert blank_to_none(" x ") == "x"