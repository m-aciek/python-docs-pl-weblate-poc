"""
Utility scripts for Python docs Polish translation.
It has to be run inside the python-docs-pl git root directory.
"""
from dataclasses import dataclass
from difflib import SequenceMatcher
from itertools import combinations
from logging import warning, basicConfig, info
from os import getenv
from pathlib import Path
from typing import Generator, Iterable, Self
from warnings import warn

from polib import pofile
from tqdm import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm
from wlc import Component, LanguageStats, Project, Statistics, TranslationStatistics, Weblate, WeblateException

LANGUAGE = 'pl'


@dataclass
class ResourceLanguageStatistics:
    name: str
    total_words: int
    translated_words: int
    total_strings: int
    translated_strings: int
    exists: bool

    @classmethod
    def from_wlc(cls, component_name: str, stats: TranslationStatistics) -> Self:
        return cls(
            name=component_name,
            total_words=stats.total_words,
            translated_words=stats.translated_words,
            total_strings=stats.total,
            translated_strings=stats.translated,
            exists=True,
        )

    @classmethod
    def empty_from_any_wlc(cls, component_name: str, stats: TranslationStatistics) -> Self:
        return cls(
            name=component_name,
            total_words=stats.total_words,
            translated_words=0,
            total_strings=stats.total,
            translated_strings=0,
            exists=False,
        )


def _get_resources(language: str, weblate_key: str) -> Generator[ResourceLanguageStatistics, None, None]:
    weblate = Weblate(weblate_key, 'https://hosted.weblate.org/api/')
    project = Project(weblate, 'https://hosted.weblate.org/api/projects/python-docs/')
    _validate_language(language, project)
    with logging_redirect_tqdm():
        for component in tqdm(project.list()):
            if component.is_glossary:
                continue
            for translation in component.list():
                if translation.language.code == language:
                    yield ResourceLanguageStatistics.from_wlc(component.name, translation.statistics())
                    break
            else:
                info(f"{component.slug} doesn't have a {language} translation")
                yield ResourceLanguageStatistics.empty_from_any_wlc(component.name, translation.statistics())


def _validate_language(language: str, project: Project):
    for l in project.languages():
        if l.code == language:
            break
    else:
        raise SystemError(f'{language} is an incorrect language')


def get_resource_language_stats(language: str = None, weblate_key: str = None) -> list[ResourceLanguageStatistics]:
    if not language:
        language = LANGUAGE
    if not weblate_key:
        if not (weblate_key := getenv('KEY')):
            warning('Not authenticated, you will be heavy throttled')
    return list(_get_resources(language, weblate_key))


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
    language_switcher_resources_prefixes = ('bugs', 'tutorial', 'library/functions')
    return any(entry.name.startswith(prefix) for prefix in language_switcher_resources_prefixes)


basicConfig(level='INFO')
