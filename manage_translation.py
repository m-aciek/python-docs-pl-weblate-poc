#!/usr/bin/env python
#
# This python file contains utility scripts to manage Python docs Polish translation.
# It has to be run inside the python-docs-pl git root directory.
#
# Inspired by django-docs-translations script by claudep.
#
# The following commands are available:
#
# * fetch: fetch translations from transifex.com and strip source lines from the
#          files.
# * regenerate_tx_config: recreate configuration for all resources.

from argparse import ArgumentParser
import os
from dataclasses import dataclass
from difflib import SequenceMatcher
from itertools import combinations
from pathlib import Path
from re import match
from subprocess import call
import sys
from typing import Self, Callable
from urllib.parse import urlparse, parse_qs
from warnings import warn

from polib import pofile

LANGUAGE = 'pl'


def fetch():
    """
    Fetch translations from Transifex, remove source lines.
    """
    if call("tx --version", shell=True) != 0:
        sys.stderr.write("The Transifex client app is required.\n")
        exit(1)
    lang = LANGUAGE
    pull_returncode = call(
        f'tx pull -l {lang} --minimum-perc=1 --force --skip', shell=True
    )
    if pull_returncode != 0:
        exit(pull_returncode)
    for root, _, po_files in os.walk('.'):
        for po_file in po_files:
            if not po_file.endswith(".po"):
                continue
            po_path = os.path.join(root, po_file)
            call(f'msgcat --no-location -o {po_path} {po_path}', shell=True)


RESOURCE_NAME_MAP = {'glossary_': 'glossary'}
PROJECT_SLUG = 'python-newest'


def recreate_tx_config():
    """
    Regenerate Transifex client config for all resources.
    """
    resources = _get_resources()
    with open('.tx/config', 'w') as config:
        config.writelines(
            (
                '[main]\n',
                'host = https://www.transifex.com\n',
            )
        )
        for resource in resources:
            slug = resource.slug
            name = RESOURCE_NAME_MAP.get(slug, slug)
            if slug == '0':
                continue
            elif '--' in slug:
                directory, file_name = name.split('--')
                if match(r'\d+_\d+', file_name):
                    file_name = file_name.replace('_', '.')
                config.writelines(
                    (
                        '\n',
                        f'[o:python-doc:p:{PROJECT_SLUG}:r:{slug}]\n',
                        f'file_filter = {directory}/{file_name}.po\n',
                        'type = PO\n',
                        'source_lang = en\n',
                    )
                )
            else:
                config.writelines(
                    (
                        '\n',
                        f'[o:python-doc:p:{PROJECT_SLUG}:r:{slug}]\n',
                        f'file_filter = {name}.po\n',
                        'type = PO\n',
                        'source_lang = en\n',
                    )
                )


@dataclass
class Resource:
    slug: str

    @classmethod
    def from_api_v3_entry(cls, data: dict) -> Self:
        return cls(slug=data['attributes']['slug'])


@dataclass
class ResourceLanguageStatistics:
    name: str
    total_words: int
    translated_words: int
    total_strings: int
    translated_strings: int

    @classmethod
    def from_api_v3_entry(cls, data: dict) -> Self:
        return cls(
            name=data['id'].removeprefix(f'o:python-doc:p:{PROJECT_SLUG}:r:').removesuffix(f':l:{LANGUAGE}'),
            total_words=data['attributes']['total_words'],
            translated_words=data['attributes']['translated_words'],
            total_strings=data['attributes']['total_strings'],
            translated_strings=data['attributes']['translated_strings'],
        )


def _get_from_api_v3_with_cursor(url: str, params: dict) -> list[dict]:
    from requests import get

    resources = []
    cursor = None
    if os.path.exists('.tx/api-key'):
        with open('.tx/api-key') as f:
            transifex_api_key = f.read()
    else:
        transifex_api_key = os.getenv('TX_TOKEN', '')
    while True:
        response = get(
            url,
            params=params | ({'page[cursor]': cursor} if cursor else {}),
            headers={'Authorization': f'Bearer {transifex_api_key}'}
        )
        response.raise_for_status()
        response_json = response.json()
        response_list = response_json['data']
        resources.extend(response_list)
        if not response_json['links'].get('next'):  # for stats no key, for list resources null
            break
        cursor, *_ = parse_qs(urlparse(response_json['links']['next']).query)['page[cursor]']
    return resources


def _get_resources() -> list[Resource]:
    resources = _get_from_api_v3_with_cursor(
        'https://rest.api.transifex.com/resources', {'filter[project]': f'o:python-doc:p:{PROJECT_SLUG}'}
    )
    return [Resource.from_api_v3_entry(entry) for entry in resources]


def get_resource_language_stats() -> list[ResourceLanguageStatistics]:
    resources = _get_from_api_v3_with_cursor(
        'https://rest.api.transifex.com/resource_language_stats',
        {'filter[project]': f'o:python-doc:p:{PROJECT_SLUG}', 'filter[language]': f'l:{LANGUAGE}'}
    )
    return [ResourceLanguageStatistics.from_api_v3_entry(entry) for entry in resources]


def progress_from_resources(resources: list[ResourceLanguageStatistics], filter_function: Callable) -> float:
    filtered = filter(filter_function, resources)
    pairs = ((e.translated_words, e.total_words) for e in filtered)
    translated_total, total_total = (sum(counts) for counts in zip(*pairs))
    return translated_total / total_total * 100


def get_number_of_translators():
    translators = _fetch_translators()
    _remove_aliases(translators)
    _check_for_new_aliases(translators)
    return len(translators)


def _fetch_translators() -> set[str]:
    translators = set()
    for file in Path().rglob('*.po'):
        header = pofile(file).header.splitlines()
        for translator_record in header[header.index('Translators:') + 1:]:
            translator, _year = translator_record.split(', ')
            translators.add(translator)
    return translators


def _remove_aliases(translators: set[str]) -> None:
    for alias, main in (("m_aciek <maciej.olko@gmail.com>", "Maciej Olko <maciej.olko@gmail.com>"),):
        translators.remove(alias)
        assert main in translators


def _check_for_new_aliases(translators) -> None:
    for pair in combinations(translators, 2):
        if (ratio := SequenceMatcher(lambda x: x in '<>@', *pair).ratio()) > 0.64:
            warn(
                f"{pair} are similar ({ratio:.3f}). Please add them to aliases list or bump the limit."
            )


def language_switcher(entry: ResourceLanguageStatistics) -> bool:
    language_switcher_resources_prefixes = ('bugs', 'tutorial', 'library--functions')
    return any(entry.name.startswith(prefix) for prefix in language_switcher_resources_prefixes)


if __name__ == "__main__":
    RUNNABLE_SCRIPTS = ('fetch', 'recreate_tx_config')

    parser = ArgumentParser()
    parser.add_argument('cmd', choices=RUNNABLE_SCRIPTS)
    options = parser.parse_args()

    eval(options.cmd)()
