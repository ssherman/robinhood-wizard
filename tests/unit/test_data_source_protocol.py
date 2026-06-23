from rh_wizard.data.base import DataSource
from rh_wizard.models.market import SymbolData
from rh_wizard.models.signals import Signal


class _ConformingSource:
    name = "fake"

    def provides(self) -> set[Signal]:
        return {Signal.PRICE}

    def fetch(self, symbols, signals) -> dict[str, SymbolData]:
        return {s: SymbolData(symbol=s, price="1") for s in symbols}


class _NonConformingSource:
    name = "broken"
    # missing provides() and fetch()


def test_conforming_source_is_a_datasource():
    assert isinstance(_ConformingSource(), DataSource)


def test_nonconforming_source_is_not_a_datasource():
    assert not isinstance(_NonConformingSource(), DataSource)


def test_protocol_methods_callable_on_conformer():
    src = _ConformingSource()
    assert src.provides() == {Signal.PRICE}
    assert src.fetch(["AAPL"], {Signal.PRICE})["AAPL"].price is not None
