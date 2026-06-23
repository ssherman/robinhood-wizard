from rh_wizard.masking import mask_account


def test_masks_all_but_last_four():
    assert mask_account("ACC123456") == "*****3456"


def test_short_values_unchanged():
    assert mask_account("12") == "12"


def test_coerces_non_str():
    assert mask_account(1234567) == "***4567"
