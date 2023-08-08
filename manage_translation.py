"""
Utility scripts for Python docs Polish translation.
It has to be run inside the python-docs-pl git root directory.
"""
import os
from dataclasses import dataclass
from difflib import SequenceMatcher
from itertools import combinations
from pathlib import Path
from typing import Self, Generator, Iterable
from warnings import warn

from polib import pofile
from transifex.api import transifex_api

LANGUAGE = 'pl'
PROJECT_SLUG = 'python-newest'


@dataclass
class ResourceLanguageStatistics:
    name: str
    total_words: int
    translated_words: int
    total_strings: int
    translated_strings: int

    @classmethod
    def from_api_entry(cls, data: transifex_api.ResourceLanguageStats) -> Self:
        return cls(
            name=data.id.removeprefix(f'o:python-doc:p:{PROJECT_SLUG}:r:').removesuffix(f':l:{LANGUAGE}'),
            total_words=data.attributes['total_words'],
            translated_words=data.attributes['translated_words'],
            total_strings=data.attributes['total_strings'],
            translated_strings=data.attributes['translated_strings'],
        )


def _get_tx_token() -> str:
    if os.path.exists('.tx/api-key'):
        with open('.tx/api-key') as f:
            transifex_api_key = f.read()
    else:
        transifex_api_key = os.getenv('TX_TOKEN', '')
    return transifex_api_key


def _get_resources() -> list[transifex_api.Resource]:
    transifex_api.setup(auth=_get_tx_token())
    return transifex_api.Resource.filter(project=f'o:python-doc:p:{PROJECT_SLUG}').all()


def get_resource_language_stats() -> list[ResourceLanguageStatistics]:
    transifex_api.setup(auth=_get_tx_token())
    resources = transifex_api.ResourceLanguageStats.filter(
        project=f'o:python-doc:p:{PROJECT_SLUG}', language=f'l:{LANGUAGE}'
    ).all()
    return [ResourceLanguageStatistics.from_api_entry(entry) for entry in resources]


def progress_from_resources(resources: Iterable[ResourceLanguageStatistics]) -> float:
    pairs = ((e.translated_words, e.total_words) for e in resources)
    translated_total, total_total = (sum(counts) for counts in zip(*pairs))
    return translated_total / total_total * 100


def get_number_of_translators():
    translators = set(_fetch_translators())
    _remove_bot(translators)
    _check_for_aliases(translators)
    return len(translators)


def _fetch_translators() -> Generator[str, None, None]:
    for file in Path().rglob('*.po'):
        header = pofile(file).header.splitlines()
        for translator_record in header[header.index('Translators:') + 1:]:
            translator, _year = translator_record.split(', ')
            yield translator


def _remove_bot(translators: set[str]) -> None:
    translators.remove("Transifex Bot <>")


def _check_for_aliases(translators) -> None:
    for pair in combinations(translators, 2):
        if (ratio := SequenceMatcher(lambda x: x in '<>@', *pair).ratio()) > 0.64:
            warn(
                f"{pair} are similar ({ratio:.3f}). Please add them to aliases list or bump the limit."
            )


def language_switcher(entry: ResourceLanguageStatistics) -> bool:
    language_switcher_resources_prefixes = ('bugs', 'tutorial', 'library--functions')
    return any(entry.name.startswith(prefix) for prefix in language_switcher_resources_prefixes)
